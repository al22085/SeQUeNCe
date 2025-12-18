NSFNET distances (km)

- This file (`nsfnet_distances.csv`) is a heuristic placeholder derived from SNDlib visualization coordinates (great-circle). SNDlib states coordinates are for drawing only.
- Units: kilometers (approximate).
- Columns: `u,v,distance_km` (undirected edges).

Authoritative option:
- Use TopologyBench NSFNET13 dataset (Zenodo DOI: 10.5281/zenodo.8202773) via `data/nsfnet_distances_topologybench.csv` (generate with `scripts/qn_import_nsfnet_distances_from_topologybench.py`) and set `--distance-dataset-id topologybench_nsfnet13`.
