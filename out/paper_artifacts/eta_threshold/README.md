# Eta-threshold study (BK vs EQT)

Purpose
- Determine the smallest transducer efficiency eta where EQT becomes comparable to BK.
- Include experimental anchor point 0.30 (Sahu et al., Nat Commun 13, 1276 (2022), doi:10.1038/s41467-022-28924-2).

Sweep
- etas: [0.01, 0.03, 0.05, 0.1, 0.15, 0.3, 0.5, 0.8]
- bk_eta (BK run reused): 0.8
- measured_eta (macros): 0.3
- seeds: 0..29
- requests/seed: 200
- workers: 20

Baseline simulator args (explicit)
- topology: nsfnet
- pair_mode: fixed
- src_node: 12
- dst_node: 13
- horizon_s: 0.1
- tau_s: 5.0
- lambda_req: None
- otp_data_rate_bps: 1000
- otp_session_duration_s: 0.01
- otp_directions: 2
- distance_dataset_id: sndlib_great_circle_heuristic
- edge_distance_csv: None
- segment_length_km: 50.0
- key_bits_per_pair: 1.0

Non-saturation adjustment
- Default nsfnet endpoints (1->14) produced served=0 in diagnostics.
- Use the shortest nsfnet pair (12->13) and tau_s=5.0 to enter a non-zero regime.

Threshold definitions
- eta_equal: smallest eta where mean(EQT) >= mean(BK).
- eta_sig: smallest eta where CI_low(EQT) >= CI_high(BK).
- CI uses normal approximation and is clamped to [0,1].
- eta_equal: 0.01
- eta_sig: 0.01

Notes
- BK is run once at bk_eta and reused across all etas during aggregation.
- Eta scaling for p_eg is documented in eta_usage_note.txt.

Eta sensitivity note
- EQT mean range across eta: 0.0325..0.0325 (Δ=0.0000). Variation is tiny; likely bottleneck or p_eg floor.

Run command (example)
- .venv/bin/python scripts/run_eta_threshold_batch.py --eta 0.30 --seed-start 0 --seed-end 30 --workers 20 --requests-per-seed 200 --resume
- Diagnostics: .venv/bin/python scripts/diagnose_eta_threshold.py --raw-root out/paper_artifacts/eta_threshold/raw --outdir out/paper_artifacts/eta_threshold/diagnostics
