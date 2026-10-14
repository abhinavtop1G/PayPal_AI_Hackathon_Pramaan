"""Synthetic payee-side ledger: the transfers a beneficiary bank / the UPI switch sees.

The session simulator (ml.sim) only knows what happens on the victim's phone. This module extends it with
what happens to the money afterwards, and with enough benign traffic that fan-in alone does not give a
mule away:

  * every PAYMENT_SUCCESS / CREDIT_RECEIVED of the simulator becomes a transfer (scam payments land in the
    simulator's mule accounts; mules are partitioned into syndicates)
  * mules forward received money onward through layer-2 / layer-3 accounts to cash-out sinks. Most are fast
    (minutes) but ~30% are slow (hours) and keep part of the money, so dwell time is not a clean separator
  * benign look-alikes: busy merchants, flash-sale merchants, fundraisers, rent collectors, gig workers
    (many first-time payers and/or fast pass-through, but different shape)
  * optionally one *novel* scam ("wrong credit, please return") that starts late and appears nowhere in the
    training period, to test emerging-pattern detection

All behaviours are our assumptions (documented in ml/reports/campaign.md); results validate the pipeline,
not real-world accuracy.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.sim.generate import START, WINDOW_DAYS

N_BANKS = 12
DAY = 86400.0
HOUR = 3600.0
UNSCOREABLE = {"user", "customer", "sink", "own"}  # not payees we score: payers, exchanges, own settlement accounts
END = START + pd.Timedelta(days=WINDOW_DAYS)


@dataclass
class Ledger:
    transfers: pd.DataFrame  # ts, src, dst, amount, src_bank, kind, session_id, scam_credit, campaign_truth, standin_score
    accounts: pd.DataFrame   # account, kind, is_mule, is_novel, campaign_truth, age_days, is_merchant_vpa, bank, scoreable


def _ts(seconds: np.ndarray) -> pd.DatetimeIndex:
    return START + pd.to_timedelta(np.asarray(seconds, dtype="float64"), unit="s")


def _lognormal_delay(rng, median_s: float, sigma: float, n=None):
    return rng.lognormal(np.log(median_s), sigma, n)


class _Builder:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.rows: list[pd.DataFrame] = []
        self.accounts: list[dict] = []
        self.bank: dict[str, int] = {}

    def add_account(self, account, kind, age_days, is_mule=False, is_novel=False, truth=None, merchant=False):
        b = int(self.rng.integers(N_BANKS))
        self.bank[account] = b
        self.accounts.append({
            "account": account, "kind": kind, "is_mule": bool(is_mule), "is_novel": bool(is_novel),
            "campaign_truth": truth, "age_days": float(max(1.0, age_days)), "is_merchant_vpa": bool(merchant),
            "bank": b, "scoreable": kind not in UNSCOREABLE})

    def add(self, ts_s, src, dst, amount, kind, **extra):
        """Vectorised add: ts_s seconds from START (array); src/dst scalar or array."""
        n = len(ts_s)
        if n == 0:
            return
        df = pd.DataFrame({"ts_s": np.asarray(ts_s, dtype="float64"), "src": src, "dst": dst,
                           "amount": np.asarray(amount, dtype="float64"), "kind": kind})
        for k, v in extra.items():
            df[k] = v
        self.rows.append(df)


def _mule_age(rng) -> float:
    """Half freshly opened (weeks), half rented from real people (years), as in the session simulator."""
    return float(rng.lognormal(np.log(900), 0.7) if rng.random() < 0.5 else rng.lognormal(np.log(25), 0.8))


def _round(x, step=100):
    return np.maximum(step, np.round(np.asarray(x, dtype="float64") / step) * step)


def build_ledger(events: pd.DataFrame, sessions: pd.DataFrame, users: pd.DataFrame, payees: pd.DataFrame,
                 seed: int = 13, novel: bool = True, novel_start_day: float = 78.0,
                 ambient_scale: float = 1.0) -> Ledger:
    rng = np.random.default_rng(seed)
    B = _Builder(rng)
    horizon = WINDOW_DAYS * DAY

    # ------------------------------------------------------------------ accounts from the session simulator
    benign_age = {m: payees.loc[(~payees["is_mule"]) & (payees["is_merchant_vpa"] == m), "vpa_age_days"].to_numpy() for m in (True, False)}
    for r in payees.itertuples(index=False):
        kind = "mule_l1" if r.is_mule else r.kind
        age = r.vpa_age_days
        if r.is_mule and age > 200:  # a *rented* account: indistinguishable from an ordinary one by age
            age = float(rng.choice(benign_age[bool(r.is_merchant_vpa)]))
        B.add_account(r.payee_id, kind, age, is_mule=r.is_mule, merchant=bool(r.is_merchant_vpa))
    for r in users.itertuples(index=False):
        B.add_account(r.user_id, "user", r.account_age_days)

    # ------------------------------------------------------------------ base transfers from sessions
    ev = events
    pay = ev[ev["event"] == "PAYMENT_SUCCESS"]
    pdf = pd.DataFrame({"ts_s": (pay["event_time"] - START).dt.total_seconds().to_numpy(), "src": pay["user_id"].to_numpy(),
                        "dst": pay["payee_id"].to_numpy(), "amount": pay["amount"].to_numpy(),
                        "session_id": pay["session_id"].to_numpy(), "standin_score": pay["payee_mule_score"].to_numpy()})
    mule_ids = set(payees.loc[payees["is_mule"], "payee_id"])
    kind_of = payees.set_index("payee_id")["kind"].to_dict()
    pdf["scam_credit"] = pdf["dst"].isin(mule_ids)
    pdf["kind"] = np.where(pdf["scam_credit"], "scam_payment", [("merchant" if kind_of[d] == "merchant" else "p2p") for d in pdf["dst"]])
    cred = ev[ev["event"] == "CREDIT_RECEIVED"]
    cdf = pd.DataFrame({"ts_s": (cred["event_time"] - START).dt.total_seconds().to_numpy(), "src": cred["payee_id"].to_numpy(),
                        "dst": cred["user_id"].to_numpy(), "amount": cred["amount"].to_numpy(),
                        "session_id": cred["session_id"].to_numpy(), "standin_score": cred["payee_mule_score"].to_numpy()})
    cdf["scam_credit"] = False
    cdf["kind"] = "credit_in"
    B.rows += [pdf, cdf]

    # ------------------------------------------------------------------ syndicates and forwarding chains
    l1 = np.array(sorted(mule_ids))
    synd_of = {r.payee_id: int(r.syndicate) for r in payees.itertuples(index=False) if r.is_mule}
    n_syndicates = max(synd_of.values()) + 1
    acct_df = {a["account"]: a for a in B.accounts}
    for m, s in synd_of.items():
        acct_df[m]["campaign_truth"] = f"S{s:02d}"

    n_sinks = 6
    sinks = [f"SINK_{k}" for k in range(n_sinks)]
    for k in sinks:
        B.add_account(k, "sink", 2000)
    l2, l3 = {}, {}
    for s in range(n_syndicates):
        size = int(np.sum([1 for v in synd_of.values() if v == s]))
        l2[s] = [f"L2_{s:02d}_{i:03d}" for i in range(max(4, int(0.6 * size)))]
        l3[s] = [f"L3_{s:02d}_{i:03d}" for i in range(max(3, int(0.3 * size)))]
        for a in l2[s]:
            B.add_account(a, "mule_l2", _mule_age(rng), is_mule=True, truth=f"S{s:02d}")
        for a in l3[s]:
            B.add_account(a, "mule_l3", _mule_age(rng), is_mule=True, truth=f"S{s:02d}")

    # tradecraft per mule account: fast (minutes) or slow (hours, keeps part of the money)
    speed_slow = {a["account"]: bool(rng.random() < 0.30) for a in B.accounts if a["is_mule"]}

    def delay(acct, fast_med, slow_med):
        return _lognormal_delay(rng, slow_med if speed_slow[acct] else fast_med, 0.8 if not speed_slow[acct] else 0.9)

    def frac(acct):
        return rng.uniform(0.60, 0.95) if speed_slow[acct] else rng.uniform(0.88, 1.0)

    fwd = []  # (ts_s, src, dst, amount, truth)

    def forward(rows, level):
        for ts_s, acct, amount, s in rows:
            total = amount * frac(acct)
            k = int(rng.integers(1, 4 if level == 1 else 3))
            parts = rng.dirichlet(np.ones(k)) * total
            for j, p in enumerate(parts):
                if level == 1:
                    dst = str(rng.choice(l2[s]))
                elif level == 2:
                    dst = str(rng.choice(l3[s])) if rng.random() < 0.6 else str(rng.choice(sinks))
                else:
                    dst = str(rng.choice(sinks))
                t = ts_s + (delay(acct, 360.0, 36000.0) if level == 1 else delay(acct, 1500.0, 86400.0)) * (1 + 0.3 * j) + rng.uniform(0, 60)
                if t < horizon:
                    fwd.append((t, acct, dst, float(_round(p)), f"S{s:02d}"))

    scam_in = pdf[pdf["scam_credit"]]
    rows1 = [(t, a, amt, synd_of[a]) for t, a, amt in zip(scam_in["ts_s"], scam_in["dst"], scam_in["amount"])]
    forward(rows1, 1)
    f1 = [r for r in fwd if r[2].startswith("L2_")]
    n1 = len(fwd)
    forward([(t, d, amt, int(d[3:5])) for t, _, d, amt, _ in f1], 2)
    f2 = [r for r in fwd[n1:] if r[2].startswith("L3_")]
    forward([(t, d, amt, int(d[3:5])) for t, _, d, amt, _ in f2], 3)
    if fwd:
        fd = pd.DataFrame(fwd, columns=["ts_s", "src", "dst", "amount", "campaign_truth"])
        fd["kind"] = "forward"
        B.rows.append(fd)

    # benign noise on about half of the layer-1 mules (rented accounts keep some ordinary use)
    user_ids = users["user_id"].to_numpy()
    for m in l1:
        if rng.random() < 0.5:
            n = rng.poisson(3.0 * WINDOW_DAYS / 7)
            B.add(rng.uniform(0, horizon, n), rng.choice(user_ids, n), m, _round(rng.lognormal(np.log(400), 0.8, n), 50),
                  "noise", session_id=None, scam_credit=False)

    # ------------------------------------------------------------------ benign ambient traffic
    n_pool = int(4000 * ambient_scale)
    pool = np.array([f"C{i:06d}" for i in range(n_pool)])
    for c in pool:
        B.add_account(c, "customer", 500)

    def own(account):
        B.add_account(account, "own", 1500)
        return account

    def payers(n, loyal=None, p_loyal=0.0):
        if loyal is not None and p_loyal > 0:
            use = rng.random(n) < p_loyal
            return np.where(use, rng.choice(loyal, n), rng.choice(pool, n))
        return rng.choice(pool, n)

    days = np.arange(WINDOW_DAYS)
    for i in range(int(25 * ambient_scale)):  # busy merchants: steady high fan-in, daily settlement
        a = f"BM_{i:02d}"
        B.add_account(a, "busy_merchant", rng.lognormal(np.log(1200), 0.5), merchant=True)
        loyal = rng.choice(pool, 150, replace=False)
        rate = 40 * rng.uniform(0.7, 1.3)
        n_day = rng.poisson(rate, WINDOW_DAYS)
        ts = np.concatenate([d * DAY + rng.uniform(8 * HOUR, 22 * HOUR, n) for d, n in zip(days, n_day)])
        amt = _round(rng.lognormal(np.log(250), 0.7, len(ts)), 10)
        B.add(ts, payers(len(ts), loyal, 0.55), a, amt, "ambient", session_id=None, scam_credit=False)
        sett = own(f"SET_{a}")
        daily = pd.Series(amt).groupby((ts // DAY).astype(int)).sum()
        B.add(daily.index.to_numpy() * DAY + 23.5 * HOUR, a, sett, _round(0.97 * daily.to_numpy(), 10), "settlement",
              session_id=None, scam_credit=False)
    for i in range(int(15 * ambient_scale)):  # flash-sale merchants: new shop, one burst of first-time payers
        a = f"FM_{i:02d}"
        B.add_account(a, "flash_merchant", rng.uniform(20, 150), merchant=True)
        d0 = int(rng.integers(5, WINDOW_DAYS - 2))
        n = int(rng.integers(120, 300))
        ts = d0 * DAY + rng.uniform(12 * HOUR, 15 * HOUR, n)
        amt = _round(rng.lognormal(np.log(300), 0.5, n), 10)
        B.add(ts, payers(n), a, amt, "ambient", session_id=None, scam_credit=False)
        trickle = rng.poisson(5, WINDOW_DAYS)
        tt = np.concatenate([d * DAY + rng.uniform(9 * HOUR, 21 * HOUR, k) for d, k in zip(days, trickle)])
        B.add(tt, payers(len(tt)), a, _round(rng.lognormal(np.log(200), 0.6, len(tt)), 10), "ambient", session_id=None, scam_credit=False)
        B.add([(d0 + 1) * DAY + 9.5 * HOUR], a, own(f"SET_{a}"), [_round(0.98 * amt.sum(), 10)], "settlement", session_id=None, scam_credit=False)
    for i in range(int(10 * ambient_scale)):  # fundraisers: many small round donations over two days, lump-sum out
        a = f"FR_{i:02d}"
        B.add_account(a, "fundraiser", rng.uniform(30, 600))
        d0 = float(rng.uniform(3, WINDOW_DAYS - 6))
        n = int(rng.integers(300, 800))
        ts = d0 * DAY + rng.uniform(0, 2 * DAY, n)
        amt = rng.choice([100, 200, 500, 501, 1000, 1100], n, p=[0.3, 0.2, 0.25, 0.05, 0.15, 0.05]).astype(float)
        B.add(ts, payers(n), a, amt, "ambient", session_id=None, scam_credit=False)
        out = own(f"OWN_{a}")
        k = int(rng.integers(1, 3))
        B.add(d0 * DAY + 2 * DAY + rng.uniform(0.5, 1.5, k) * DAY, a, out, _round(0.97 * amt.sum() / k, 100), "settlement",
              session_id=None, scam_credit=False)
    for i in range(int(60 * ambient_scale)):  # rent collectors: a few roommates pay, sum forwarded to the landlord within hours
        a = f"RC_{i:02d}"
        B.add_account(a, "rent_collector", rng.lognormal(np.log(900), 0.7))
        mates = rng.choice(pool, int(rng.integers(3, 6)), replace=False)
        landlord = own(f"LL_{a}")
        for m in range(3):
            t0 = (m * 30 + rng.integers(1, 6)) * DAY + rng.uniform(9 * HOUR, 18 * HOUR)
            amt = _round(rng.uniform(3000, 9000, len(mates)), 500)
            B.add(t0 + rng.uniform(0, 2 * HOUR, len(mates)), mates, a, amt, "ambient", session_id=None, scam_credit=False)
            B.add([t0 + 2 * HOUR + rng.uniform(20, 150) * 60], a, landlord, [amt.sum()], "settlement", session_id=None, scam_credit=False)
    for i in range(int(30 * ambient_scale)):  # gig workers: many first-time payers a day, weekly sweep
        a = f"GW_{i:02d}"
        B.add_account(a, "gig_worker", rng.lognormal(np.log(500), 0.6))
        n_day = rng.poisson(14, WINDOW_DAYS)
        ts = np.concatenate([d * DAY + rng.uniform(7 * HOUR, 23 * HOUR, n) for d, n in zip(days, n_day)])
        amt = _round(rng.lognormal(np.log(120), 0.6, len(ts)), 10)
        B.add(ts, payers(len(ts)), a, amt, "ambient", session_id=None, scam_credit=False)
        wk = pd.Series(amt).groupby((ts // (7 * DAY)).astype(int)).sum()
        B.add(wk.index.to_numpy() * 7 * DAY + 6.9 * DAY + 20 * HOUR, a, own(f"SWEEP_{a}"), _round(0.95 * wk.to_numpy(), 10), "settlement",
              session_id=None, scam_credit=False)

    # debit-heavy and reciprocal benign accounts: without them "sends money to many accounts" would itself be a mule signal
    for i in range(int(10 * ambient_scale)):  # payroll: one big funding credit, then a run of salary transfers
        a = f"PR_{i:02d}"
        B.add_account(a, "payroll", rng.lognormal(np.log(1500), 0.5), merchant=True)
        funder = own(f"FUND_{a}")
        for m in range(3):
            t0 = (m * 30 + 1) * DAY + rng.uniform(9, 11) * HOUR
            k = int(rng.integers(40, 120))
            amt = _round(rng.uniform(15000, 80000, k), 500)
            B.add([t0 - 3 * HOUR], funder, a, [amt.sum()], "settlement", session_id=None, scam_credit=False)
            B.add(t0 + rng.uniform(0, 40 * 60, k), a, rng.choice(pool, k, replace=False), amt, "ambient", session_id=None, scam_credit=False)
    for i in range(int(6 * ambient_scale)):  # cashback senders: hundreds of tiny debits a day, topped up weekly
        a = f"CB_{i:02d}"
        B.add_account(a, "cashback_sender", rng.lognormal(np.log(1000), 0.5), merchant=True)
        funder = own(f"FUND_{a}")
        n_day = rng.poisson(150, WINDOW_DAYS)
        ts = np.concatenate([d * DAY + rng.uniform(8 * HOUR, 22 * HOUR, n) for d, n in zip(days, n_day)])
        amt = rng.choice([5, 10, 20, 25, 50], len(ts)).astype(float)
        B.add(ts, a, rng.choice(pool, len(ts)), amt, "ambient", session_id=None, scam_credit=False)
        wk = pd.Series(amt).groupby((ts // (7 * DAY)).astype(int)).sum()
        B.add(wk.index.to_numpy() * 7 * DAY - 2 * HOUR + 7 * HOUR, funder, a, _round(1.05 * wk.to_numpy(), 100), "settlement",
              session_id=None, scam_credit=False)
    for i in range(int(8 * ambient_scale)):  # marketplaces: customers pay all week, sellers are paid out once a week
        a = f"MP_{i:02d}"
        B.add_account(a, "marketplace", rng.lognormal(np.log(1200), 0.5), merchant=True)
        sellers = rng.choice(pool, 40, replace=False)
        n_day = rng.poisson(30, WINDOW_DAYS)
        ts = np.concatenate([d * DAY + rng.uniform(8 * HOUR, 22 * HOUR, n) for d, n in zip(days, n_day)])
        amt = _round(rng.lognormal(np.log(600), 0.7, len(ts)), 10)
        B.add(ts, payers(len(ts)), a, amt, "ambient", session_id=None, scam_credit=False)
        wk = pd.Series(amt).groupby((ts // (7 * DAY)).astype(int)).sum()
        for w, total in wk.items():
            share = rng.dirichlet(np.ones(len(sellers))) * 0.9 * total
            B.add(np.full(len(sellers), w * 7 * DAY + 6 * DAY + 18 * HOUR) + rng.uniform(0, 1800, len(sellers)), a, sellers, _round(share, 10),
                  "ambient", session_id=None, scam_credit=False)
    for i in range(int(30 * ambient_scale)):  # friend groups: bill splitting, people send money back in matching amounts
        names = [f"FG_{i:02d}_{j}" for j in range(5)]
        for nme in names:
            B.add_account(nme, "friend", rng.lognormal(np.log(900), 0.7))
        n = rng.poisson(4 * WINDOW_DAYS / 7)
        ts = rng.uniform(0, horizon, n)
        pair = np.array([rng.choice(5, 2, replace=False) for _ in range(n)]).reshape(-1, 2)
        amt = _round(rng.lognormal(np.log(600), 0.6, n), 10)
        B.add(ts, [names[x] for x in pair[:, 0]], [names[y] for y in pair[:, 1]], amt, "ambient", session_id=None, scam_credit=False)
        back = rng.random(n) < 0.4
        tb = ts[back] + _lognormal_delay(rng, 3 * 3600, 0.8, int(back.sum()))
        ok = tb < horizon
        B.add(tb[ok], [names[y] for y in pair[back, 1][ok]], [names[x] for x in pair[back, 0][ok]], amt[back][ok], "ambient",
              session_id=None, scam_credit=False)

    # ------------------------------------------------------------------ novel scam: "wrong credit, please return"
    # A genuinely new workflow *and* an adaptation to what the known mule model keys on: rented (old) accounts,
    # irregular non-round amounts, slow trickle of returns, weekly sweep. Money goes OUT first to many strangers
    # who are then talked into sending it back, so the account is debit-heavy with matching return credits.
    if novel:
        # variant A: "wrong credit, please return" (debit-heavy, aged accounts, irregular amounts, slow returns)
        scammers = [f"NA_{i:02d}" for i in range(12)]
        for a in scammers:
            B.add_account(a, "novel_scammer", rng.lognormal(np.log(800), 0.6), is_mule=True, is_novel=True, truth="NOVEL_A")
        B.add_account("NVC_A", "collector", 600, is_mule=True, is_novel=True, truth="NOVEL_A")
        for a in scammers:
            for d in range(int(novel_start_day), WINDOW_DAYS):
                if rng.random() > 0.5:
                    continue
                n = int(rng.integers(8, 20))
                ts = d * DAY + rng.uniform(9 * HOUR, 21 * HOUR, n)
                amt = np.round(rng.uniform(1500, 9500, n))                 # irregular, not round
                to = rng.choice(pool, n)
                B.add(ts, a, to, amt, "novel_send", session_id=None, scam_credit=False, campaign_truth="NOVEL_A")
                back = rng.random(n) < 0.25
                tb = ts[back] + _lognormal_delay(rng, 6 * 3600, 0.9, int(back.sum()))   # returns trickle in over hours
                ok = tb < horizon
                B.add(tb[ok], to[back][ok], a, amt[back][ok], "novel_return", session_id=None, scam_credit=True, campaign_truth="NOVEL_A")
            if rng.random() < 0.9:  # sweep to the collector every few days
                for d in range(int(novel_start_day) + 2, WINDOW_DAYS, 3):
                    B.add([d * DAY + 20 * HOUR], a, "NVC_A", [float(np.round(rng.uniform(15000, 60000)))], "novel_collect",
                          session_id=None, scam_credit=False, campaign_truth="NOVEL_A")
        # variant B: "micro registration fee" -- looks like a busy small merchant (many first-time payers, small amounts,
        # daily settlement) plus small "reward" payouts to some payers. Deliberately close to benign behaviour.
        fronts = [f"NB_{i:02d}" for i in range(12)]
        for a in fronts:
            B.add_account(a, "novel_scammer", rng.lognormal(np.log(800), 0.6), is_mule=True, is_novel=True, truth="NOVEL_B", merchant=True)
        B.add_account("NVC_B", "collector", 600, is_mule=True, is_novel=True, truth="NOVEL_B")
        for a in fronts:
            for d in range(int(novel_start_day), WINDOW_DAYS):
                if rng.random() > 0.8:
                    continue
                n = int(rng.poisson(25))
                ts = d * DAY + rng.uniform(8 * HOUR, 22 * HOUR, n)
                amt = rng.choice([99, 149, 199, 299], n).astype(float)
                who = rng.choice(pool, n)
                B.add(ts, who, a, amt, "novel_fee", session_id=None, scam_credit=True, campaign_truth="NOVEL_B")
                pay = rng.random(n) < 0.15
                tp = ts[pay] + _lognormal_delay(rng, 3 * 3600, 0.6, int(pay.sum()))
                B.add(tp, a, who[pay], _round(rng.uniform(20, 120, int(pay.sum())), 10), "novel_payout", session_id=None,
                      scam_credit=False, campaign_truth="NOVEL_B")
                B.add([d * DAY + 23.5 * HOUR], a, "NVC_B", [float(np.round(0.9 * amt.sum()))], "novel_collect", session_id=None,
                      scam_credit=False, campaign_truth="NOVEL_B")

    # ------------------------------------------------------------------ assemble
    accounts = pd.DataFrame(B.accounts)
    tr = pd.concat(B.rows, ignore_index=True)
    for c, default in [("session_id", None), ("scam_credit", False), ("campaign_truth", None), ("standin_score", np.nan)]:
        if c not in tr:
            tr[c] = default
    tr["scam_credit"] = np.where(tr["scam_credit"].isna(), False, tr["scam_credit"]).astype(bool)
    tr["ts_s"] = tr["ts_s"].astype("float64")
    tr = tr[(tr["ts_s"] >= 0) & (tr["ts_s"] < horizon)].sort_values("ts_s", kind="stable").reset_index(drop=True)
    tr["ts"] = _ts(tr["ts_s"])
    tr["src_bank"] = tr["src"].map(B.bank).fillna(0).astype(int)
    truth = accounts.set_index("account")["campaign_truth"]
    tr["campaign_truth"] = tr["campaign_truth"].where(tr["campaign_truth"].notna(), tr["dst"].map(truth))
    missing = (set(tr["src"]) | set(tr["dst"])) - set(accounts["account"])
    assert not missing, f"transfers reference unknown accounts: {sorted(missing)[:5]}"
    cols = ["ts", "ts_s", "src", "dst", "amount", "src_bank", "kind", "session_id", "scam_credit", "campaign_truth", "standin_score"]
    return Ledger(tr[cols], accounts)
