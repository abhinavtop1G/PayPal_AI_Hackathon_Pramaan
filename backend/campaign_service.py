"""Payee-side campaign service: payee risk for the payer's session, ledger ingestion, ranked analyst cases, holds.

Two consumers share one state:

  * the payer-side session pipeline asks "how risky is this payee for ₹X?" at payment time (`payee_risk`, read-only)
  * the analyst console reads ranked campaign cases and applies a *transaction-level* credit hold (`cases`, `hold`)

State is built from transfers the bank/switch already sees (`ingest`, or `load_demo` for the synthetic ledger).
Everything runs inside the bank's perimeter; accounts are referenced by opaque ids (hash them before they reach
this service when sharing across institutions).
"""
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from ml.campaign.campaigns import CampaignTracker
from ml.campaign.features import FEATURES, AccountMeta, FeatureEngine, stream_features
from ml.campaign.ledger import DAY
from ml.campaign.narrative import case_summary
from ml.campaign.payee_model import ART_DIR, PayeeRiskModel
from ml.sim.generate import START

DEMO_DIR = Path("data/campaign_demo")


def to_seconds(ts) -> float:
    """Seconds since the ledger origin; accepts a number (already seconds) or an ISO timestamp."""
    if isinstance(ts, (int, float)):
        return float(ts)
    return float((pd.Timestamp(ts).tz_localize(None) - START).total_seconds())


def campaign_override(action: str, fused_p: float, payee: dict | None, monitor_p: float = 0.02) -> tuple[str, str | None]:
    """Payer-side rule that turns campaign evidence into a floor on the session decision.

    * payee on an analyst credit hold      -> at least `cool_off`
    * payee inside a corroborated campaign -> at least `nudge`, but only when the session itself is non-trivially risky
    A flagged payee alone never changes a decision: one weak signal must not interrupt an innocent payment.
    """
    if not payee:
        return action, None
    rank = {"allow": 0, "monitor": 0, "nudge": 1, "cool_off": 2, "hold": 3}
    if payee.get("held") and rank[action] < 2:
        return "cool_off", "payee account is under an analyst credit hold"
    if payee.get("case_id") and fused_p >= monitor_p and rank[action] < 1:
        return "nudge", "payee belongs to an active scam campaign"
    return action, None


