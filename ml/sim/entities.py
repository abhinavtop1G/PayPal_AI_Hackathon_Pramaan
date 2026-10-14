"""Users and payees that sessions are drawn from.

Payee kinds:
  merchant  - shops / billers, old VPAs, low mule score
  personal  - individuals; mostly old VPAs but ~15% genuinely new accounts (hard negatives)
  mule      - money-mule accounts; mostly fresh VPAs, ~25% "rented" old accounts.
              Reuse across victims is power-law, so a few mules receive from many sessions.

`payee_mule_score` is a *noisy observed* network-intelligence score (stand-in for what the GNN
will later produce); the ground truth is `is_mule`.

Mules belong to syndicates. A scam session draws all of its mules from one syndicate (a gang runs one
operation), so the payee graph has campaign structure; reuse inside a syndicate stays power-law.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

AGE_GROUPS = ["18-25", "26-40", "41-60", "60+"]
AGE_GROUP_P = [0.22, 0.38, 0.27, 0.13]


@dataclass
class User:
    user_id: str
    age_group: str
    account_age_days: int
    avg_txn_amount: float
    known_payees: list = field(default_factory=list)    # people the user has paid before
    known_merchants: list = field(default_factory=list)  # regular shops / billers
    bio: dict = field(default_factory=dict)  # baseline biometrics
    hmog_subject: int | None = None  # held-out HMOG subject whose real gestures stand for this customer's touches


class World:
    def __init__(self, rng: np.random.Generator, n_users: int, n_merchants: int, n_personal: int, n_mules: int,
                 n_syndicates: int = 12):
        self.rng = rng
        self.n_syndicates = n_syndicates
        self.payees = self._make_payees(n_merchants, n_personal, n_mules)
        kinds = self.payees["kind"].to_numpy()
        ids = self.payees["payee_id"].to_numpy()
        self.merchant_ids = ids[kinds == "merchant"]
        self.personal_ids = ids[kinds == "personal"]
        self.mule_ids = ids[kinds == "mule"]
        # Zipf-like reuse: mule k is picked with weight 1/k^0.6 (a few hubs, long tail)
        w = 1.0 / np.arange(1, len(self.mule_ids) + 1) ** 0.6
        self.mule_p = w / w.sum()
        self._mule_front = self.payees.set_index("payee_id").loc[self.mule_ids, "merchant_front"].to_numpy()
        self._mule_synd = self.payees.set_index("payee_id").loc[self.mule_ids, "syndicate"].to_numpy().astype(int)
        share = self._synd_share
        ids = np.unique(self._mule_synd)
        self.synd_ids = ids
        self.synd_p = share[ids] / share[ids].sum()  # bigger syndicates run more campaigns
        self._payee_rec = self.payees.set_index("payee_id").to_dict("index")
        self.users = [self._make_user(i) for i in range(n_users)]
        # real touch gestures (optional: needs the HMOG cache); assigned by index so no random draws are consumed
        from .hmog_bank import HmogBank
        self.hmog = HmogBank.load()
        if self.hmog is not None:
            for i, u in enumerate(self.users):
                u.hmog_subject = self.hmog.subject_for(i)

    # ---------- payees ----------
    def _make_payees(self, n_merchants, n_personal, n_mules) -> pd.DataFrame:
        rng = self.rng
        # Account age overlaps between classes: many legit payees/shops are new to UPI, and about half of
        # mules are aged accounts rented or recruited from real people, so VPA age alone is a weak cue.
        new_shop = rng.random(n_merchants) < 0.2
        merchant_age = np.where(new_shop, rng.uniform(5, 120, n_merchants), rng.lognormal(np.log(1500), 0.6, n_merchants))
        young = rng.random(n_personal) < 0.3
        personal_age = np.where(young, rng.uniform(1, 90, n_personal), rng.lognormal(np.log(900), 0.7, n_personal))
        rented = rng.random(n_mules) < 0.5
        mule_age = np.where(rented, rng.lognormal(np.log(700), 0.7, n_mules), rng.lognormal(np.log(15), 0.9, n_mules))

        df = pd.DataFrame({
            "payee_id": [f"M{i:05d}" for i in range(n_merchants)]
                        + [f"P{i:06d}" for i in range(n_personal)]
                        + [f"X{i:05d}" for i in range(n_mules)],
            "kind": ["merchant"] * n_merchants + ["personal"] * n_personal + ["mule"] * n_mules,
            "vpa_age_days": np.concatenate([merchant_age, personal_age, mule_age]).clip(1).round().astype(int),
            "is_mule": [False] * (n_merchants + n_personal) + [True] * n_mules,
        })
        # A quarter of mules are merchant fronts (fake shops / aggregator QR), so they look like merchants in UPI.
        df["merchant_front"] = df["is_mule"] & (rng.random(len(df)) < 0.25)
        df["is_merchant_vpa"] = (df["kind"] == "merchant") | df["merchant_front"]
        # Fresh mules are cold-start for network intel (few complaints yet) -> low scores; this gap is what the GNN closes.
        fresh_mule = df["is_mule"] & (df["vpa_age_days"] < 30)
        score = np.select(
            [fresh_mule, df["is_mule"]],
            [rng.beta(1.5, 4, len(df)), rng.beta(3, 2.5, len(df))],
            rng.beta(1.2, 8, len(df)),
        )
        df["mule_score"] = score.round(3)
        self._synd_share = rng.dirichlet(np.full(self.n_syndicates, 3.0))
        df["syndicate"] = -1
        is_mule = df["is_mule"].to_numpy()
        df.loc[is_mule, "syndicate"] = rng.choice(self.n_syndicates, int(is_mule.sum()), p=self._synd_share)
        return df

    def payee(self, payee_id: str) -> dict:
        return self._payee_rec[payee_id]

    def sample_syndicate(self) -> int:
        return int(self.rng.choice(self.synd_ids, p=self.synd_p))

    def sample_mule(self, merchant_front: bool | None = None, syndicate: int | None = None) -> str:
        """Power-law reuse; optionally restricted to merchant-front (or personal-looking) mules and to one syndicate."""
        mask = np.ones(len(self.mule_ids), dtype=bool)
        if syndicate is not None:
            mask &= self._mule_synd == syndicate
        if merchant_front is not None:
            narrowed = mask & (self._mule_front == merchant_front)
            mask = narrowed if narrowed.any() else mask
        p = self.mule_p[mask]
        return str(self.rng.choice(self.mule_ids[mask], p=p / p.sum()))

    def sample_merchant(self, user: User | None = None, p_known: float = 0.8) -> str:
        """Mostly a merchant the user already pays; sometimes a new shop."""
        if user is not None and user.known_merchants and self.rng.random() < p_known:
            return str(self.rng.choice(user.known_merchants))
        return str(self.rng.choice(self.merchant_ids))

    def sample_new_personal(self, user: User) -> str:
        while True:
            pid = str(self.rng.choice(self.personal_ids))
            if pid not in user.known_payees:
                return pid

    # ---------- users ----------
    def _make_user(self, i: int) -> User:
        rng = self.rng
        age_group = str(rng.choice(AGE_GROUPS, p=AGE_GROUP_P))
        older = age_group in ("41-60", "60+")
        bio = {
            "pressure": rng.uniform(0.35, 0.70),
            "swipe_velocity": rng.uniform(0.6, 1.6) * (0.75 if older else 1.0),
            "tap_interval_ms": rng.uniform(250, 600) * (1.3 if older else 1.0),
            "hesitation_ms": rng.uniform(800, 2500) * (1.3 if older else 1.0),
            "orientation_var": rng.uniform(0.02, 0.08),
        }
        n_known = int(rng.integers(3, 15))
        known = list(rng.choice(self.personal_ids, n_known, replace=False))
        return User(
            user_id=f"U{i:06d}",
            age_group=age_group,
            account_age_days=int(rng.integers(30, 3000)),
            avg_txn_amount=float(rng.lognormal(np.log(800), 0.7)),
            known_payees=[str(p) for p in known],
            known_merchants=[str(m) for m in rng.choice(self.merchant_ids, int(rng.integers(3, 12)), replace=False)],
            bio=bio,
        )

    def users_frame(self) -> pd.DataFrame:
        rows = []
        for u in self.users:
            rows.append({
                "user_id": u.user_id, "age_group": u.age_group, "account_age_days": u.account_age_days,
                "avg_txn_amount": round(u.avg_txn_amount, 2), "n_known_payees": len(u.known_payees),
                "n_known_merchants": len(u.known_merchants), "hmog_subject": u.hmog_subject,
                **{f"bio_{k}_baseline": round(v, 4) for k, v in u.bio.items()},
            })
        return pd.DataFrame(rows)
