# Upgrade-k activation stress attempt

## Run parameters
- topology: nsfnet
- strategy: EQT
- eta: 0.03
- upgrade_k: 8
- pair_mode: fixed
- src_node: 12
- dst_node: 13
- num_requests: 200
- horizon_s: 0.05
- tau_s: 0.01
- arrival_interval_s: 0.00025

## Path vs upgraded edges
- upgraded_edges (k=8, policy=shortestpath_count): [('10', '12'), ('10', '8'), ('11', '13'), ('11', '9'), ('3', '5'), ('5', '7'), ('6', '8'), ('7', '9')]
- path edges (src=12, dst=13): [('12', '13')]
- overlap: []
- path_upgraded_fraction: 0.000

## Outcome
- Even under higher load (shorter horizon) and tighter deadline, upgraded edges do not overlap the fixed path.
- Activation remains 0 because the upgrade set is off-path for src=12→dst=13.