# Topology normalization (deadline scaling)
- base topology: NSFNET13
- base deadline window: tau_s_base = 0.05
- normalization formula: tau_s(topology) = tau_s_base * (avg_shortest_path_km(topology) / avg_shortest_path_km(NSFNET13))

## Average shortest-path distance (km)
- NSFNET13: 3360.781706 km (scale=1.000000)
- TOP_0_SANET: 203.244444 km (scale=0.060475)
- TOP_103_GEANT: 2775.749111 km (scale=0.825924)
