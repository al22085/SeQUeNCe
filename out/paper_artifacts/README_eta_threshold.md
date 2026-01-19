# Eta-threshold study (BK vs EQT)

Purpose
- Determine the smallest transducer efficiency eta where EQT becomes comparable to BK.
- Include experimental anchor points 0.087/0.15/0.30 (Sahu et al., Nat Commun 13, 1276 (2022)).

Sweep
- etas: [0.03, 0.05, 0.087, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 0.95]
- bk_eta (BK run reused): 0.8
- measured_eta (macros): 0.087
- seeds: 0..29
- requests/seed: 200
- workers: 20

Baseline simulator args (explicit)
- topology: chain
- pair_mode: fixed
- src_node: A
- dst_node: B
- horizon_s: 0.1
- tau_s: 0.05
- lambda_req: None
- otp_data_rate_bps: 1000
- otp_session_duration_s: 0.01
- otp_directions: 2
- distance_dataset_id: sndlib_great_circle_heuristic
- edge_distance_csv: None
- segment_length_km: 50.0
- key_bits_per_pair: 1.0

Diagnostic note
- Earlier non-zero availability used chain topology (A->B) with horizon_s=0.1/tau_s=0.05.
- The previous nsfnet-based eta sweep produced served=0 at all eta; this run reuses the non-zero baseline.

Threshold definitions
- eta_equal: smallest eta where mean(EQT) >= mean(BK).
- eta_sig: smallest eta where CI_low(EQT) >= CI_high(BK).
- eta_equal: 0.03
- eta_sig: 0.03

Run command (example)
- python scripts/run_eta_threshold_batch.py --eta 0.087 --seed-start 0 --seed-end 30 --workers 20 --requests-per-seed 200 --resume

Notes
- BK is run once at bk_eta and reused across all etas during aggregation.
