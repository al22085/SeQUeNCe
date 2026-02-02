# Topology normalization provenance (deadline scaling)

## 1) Formula used
We scale the deadline window (tau_s) by average shortest‑path distance:

```
tau_s(topology) = tau_s_base * (L_topo / L_ref)
```

- `tau_s_base` is the baseline deadline window used for the reference topology.

## 2) Definition of L_topo and L_ref
- **L_topo** = *average shortest‑path distance (km)* across **all unordered node pairs** in the topology’s distance dataset.
  - For each topology, build the weighted graph from its distance file (edge lengths in km).
  - For every node pair (i, j), compute the shortest‑path length (Dijkstra on edge lengths) and average over all pairs.
- **L_ref** is computed the same way on the **reference topology (NSFNET13)**.

This matches the values reported in `out/thesis_artifacts_v4/diagnostics/topology_normalization.md` and the normalized `tau_s` used in the topology sweep.

## 3) Constants
- `tau_s_base = 0.05` (seconds)
- `L_ref = 3360.781706 km` (NSFNET13 average shortest‑path distance)

## 4) Example values (from existing normalization log)
| Topology | L_topo (km) | scale = L_topo / L_ref | tau_s (s) |
|---|---:|---:|---:|
| NSFNET13 (reference) | 3360.781706 | 1.000000 | 0.050000 |
| TOP_0_SANET | 203.244444 | 0.060475 | 0.003024 |
| TOP_103_GEANT | 2775.749111 | 0.825924 | 0.041296 |

Source of numbers: `out/thesis_artifacts_v4/diagnostics/topology_normalization.md`.