class CampaignService:
    def __init__(self, model_dir: Path | str = ART_DIR):
        self.model = PayeeRiskModel.load(Path(model_dir))
        meta = self.model.meta
        self.flag = float(meta.get("flag_threshold", 0.9))
        self.watch = float(meta.get("watch_threshold", self.flag / 2))
        self.lock = threading.Lock()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        with self.lock:
            # load_demo fills account metadata only when it (re)loads the ledger, so a reset must drop the ledger too;
            # otherwise the next load_demo replays transfers for accounts it no longer knows (0 tracked, no cases)
            self.ledger = None
            self.meta: dict[str, AccountMeta] = {}
            self.scoreable: dict[str, bool] = {}
            self.engine = FeatureEngine(self.meta)
            self.tracker = CampaignTracker(self.scoreable, watch=self.watch, flag=self.flag)
            self.held: dict[str, dict] = {}
            self.now = 0.0
            self._reasoned: set[str] = set()
            self._cursor = 0
            self._risk: dict[int, float] = {}

    def _ensure(self, account: str, ts: float, payee: bool, age_days: float | None = None, merchant: bool | None = None) -> None:
        if account not in self.meta:
            # age_days is the age at `ts`; store the age at the ledger origin so FeatureEngine's age(now) is right
            self.meta[account] = AccountMeta((age_days if age_days is not None else 1.0) - ts / DAY, bool(merchant), payee)
            self.scoreable[account] = payee
        elif payee and not self.scoreable.get(account):
            self.meta[account].scoreable = self.scoreable[account] = True

    def band(self, risk: float) -> str:
        return "flag" if risk >= self.flag else "watch" if risk >= self.watch else "ok"

    def _payee_info(self, account: str, risk: float, reasons: list | None = None) -> dict:
        in_case = self.tracker.in_case(account)
        cid = self.tracker.case_id.get(self.tracker._find(account)) if in_case else None
        out = {"payee_id": account, "risk": round(float(risk), 4), "band": self.band(risk), "case_id": cid,
               "held": account in self.held, "reasons": [r for r, _ in (reasons or [])]}
        if cid:
            root = self.tracker._find(account)
            members = [a for a in self.tracker.parent if self.tracker._find(a) == root]
            out["case_recoverable"] = round(sum(max(0.0, self.tracker.bal_in[a] - self.tracker.bal_out[a]) for a in members))
        return out

    # ------------------------------------------------------------------ payer-side query (read-only)
    def payee_risk(self, payee_id: str, amount: float, payer_id: str | None = None, ts=None,
                   payee_age_days: float | None = None, payee_is_merchant: bool | None = None) -> dict:
        t0 = time.perf_counter()
        with self.lock:
            now = self.now if ts is None else to_seconds(ts)
            known = payee_id in self.meta
            if not known:
                self._ensure(payee_id, now, True, payee_age_days, payee_is_merchant)
            x = self.engine.features(payee_id, now, payer_id or "?", float(amount))
            risk = float(self.model.predict(pd.DataFrame([x], columns=FEATURES))[0])
            reasons = self.model.reasons(x) if risk >= self.watch else []
            out = self._payee_info(payee_id, risk, reasons)
            out["known_account"] = known
            if not known:  # a pure query must not create state
                self.meta.pop(payee_id, None)
                self.scoreable.pop(payee_id, None)
                self.engine.state.pop(payee_id, None)
        out["latency_ms"] = round(1000 * (time.perf_counter() - t0), 2)
        return out

    # ------------------------------------------------------------------ ingestion
    def ingest(self, ts, src: str, dst: str, amount: float, src_bank: int = 0, src_is_account: bool = False,
               dst_age_days: float | None = None, dst_is_merchant: bool | None = None) -> dict:
        with self.lock:
            t = to_seconds(ts)
            self._ensure(dst, t, True, dst_age_days, dst_is_merchant)
            self._ensure(src, t, bool(src_is_account))
            x = self.engine.features(dst, t, src, float(amount))
            risk = float(self.model.predict(pd.DataFrame([x], columns=FEATURES))[0])
            why = None
            if risk >= self.flag and dst not in self._reasoned:
                self._reasoned.add(dst)
                why = self.model.reasons(x)
            self.tracker.observe(t, src, dst, float(amount), risk, why)
            self.engine.on_transfer(t, src, dst, float(amount), src_bank)
            self.now = max(self.now, t)
            return self._payee_info(dst, max(risk, self.tracker.risk.get(dst, 0.0)), why)

    # ------------------------------------------------------------------ demo ledger
    def load_demo(self, n_sessions: int = 3000, seed: int = 7, ambient_scale: float = 0.4, until_day: float = 80.0,
                  cache: Path | None = DEMO_DIR) -> dict:
        """Replay a synthetic ledger up to `until_day`. Call again with a later day to advance (a live feed)."""
        from ml.campaign.ledger import build_ledger
        from ml.campaign.pipeline import load_ledger, save_ledger
        from ml.sim.generate import generate
        t0 = time.perf_counter()
        with self.lock:
            if self.ledger is None:
                cache = Path(cache) / f"s{n_sessions}_a{ambient_scale}_seed{seed}" if cache else None  # keyed: no stale reuse
                if cache and (cache / "transfers.parquet").exists():
                    self.ledger = load_ledger(cache)
                else:
                    self.ledger = build_ledger(*generate(n_sessions, 0.2, seed), seed=13, ambient_scale=ambient_scale)
                    if cache:
                        save_ledger(self.ledger, cache)
                tr, ac = self.ledger.transfers, self.ledger.accounts
                for r in ac.itertuples(index=False):
                    self.meta[r.account] = AccountMeta(float(r.age_days), bool(r.is_merchant_vpa), bool(r.scoreable))
                    self.scoreable[r.account] = bool(r.scoreable)
                feats = stream_features(tr, ac).credit
                self._risk = dict(zip(feats.index, self.model.predict(feats)))
                self._feats = feats
            tr = self.ledger.transfers
            ts = tr["ts_s"].to_numpy()
            end = int(pd.Series(ts).searchsorted(until_day * DAY))
            src, dst, amt, bank = tr["src"].to_numpy(), tr["dst"].to_numpy(), tr["amount"].to_numpy(), tr["src_bank"].to_numpy()
            for i in range(self._cursor, end):
                r = self._risk.get(i)
                why = None
                if r is not None and r >= self.flag and dst[i] not in self._reasoned:
                    self._reasoned.add(dst[i])
                    why = self.model.reasons(self._feats.loc[i, FEATURES])
                self.tracker.observe(float(ts[i]), src[i], dst[i], float(amt[i]), r, why)
                self.engine.on_transfer(float(ts[i]), src[i], dst[i], float(amt[i]), int(bank[i]))
            n = end - self._cursor
            self._cursor = end
            self.now = float(ts[end - 1]) if end else self.now
        return {"replayed_transfers": int(n), "cursor": int(self._cursor), "now_day": round(self.now / DAY, 2),
                "accounts_flagged": len(self.tracker.flagged_ts), "cases": len(self.tracker.cases(self.now)),
                "seconds": round(time.perf_counter() - t0, 1)}

    # ------------------------------------------------------------------ analyst view
    def cases(self, top: int = 10) -> list[dict]:
        with self.lock:
            out = []
            for c in self.tracker.cases(self.now, top):
                d = asdict(c)
                d["accounts"] = c.accounts[:15]
                d["n_accounts"] = len(c.accounts)
                d["held_accounts"] = sum(a in self.held for a in c.accounts)
                d["summary"] = case_summary(c, self.now)
                out.append(d)
            return out

    def case_graph(self, case_id: str, max_victims: int = 40, max_exits: int = 8) -> dict:
        """Nodes and aggregated money-flow edges of one case, from the transfers replayed so far.

        hop 1 = accounts paid directly by outside payers (victims); hop n = reached from hop n-1 inside the case.
        Victims and exits (money leaving the case) are capped to the largest flows; totals cover all of them."""
        with self.lock:
            case = next((c for c in self.tracker.cases(self.now) if c.case_id == case_id), None)
            if case is None:
                raise KeyError(case_id)
            members = set(case.accounts)
            if self.ledger is not None:
                tr = self.ledger.transfers.iloc[: self._cursor]
                tr = tr[tr["src"].isin(members) | tr["dst"].isin(members)]
                flows = tr.groupby(["src", "dst"], sort=False)["amount"].agg(["sum", "count"]).reset_index()
            else:
                flows = pd.DataFrame(columns=["src", "dst", "sum", "count"])
            inner = flows[flows["src"].isin(members) & flows["dst"].isin(members)]
            into = flows[~flows["src"].isin(members) & flows["dst"].isin(members)]
            out = flows[flows["src"].isin(members) & ~flows["dst"].isin(members)]

            hop = {a: 1 for a in set(into["dst"])}
            frontier = set(hop)
            while frontier:
                nxt = set(inner[inner["src"].isin(frontier)]["dst"]) - set(hop)
                for a in nxt:
                    hop[a] = max(hop[s] for s in inner[inner["dst"] == a]["src"] if s in hop) + 1
                frontier = nxt
            nodes = [{"id": a, "kind": "account", "hop": hop.get(a, 1), "risk": round(float(self.tracker.risk.get(a, 0.0)), 4),
                      "flagged": a in self.tracker.flagged_ts, "held": a in self.held,
                      "balance": round(max(0.0, self.tracker.bal_in[a] - self.tracker.bal_out[a])),
                      "victims": len(self.tracker.victims[a])} for a in case.accounts]

            vic = into.groupby("src")["sum"].sum().sort_values(ascending=False)
            top_v = set(vic.index[:max_victims])
            for v in top_v:
                nodes.append({"id": v, "kind": "victim", "hop": 0, "amount": round(float(vic[v]))})
            ext = out.groupby("dst")["sum"].sum().sort_values(ascending=False)
            top_x = set(ext.index[:max_exits])
            for x in top_x:
                nodes.append({"id": x, "kind": "exit", "hop": max(hop.values(), default=1) + 1, "amount": round(float(ext[x]))})

            keep = members | top_v | top_x
            edges = [{"src": r.src, "dst": r.dst, "amount": round(float(r.sum)), "count": int(r.count)}
                     for r in flows.itertuples(index=False) if r.src in keep and r.dst in keep]
            return {"case_id": case_id, "nodes": nodes, "edges": edges,
                    "totals": {"victims": int(len(vic)), "victim_amount": round(float(vic.sum())),
                               "exits": int(len(ext)), "exit_amount": round(float(ext.sum())),
                               "inner_amount": round(float(inner["sum"].sum()))}}

    def hold(self, case_id: str, analyst: str, reason: str = "") -> dict:
        """Transaction-level credit hold on every account of the case. A human action, logged; never automatic."""
        with self.lock:
            for c in self.tracker.cases(self.now):
                if c.case_id == case_id:
                    for a in c.accounts:
                        self.held.setdefault(a, {"case_id": case_id, "analyst": analyst, "reason": reason, "ts": self.now})
                    return {"case_id": case_id, "held_accounts": len(c.accounts), "recoverable_at_hold": round(c.recoverable),
                            "analyst": analyst}
            raise KeyError(case_id)

    def release(self, accounts: list[str]) -> dict:
        with self.lock:
            n = sum(self.held.pop(a, None) is not None for a in accounts)
        return {"released": n}

    def summary(self) -> dict:
        with self.lock:
            return {"now_day": round(self.now / DAY, 2), "accounts_tracked": len(self.meta), "flagged": len(self.tracker.flagged_ts),
                    "watchlist": len(self.tracker.watchlist()), "held": len(self.held), "flag_threshold": self.flag}
