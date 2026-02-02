# eta* definition and claim scope

Definition used in the thesis artifacts (per `scripts/run_eta_threshold_batch.py`):
- **eta_equal**: the smallest eta where `mean_success_rate(EQT) >= mean_success_rate(BK)`.
- **eta_sig** (stricter): the smallest eta where `CI95_low(EQT) >= CI95_high(BK)`.
- CI is computed as `mean ± 1.96 * std / sqrt(n)` on per‑seed success rates.

Extended sweep below 0.01 (this pack):
- Added etas: 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3.
- Result: EQT mean success is **0** for all added points, while BK remains >0.
- At eta = 0.01, EQT exceeds BK (mean and CI non‑overlap).

What we can claim now:
- With tested points, **eta_equal and eta_sig fall in (0.003, 0.01]**.
- Therefore the statement **“eta* < 0.01” is supported**, but we **cannot pin it below 0.003** without additional points.
- A conservative alternative wording is: **“eta* ≤ 0.01 (tested minimum), with lower bound > 0.003 in current sweep.”**

Tested range summary:
- Base sweep: eta ∈ {0.01, 0.03, 0.05, 0.1, 0.15, 0.3, 0.5, 0.8}
- Extension: eta ∈ {1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3}
