# Payee-side campaign layer: synthetic ledger results

> **Read this first.** The ledger is synthetic and every behaviour (mule speed, benign look-alikes, the novel scam) is an assumption we wrote. These numbers test that the pipeline works end to end and that its failure modes are visible; they are not real-world accuracy. Probabilities are at the ledger's mule prevalence, not at real-world prevalence.

Setup: 10,000 simulated sessions -> 344,065 transfers, 16,132 accounts; time split train < day 60 <= valid < day 75 <= test; flag 0.992, watch 0.496.

## 1. Payee-risk model (test period, days 75-90)

| slice | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |
|---|---|---|---|---|---|
| all credits | 9800 | 29526 | 0.8182 | 0.7428 | 0.6419 |
| cold start (first credit to the account) | 30 | 356 | 0.4585 | 0.3241 | 0.3 |
| warm (>= 3 prior credits) | 9690 | 29005 | 0.8211 | 0.7443 | 0.6494 |
| accounts never seen in training (excl. novel) | 12 | 1352 | 0.9514 | 0.7286 | 0.75 |
| layer-2/3 mule accounts (forwarded money) | 3547 | 29526 | 0.9999 | 0.9988 | 0.9994 |
| excluding the novel campaign | 6185 | 29526 | 0.9989 | 0.9947 | 0.9769 |
| novel A: wrong-credit return scam (never trained on) | 267 | 29526 | 0.9913 | 0.7456 | 0.8989 |
| novel B: micro-fee front, merchant-like (never trained on) | 3348 | 29526 | 0.4707 | 0.1005 | 0.0027 |

Baselines on all credits:

| baseline | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |
|---|---|---|---|---|---|
| fan-in only (distinct payers 24h) | 9800 | 29526 | 0.1668 | 0.1675 | 0.0 |
| fan-in x fast pass-through | 9800 | 29526 | 0.5278 | 0.2771 | 1.0 |
| account age only | 9800 | 29526 | 0.6791 | 0.4973 | 0.2206 |

Payer-side view (3,212 payments: scam payments vs ordinary merchant/P2P payments):

| score | positives | negatives | ROC-AUC | PR-AUC | recall @ 1% FPR |
|---|---|---|---|---|---|
| honest payee model | 974 | 2238 | 0.9931 | 0.9884 | 0.9497 |
| old simulator stand-in (drawn from the label) | 974 | 2238 | 0.8642 | 0.7973 | 0.4302 |

## 2. Benign look-alikes (test period)

Flag threshold 0.9918 (chosen on out-of-fold training rows plus the validation period so that at most 2% of benign accounts of each type are ever flagged).

| account type | accounts (test) | ever flagged (test, accounts the model trained on) | credits flagged (test) | ever flagged (days 10-60, out-of-fold: accounts the model never saw) |
|---|---|---|---|---|
| merchant | 470 | 0.0% | 0.0% | 1.0% |
| personal | 504 | 0.4% | 0.384% | 0.57% |
| busy_merchant | 25 | 0.0% | 0.0% | 0.0% |
| flash_merchant | 15 | 0.0% | 0.0% | 0.0% |
| fundraiser | 2 | 0.0% | 0.0% | 0.0% |
| gig_worker | 30 | 0.0% | 0.0% | 0.0% |
| cashback_sender | 6 | 0.0% | 0.0% | 0.0% |
| marketplace | 8 | 0.0% | 0.0% | 0.0% |
| friend | 137 | 0.73% | 0.284% | 10.0% |

## 3. Campaigns and cases (whole ledger, honest scores)

- 31,984 credit-level alerts on 1,133 flagged accounts became **21 cases** (1523.0 alerts and 54.0 flagged accounts per case); 46 flagged accounts stayed on the watchlist because nothing corroborated them.
- 95.1% of mule accounts that received money ended up inside a case; 2 benign accounts were swept in; 2 cases contained no mule at all.
- Mean purity of the 19 cases that contain mules (share of accounts from the dominant ground-truth syndicate): 1.0. Syndicates split over several cases: {'S05': 3, 'S07': 2, 'NOVEL_A': 2, 'S10': 2, 'S02': 2}.

