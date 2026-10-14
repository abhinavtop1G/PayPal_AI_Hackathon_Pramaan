"""Online campaign tracker: links risky accounts into scam campaigns and ranks them as analyst cases.

Per transfer it updates account balances, spreads *taint* from a flagged account to the accounts it forwards
money to (the layer-2/3 mules have no history of their own yet), and links accounts that (a) forward
money to each other or (b) were paid by the same victim within 48h. Connected components of that graph are
campaigns. Known cash-out sinks / own-settlement accounts are not scoreable and therefore never become
nodes, so a shared exchange account cannot glue unrelated campaigns together.

A flagged account on its own only goes on a watchlist. A *case* needs corroboration: two or more linked flagged
accounts, or a single account that was flagged on at least `solo_min_hits` separate credits (isolated false flags are
usually one-offs), *and* at least `solo_min_victims` distinct outside payers feeding the component (a group of accounts that only pay each other is not a scam campaign).

Links come from money moving between flagged accounts. Linking two accounts because the same payer paid both is
off by default (`min_shared_victims=0`): over 90 days, coincidences between heavy-hitter accounts merge unrelated
campaigns into one.

A case is ranked by what an analyst can still save, not by a raw score:

    priority = risk * (recoverable_rupees + expected_next_24h_inflow) * exp(-hours_since_last_victim / 12) * (1.5 if novel)
"""
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

H = 3600.0
D = 86400.0


@dataclass
class Case:
    case_id: str
    opened_ts: float
    accounts: list
    n_flagged: int
    n_victims: int
    victims_24h: int
    loss_in: float
    recoverable: float
    inflow_24h: float
    last_victim_ts: float | None
    risk: float
    novel: bool
    priority: float
    reasons: list = field(default_factory=list)


