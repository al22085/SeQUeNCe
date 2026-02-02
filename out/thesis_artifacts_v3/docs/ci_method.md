# 95% CI method (availability / success rate)

Definition used in these artifacts:
- For each scenario and parameter setting, compute per-seed success rate:
  success_rate_seed = (# requests with served==True AND t_done<=deadline) / (requests_per_seed)
- Then compute mean and sample standard deviation across seeds.

Let n be the number of seeds (Chapter 9 baseline uses n=30; see run_config.json).

95% CI formula:
- mean ± t_{0.975, n-1} * s / sqrt(n)
  where s is the sample standard deviation of the per-seed success rates.

Why t-distribution:
- n is finite (30), so we use the t-distribution rather than a normal approximation.

Note:
- When success probabilities are very small, the normal approximation can be conservative; the t-based CI still reflects finite-n uncertainty around the sample mean.

Seed-level data (baseline eta=0.03):
- out/thesis_artifacts_v3/results/seedlevel_baseline_eta003.csv
  (BK and EQT, 30 seeds each; computed from study_upgrade_k raw data with k=0)