| case | accounts | victims | money in (₹) | still recoverable (₹) | risk | novel | why |
|---|---|---|---|---|---|---|---|
| CMP-0007 | 178 | 1422 | 24,717,670 | 6,906,809 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0001 | 149 | 1176 | 22,354,075 | 5,656,004 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0013 | 120 | 1112 | 14,081,094 | 4,512,759 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0017 | 84 | 699 | 12,040,774 | 3,565,964 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0012 | 104 | 885 | 14,913,902 | 4,315,735 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0010 | 97 | 892 | 10,820,229 | 3,166,530 | 1.0 | False | money stays only minutes before moving on; this payment is large; very new account |
| CMP-0002 | 62 | 471 | 8,645,409 | 2,379,701 | 1.0 | False | this payment is large; money stays only minutes before moving on; very new account |
| CMP-0099 | 10 | 187 | 1,075,698 | 1,518,827 | 1.0 | True | this payment is large; money is split across many accounts; unusually large typical credit |

## 4. How early could money have been stopped

Operating curve: the flag threshold is set so that at most this share of benign accounts (per type) is ever flagged.

| benign FP budget | flag threshold | cases | cases with mules | cases with no mule | mule accounts in cases | median hours, first victim credit to case | scam value arriving after action |
|---|---|---|---|---|---|---|---|
| 0.5% | 0.998 | 17 | 16 | 1 | 94.2% | 29.7 | 88.6% |
| 1% | 0.997 | 18 | 17 | 1 | 94.5% | 25.5 | 88.6% |
| 2% | 0.992 | 21 | 19 | 2 | 95.1% | 24.9 | 88.7% |
| 5% | 0.955 | 23 | 20 | 3 | 95.4% | 24.9 | 88.9% |

Default operating point (2%), used for sections 3 and 5:

Assumptions: the analyst acts 15 minutes after a case opens; the baseline freezes an account about 24 hours (lognormal) after its first victim credit.

| | with case-driven action | complaint-driven baseline |
|---|---|---|
| scam credit value that arrives after the account is acted on | 88.7% | 82.8% |
| victim payments that arrive after the account is acted on | 85.9% | 82.1% |

Median time from a syndicate's first victim credit to its first flagged account: 3.6 h; to its first case: 24.9 h. 12/12 syndicates had a flagged account (1 before their first victim credit), 12/12 had a case.

## 5. Emerging-pattern radar: two campaigns that never appear in training

Both start on day 78 (test period). **A** is a debit-heavy 'wrong credit, please return' scam using aged accounts, irregular amounts and slow returns. **B** is a micro-fee front that deliberately looks like a busy small merchant. We authored both, so this is a stress test, not evidence that the radar works on real scams.

| | accounts | first victim credit (h) | flagged by supervised model | supervised detect (h) | radar detect (h) | covered by radar | value after supervised action | value after radar action |
|---|---|---|---|---|---|---|---|---|
| NOVEL_A | 13 | 1884.7 | 12 | 1914.1 | None | 0 | 90.7% | None% |
| NOVEL_B | 13 | 1880.0 | 0 | None | 1908.0 | 12 | None% | 89.6% |

Anomaly score on its own (does the radar rank the novel campaigns above ordinary accounts?):

| campaign | snapshots | anomaly AUC vs benign | snapshots above the alert threshold |
|---|---|---|---|
| NOVEL_A | 487 | 0.893 | 40.9% |
| NOVEL_B | 831 | 0.983 | 44.3% |

Radar anomaly quantile 0.995, tuned on the validation period so it raises at most 2 clusters there ([{'quantile': 0.99, 'false_clusters_in_valid_15d': 8}, {'quantile': 0.995, 'false_clusters_in_valid_15d': 2}, {'quantile': 0.997, 'false_clusters_in_valid_15d': 2}, {'quantile': 0.999, 'false_clusters_in_valid_15d': 0}]). Clusters in the test period that are not novel campaigns: 2.

| cluster | first seen (h) | confirmed (h) | accounts | share that is a novel campaign | ticks | account types |
|---|---|---|---|---|---|---|
| EMG-0001 | 1844.0 | 1848.0 | 8 | 0.0 | 6 | {'marketplace': 8} |
| EMG-0002 | 1888.0 | 1908.0 | 12 | 1.0 | 13 | {'novel_scammer': 12} |
| EMG-0004 | 2012.0 | 2028.0 | 8 | 0.0 | 3 | {'marketplace': 8} |
| EMG-0006 | 2056.0 | 2060.0 | 6 | 1.0 | 2 | {'novel_scammer': 6} |