class CampaignTracker:
    def __init__(self, scoreable: dict[str, bool], watch: float = 0.2, flag: float = 0.5, taint: float = 0.8,
                 victim_link_h: float = 48.0, solo_risk: float = 0.85, solo_min_victims: int = 3,
                 min_shared_victims: int = 0, solo_min_hits: int = 3):
        self.scoreable = scoreable
        self.watch, self.flag, self.taint = watch, flag, taint
        self.solo_risk, self.solo_min_victims = solo_risk, solo_min_victims
        self.min_shared = min_shared_victims
        self.solo_min_hits = solo_min_hits
        self.flag_hits: dict[str, int] = defaultdict(int)  # credits that scored >= flag, per account
        self.pair_victims: dict[tuple, set] = defaultdict(set)  # (a, b) -> payers seen paying both within the window
        self.root_victims: dict[str, set] = {}                  # root -> distinct outside payers feeding the component
        self.flagged_n: dict[str, int] = defaultdict(int)  # root -> number of flagged accounts in the component
        self.victim_link = victim_link_h * H
        self.risk: dict[str, float] = {}
        self.reasons: dict[str, list] = {}
        self.bal_in = defaultdict(float)
        self.bal_out = defaultdict(float)
        self.ext_in = defaultdict(float)
        self.victims: dict[str, set] = defaultdict(set)
        self.victim_log: dict[str, deque] = defaultdict(deque)
        self.last_victim_ts: dict[str, float] = {}
        self.first_credit_ts: dict[str, float] = {}
        self.payer_recent: dict[str, deque] = defaultdict(deque)
        self.parent: dict[str, str] = {}
        self.member_since: dict[str, float] = {}
        self.flagged_ts: dict[str, float] = {}
        self.case_id: dict[str, str] = {}      # root -> case id
        self.case_ts: dict[str, float] = {}    # root -> opened ts
        self.novel: set[str] = set()
        self._n_cases = 0

    # ---------------------------------------------------------------- union-find
    def _find(self, a: str) -> str:
        p = self.parent
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def _add(self, a: str, ts: float) -> None:
        if a not in self.parent:
            self.parent[a] = a
            self.member_since[a] = ts
            self.root_victims[a] = set(self.victims.get(a, ()))

    def _union(self, a: str, b: str, ts: float) -> None:
        self._add(a, ts)
        self._add(b, ts)
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return
        self.parent[rb] = ra
        self.flagged_n[ra] += self.flagged_n.pop(rb, 0)
        sa, sb = self.root_victims.pop(ra, set()), self.root_victims.pop(rb, set())
        big, small = (sa, sb) if len(sa) >= len(sb) else (sb, sa)
        big |= small
        self.root_victims[ra] = big
        ca, cb = self.case_ts.pop(ra, None), self.case_ts.pop(rb, None)
        ia, ib = self.case_id.pop(ra, None), self.case_id.pop(rb, None)
        keep = [(t, i) for t, i in ((ca, ia), (cb, ib)) if t is not None]
        if keep:
            t, i = min(keep)
            self.case_ts[ra], self.case_id[ra] = t, i

    def _open_if_ready(self, a: str, ts: float) -> None:
        """Open a case for a's component once it is corroborated."""
        if a not in self.parent:
            return
        root = self._find(a)
        if root in self.case_ts:
            return
        corroborated = self.flagged_n[root] >= 2 or self.flag_hits[a] >= self.solo_min_hits
        if corroborated and len(self.root_victims.get(root, ())) >= self.solo_min_victims:
            self._n_cases += 1
            self.case_ts[root], self.case_id[root] = ts, f"CMP-{self._n_cases:04d}"

    def _flag(self, a: str, ts: float) -> None:
        if a not in self.flagged_ts:
            self.flagged_ts[a] = ts
            self._add(a, ts)
            self.flagged_n[self._find(a)] += 1

    def _raise_risk(self, a: str, r: float, why: list | None, ts: float) -> None:
        if r > self.risk.get(a, 0.0):
            self.risk[a] = float(r)
            if why:
                self.reasons[a] = why
            if r >= self.watch:
                self._add(a, ts)
            if r >= self.flag:
                self._flag(a, ts)
            self._open_if_ready(a, ts)

    # ---------------------------------------------------------------- stream
    def observe(self, ts: float, src: str, dst: str, amount: float, dst_risk: float | None = None,
                dst_reasons: list | None = None) -> None:
        sc_src, sc_dst = self.scoreable.get(src, False), self.scoreable.get(dst, False)
        if sc_src:
            self.bal_out[src] += amount
        if sc_dst:
            self.bal_in[dst] += amount
            self.first_credit_ts.setdefault(dst, ts)
            if not sc_src:  # money from a payer: a potential victim
                self.ext_in[dst] += amount
                self.victims[dst].add(src)
                if dst in self.parent:
                    self.root_victims[self._find(dst)].add(src)
                self.last_victim_ts[dst] = ts
                self.victim_log[dst].append((ts, amount, src))
            if dst_risk is not None:
                if dst_risk >= self.flag:
                    self.flag_hits[dst] += 1
                self._raise_risk(dst, dst_risk, dst_reasons, ts)
            if sc_src and self.risk.get(src, 0.0) >= self.flag:  # taint flows downstream along the money
                self._raise_risk(dst, self.taint * self.risk[src], ["receives money forwarded from a flagged account"], ts)
                self._union(src, dst, ts)
                self._open_if_ready(dst, ts)
            elif not sc_src:
                self._open_if_ready(dst, ts)
            if self.min_shared and not sc_src and self.risk.get(dst, 0.0) >= self.solo_risk:  # two strongly risky accounts paid by the same victim
                dq = self.payer_recent[src]
                while dq and ts - dq[0][0] > self.victim_link:
                    dq.popleft()
                for _, other in dq:
                    if other != dst and self.risk.get(other, 0.0) >= self.solo_risk:
                        key = (min(other, dst), max(other, dst))
                        self.pair_victims[key].add(src)  # one coincidental payer must not merge two campaigns
                        if len(self.pair_victims[key]) >= self.min_shared:
                            self._union(other, dst, ts)
                            self._open_if_ready(dst, ts)
                dq.append((ts, dst))

    def mark_novel(self, accounts) -> None:
        self.novel.update(accounts)

    # ---------------------------------------------------------------- views
    def _components(self) -> dict[str, list[str]]:
        comp = defaultdict(list)
        for a in self.parent:
            if self.risk.get(a, 0.0) >= self.watch:
                comp[self._find(a)].append(a)
        return comp

    def in_case(self, a: str) -> bool:
        return a in self.parent and self._find(a) in self.case_ts

    def watchlist(self) -> list[str]:
        """Flagged accounts that are not (yet) part of a corroborated case."""
        return [a for a in self.flagged_ts if not self.in_case(a)]

    def cases(self, now: float, top: int | None = None) -> list[Case]:
        out = []
        for root, members in self._components().items():
            if root not in self.case_ts:
                continue
            victims = set().union(*(self.victims[a] for a in members))
            inflow24, v24 = 0.0, set()
            for a in members:
                log = self.victim_log[a]
                while log and log[0][0] < now - D:
                    log.popleft()
                inflow24 += sum(x[1] for x in log)
                v24.update(x[2] for x in log)
            recoverable = sum(max(0.0, self.bal_in[a] - self.bal_out[a]) for a in members)
            last_v = max((self.last_victim_ts[a] for a in members if a in self.last_victim_ts), default=None)
            risks = sorted((self.risk[a] for a in members), reverse=True)
            risk = float(np.mean(risks[:3]))
            stale_h = (now - last_v) / H if last_v is not None else 72.0
            novel = any(a in self.novel for a in members)
            priority = risk * (recoverable + inflow24) * math.exp(-stale_h / 12.0) * (1.5 if novel else 1.0)
            why = Counter()
            for a in members:
                for r in self.reasons.get(a, []):
                    why[r if isinstance(r, str) else r[0]] += self.risk[a]
            out.append(Case(
                case_id=self.case_id[root], opened_ts=self.case_ts[root],
                accounts=sorted(members, key=lambda a: -self.risk[a]),
                n_flagged=int(sum(self.risk[a] >= self.flag for a in members)), n_victims=len(victims), victims_24h=len(v24),
                loss_in=float(sum(self.ext_in[a] for a in members)), recoverable=float(recoverable), inflow_24h=float(inflow24),
                last_victim_ts=None if last_v is None else float(last_v), risk=risk, novel=bool(novel), priority=float(priority),
                reasons=[r for r, _ in why.most_common(3)]))
        out.sort(key=lambda c: -c.priority)
        return out[:top] if top else out
