"""Causal point-in-time account features, streamed over a time-ordered transfer ledger.

For a credit into account `a` at time t the features use only transfers strictly before t plus the
current credit's own amount / payer (what the beneficiary bank knows when the credit arrives, and what
a payer-side query knows when it asks "how risky is this payee for ₹X?"). The same `FeatureEngine`
code is used for training, evaluation and the serving backend, so there is no train/serve skew.

What the receiving side can legitimately see per account: age, KYC/merchant flag, credits (payer, amount,
originating bank), its own debits, and timing. It cannot see anything on the payer's phone.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

H = 3600.0
D = 86400.0
NO_DWELL_MIN = 2880.0  # sentinel: no completed pass-through observed yet
AGE_CAP_DAYS = 365.0   # older accounts are all 'established'; an exact age would let the model memorise accounts

FEATURES = [
    "log_age_days", "is_merchant_vpa", "log_idle_days",
    "log_n_cr_1h", "log_n_cr_24h", "log_payers_1h", "log_payers_24h", "new_payer_share_24h", "n_src_banks_24h",
    "log_in_sum_24h", "log_cr_median_24h", "round_share_24h",
    "cur_log_amt", "cur_amt_vs_hist", "cur_new_payer",
    "out_ratio_1h", "out_ratio_24h", "out_fanout_24h", "log_median_dwell_min", "has_dwell",
    "reciprocal_share_24h", "log_life_credits", "log_life_payers", "log_hours_since_first_cr",
    # emerging-pattern signals: fixed-fee fronts, fake payouts, payers being bounced between new accounts
    "amount_mode_share_24h", "amount_cv_24h", "payback_share_24h", "payer_multi_new_share_24h",
]
CUR = ["cur_log_amt", "cur_amt_vs_hist", "cur_new_payer"]          # only defined for a credit being scored
LIFETIME = ["log_life_credits", "log_life_payers", "log_hours_since_first_cr"]  # grow with elapsed time
RADAR_FEATURES = [f for f in FEATURES if f not in CUR and f not in LIFETIME]  # stationary account-state view
# The ledger starts empty, so every account looks brand new at day 0 and lifetime counters grow with elapsed time:
# they encode "when" rather than "what". The supervised model leaves them out; they stay in FEATURES for inspection.
MODEL_FEATURES = [f for f in FEATURES if f not in LIFETIME]

# +1: a higher value is riskier; -1: a lower value is riskier. Used to keep reason codes on the risky side.
DIRECTION = {
    "log_age_days": -1, "is_merchant_vpa": 0, "log_idle_days": 1, "log_n_cr_1h": 1, "log_n_cr_24h": 1,
    "log_payers_1h": 1, "log_payers_24h": 1, "new_payer_share_24h": 1, "n_src_banks_24h": 1, "log_in_sum_24h": 1,
    "log_cr_median_24h": 1, "round_share_24h": 1, "cur_log_amt": 1, "cur_amt_vs_hist": 1, "cur_new_payer": 1,
    "out_ratio_1h": 1, "out_ratio_24h": 1, "out_fanout_24h": 1, "log_median_dwell_min": -1, "has_dwell": 0,
    "reciprocal_share_24h": 1, "log_life_credits": 0, "log_life_payers": 0, "log_hours_since_first_cr": 0,
    "amount_mode_share_24h": 1, "amount_cv_24h": -1, "payback_share_24h": 1, "payer_multi_new_share_24h": 1,
}
REASON_TEXT = {
    "log_age_days": "very new account",
    "log_idle_days": "account was dormant and has just become active",
    "log_n_cr_1h": "many credits in the last hour",
    "log_n_cr_24h": "many credits in the last 24 hours",
    "log_payers_1h": "many different people paid this account within the hour",
    "log_payers_24h": "many different people paid this account today",
    "new_payer_share_24h": "almost every payer is paying this account for the first time",
    "n_src_banks_24h": "money arrives from many different banks",
    "log_in_sum_24h": "large total received in 24 hours",
    "log_cr_median_24h": "unusually large typical credit",
    "round_share_24h": "payments are round-number amounts",
    "cur_log_amt": "this payment is large",
    "cur_amt_vs_hist": "this payment is far larger than the account's usual credits",
    "cur_new_payer": "first payment from this payer",
    "out_ratio_1h": "most received money was sent onward within the hour",
    "out_ratio_24h": "most received money was sent onward within a day",
    "out_fanout_24h": "money is split across many accounts",
    "log_median_dwell_min": "money stays only minutes before moving on",
    "reciprocal_share_24h": "money is sent out and returned in matching amounts",
    "amount_mode_share_24h": "payments are the same few fixed amounts",
    "amount_cv_24h": "payments are unusually uniform in size",
    "payback_share_24h": "small payouts are sent back to the people who paid in",
    "payer_multi_new_share_24h": "its payers are also paying other new accounts",
}
PAYBACK_WINDOW = 3 * D   # a debit counts as a payback if its recipient paid this account in the 72 h before
MULTI_NEW_WINDOW = 3 * D  # a payer counts as 'bounced' if it paid another account for the first time in the last 72 h
MIN_CR_FOR_SHAPE = 3      # amount-shape features need a few credits; below that they take their neutral value


@dataclass
class AccountMeta:
    age_days: float
    is_merchant_vpa: bool
    scoreable: bool = True


@dataclass
class AccountState:
    cr: deque = field(default_factory=deque)            # (ts, amount, src, bank, new_payer) credits in the last 24h
    out: deque = field(default_factory=deque)           # (ts, amount, dst, is_payback) debits in the last 24h
    payers: set = field(default_factory=set)
    paid_by: dict = field(default_factory=dict)         # payer -> ts of its latest credit into this account
    hist: deque = field(default_factory=lambda: deque(maxlen=50))
    unmatched: deque = field(default_factory=deque)     # FIFO [ts, remaining] credits awaiting a debit (dwell)
    dwells: deque = field(default_factory=lambda: deque(maxlen=20))
    out_by_dst: dict = field(default_factory=dict)      # dst -> deque((ts, amount)) recent debits (reciprocity)
    recip: deque = field(default_factory=deque)         # ts of reciprocal credits in the last 24h
    life_credits: int = 0
    first_cr: float | None = None
    last_ts: float | None = None


class FeatureEngine:
    """Streaming account state. Call `features()` *before* `on_transfer()` for the same transfer."""

    def __init__(self, accounts: pd.DataFrame | dict[str, AccountMeta]):
        if isinstance(accounts, pd.DataFrame):
            accounts = {r.account: AccountMeta(float(r.age_days), bool(r.is_merchant_vpa), bool(r.scoreable))
                        for r in accounts.itertuples(index=False)}
        self.meta: dict[str, AccountMeta] = accounts
        self.state: dict[str, AccountState] = {}
        # cross-account index: payer -> recent first-time payments (ts, payee) into scoreable accounts
        self.first_pays: dict[str, deque] = {}

    # ------------------------------------------------------------------ state updates
    def _st(self, a: str) -> AccountState:
        s = self.state.get(a)
        if s is None:
            s = self.state[a] = AccountState()
        return s

    @staticmethod
    def _prune(s: AccountState, now: float) -> None:
        lo = now - D
        while s.cr and s.cr[0][0] < lo:
            s.cr.popleft()
        while s.out and s.out[0][0] < lo:
            s.out.popleft()
        while s.recip and s.recip[0] < lo:
            s.recip.popleft()

    def on_transfer(self, ts: float, src: str, dst: str, amount: float, src_bank: int = 0) -> None:
        ms, md = self.meta.get(src), self.meta.get(dst)
        if ms is not None and ms.scoreable:
            s = self._st(src)
            back = s.paid_by.get(dst)
            s.out.append((ts, amount, dst, back is not None and ts - back <= PAYBACK_WINDOW))
            s.out_by_dst.setdefault(dst, deque(maxlen=4)).append((ts, amount))
            rem = amount
            while rem > 1e-9 and s.unmatched:
                head = s.unmatched[0]
                take = min(rem, head[1])
                s.dwells.append((ts - head[0]) / 60.0)
                head[1] -= take
                rem -= take
                if head[1] <= 1e-9:
                    s.unmatched.popleft()
            s.last_ts = ts
        if md is not None and md.scoreable:
            s = self._st(dst)
            new_payer = src not in s.payers
            recent = s.out_by_dst.get(src)
            if recent and any(ts - t <= 2 * D and abs(amount - a) <= 0.06 * a for t, a in recent):
                s.recip.append(ts)
            s.cr.append((ts, amount, src, src_bank, new_payer))
            s.payers.add(src)
            s.paid_by[src] = ts
            if new_payer:
                q = self.first_pays.setdefault(src, deque(maxlen=16))
                q.append((ts, dst))
            s.hist.append(amount)
            s.unmatched.append([ts, amount])
            s.life_credits += 1
            if s.first_cr is None:
                s.first_cr = ts
            s.last_ts = ts

    # ------------------------------------------------------------------ feature extraction
    def features(self, account: str, now: float, cur_src: str | None = None, cur_amount: float | None = None) -> np.ndarray:
        meta = self.meta.get(account)
        s = self._st(account)
        self._prune(s, now)
        age = min(AGE_CAP_DAYS, (meta.age_days if meta else 1.0) + (now / D if now > 0 else 0.0))
        cr1 = [c for c in s.cr if c[0] >= now - H]
        n24 = len(s.cr)
        payers24 = {c[2] for c in s.cr}
        in24 = sum(c[1] for c in s.cr)
        in1 = sum(c[1] for c in cr1)
        out24 = sum(o[1] for o in s.out)
        out1 = sum(o[1] for o in s.out if o[0] >= now - H)
        amts = [c[1] for c in s.cr]
        med_dwell = float(np.median(s.dwells)) if s.dwells else NO_DWELL_MIN
        cur_amt_vs = cur_log = cur_new = np.nan
        if cur_amount is not None:
            cur_log = np.log1p(cur_amount)
            cur_amt_vs = np.log((cur_amount + 1.0) / (float(np.median(s.hist)) + 1.0)) if s.hist else 0.0
            cur_new = float(cur_src not in s.payers)
        idle = np.log1p((now - s.last_ts) / D) if s.last_ts is not None else np.nan
        mode_share, cv = 0.0, 1.0
        if n24 >= MIN_CR_FOR_SHAPE:
            counts = pd.Series(np.round(amts)).value_counts()
            mode_share = float(counts.iloc[:3].sum() / n24)
            mean = float(np.mean(amts))
            cv = float(np.std(amts) / mean) if mean > 0 else 1.0
        payback = (sum(1 for o in s.out if o[3]) / len(s.out)) if s.out else 0.0
        bounced = 0
        for p in payers24:
            q = self.first_pays.get(p)
            if q and any(d != account and now - MULTI_NEW_WINDOW <= t < now for t, d in q):
                bounced += 1
        multi_new = bounced / len(payers24) if payers24 else 0.0
        return np.array([
            np.log1p(age), float(bool(meta.is_merchant_vpa)) if meta else 0.0, idle,
            np.log1p(len(cr1)), np.log1p(n24), np.log1p(len({c[2] for c in cr1})), np.log1p(len(payers24)),
            (sum(c[4] for c in s.cr) / n24) if n24 else 0.0, len({c[3] for c in s.cr}),
            np.log1p(in24), np.log1p(float(np.median(amts))) if amts else 0.0,
            (sum(1 for a in amts if a >= 1000 and a % 500 == 0) / n24) if n24 else 0.0,
            cur_log, cur_amt_vs, cur_new,
            min(3.0, out1 / in1) if in1 > 0 else 0.0, min(3.0, out24 / in24) if in24 > 0 else 0.0,
            len({o[2] for o in s.out}), np.log1p(med_dwell), float(bool(s.dwells)),
            (len(s.recip) / n24) if n24 else 0.0, np.log1p(s.life_credits), np.log1p(len(s.payers)),
            np.log1p((now - s.first_cr) / H) if s.first_cr is not None else 0.0,
            mode_share, min(cv, 3.0), payback, multi_new,
        ], dtype="float64")


@dataclass
class StreamResult:
    credit: pd.DataFrame     # one row per transfer whose dst is scoreable: features at credit time
    src_snap: pd.DataFrame   # one row per 'credit_in' transfer whose src is scoreable: src account state before the debit
    snapshots: pd.DataFrame  # periodic account-state snapshots (tick_ts, account, features) for the radar


def stream_features(transfers: pd.DataFrame, accounts: pd.DataFrame, tick_hours: float | None = None,
                    snapshot_kinds_exclude: tuple = ()) -> StreamResult:
    """Replay a time-sorted ledger once. `credit` is indexed by the transfer's row index."""
    eng = FeatureEngine(accounts)
    ts = transfers["ts_s"].to_numpy()
    src = transfers["src"].to_numpy()
    dst = transfers["dst"].to_numpy()
    amt = transfers["amount"].to_numpy()
    bank = transfers["src_bank"].to_numpy()
    kind = transfers["kind"].to_numpy()
    scoreable = {a: m.scoreable for a, m in eng.meta.items()}
    credit_idx, credit_rows, src_idx, src_rows, snaps = [], [], [], [], []
    active: dict[str, float] = {}
    tick = tick_hours * H if tick_hours else None
    next_tick = tick
    for i in range(len(ts)):
        t = float(ts[i])
        if tick is not None:
            while next_tick is not None and t >= next_tick:
                lo = next_tick - D
                for a in [a for a, lt in active.items() if lt < lo]:
                    del active[a]
                for a in active:
                    snaps.append((next_tick, a, eng.features(a, next_tick)))
                next_tick += tick
        d, s_ = dst[i], src[i]
        if scoreable.get(d):
            credit_idx.append(i)
            credit_rows.append(eng.features(d, t, s_, float(amt[i])))
        if kind[i] == "credit_in" and scoreable.get(s_):
            src_idx.append(i)
            src_rows.append(eng.features(s_, t))
        eng.on_transfer(t, s_, d, float(amt[i]), int(bank[i]))
        if scoreable.get(d):
            active[d] = t
    credit = pd.DataFrame(credit_rows, columns=FEATURES, index=credit_idx)
    src_snap = pd.DataFrame(src_rows, columns=FEATURES, index=src_idx)
    if snaps:
        snap = pd.DataFrame(np.vstack([r[2] for r in snaps]), columns=FEATURES)
        snap.insert(0, "account", [r[1] for r in snaps])
        snap.insert(0, "ts_s", [r[0] for r in snaps])
    else:
        snap = pd.DataFrame(columns=["ts_s", "account"] + FEATURES)
    return StreamResult(credit, src_snap, snap)
