# Notes on d'Avossa et al., IEEE QCE 2023 (transducer-strategy prior work)

- The paper studies **entanglement rate analysis** for a **high‑efficiency electro‑optic transducer** in quantum networks.
- It proposes a simulation methodology and evaluates how the transducer affects entanglement generation probability/rate.
- The focus is on **device‑level transduction performance and its impact on entanglement rate**, not on service‑level SLA.
- It does **not** model request arrivals, deadlines, or availability metrics across workloads.
- It does **not** compare BK/DQT/EQT service strategies under network load or SLA constraints.
- It does **not** provide network‑level admission/scheduling policies or route‑switching behavior.

## How our thesis differs (positioning)
- We evaluate **deadline‑based service availability** (served before deadline) rather than only entanglement rate.
- We compare **BK/DQT/EQT strategies** under identical workload parameters and report CIs.
- We extend SeQUeNCe with **transducer‑strategy parameter mapping (eta, p_eg)** and availability metrics.
- We analyze **offered load, deadline sweeps, topology normalization**, and policy impacts on success.
- We provide **diagnostics for upgrade‑k activation and teleportation usage**, which are outside device‑level transducer analysis.
