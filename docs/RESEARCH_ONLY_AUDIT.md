# Research-Only Audit (No TeX/Zip Tooling)

This repo is research-only: simulation outputs + analysis (CSV/plots, optionally a neutral markdown summary).  
No TeX generation, no bundling, no LaTeX shims, no verify/unpack utilities.

## A) Tracked file audits (no untracked files)
Use `git ls-files` to restrict audits to tracked content:
```
# Deleted tooling patterns

git ls-files | rg -n "qn_export_tier2_paper_artifacts|qn_bundle_tier2_paper_artifacts|qn_verify_tier2_paper_bundle|qn_unpack_tier2_paper_bundle|qn_validate_tier2_run" || true

git ls-files | rg -n "paper_artifacts_bundle|latex_include|tier2_paper_artifacts\.tex|ZipSlip|SHA256SUMS\.txt" || true

# Naming inventory (tracked only; neutral naming expected)

P1=pa
P2=per
PATTERN="${P1}${P2}"

git ls-files | rg -n "$PATTERN" || true
```

## B) Content audit excluding local artifacts
This searches tracked content while explicitly excluding local artifacts:
```
P1=pa
P2=per
PATTERN="${P1}${P2}"

rg -n "$PATTERN" -S --glob '!out/**' --glob '!.venv/**' . || true
```

## C) Outdir audits (optional, local artifacts only)
These do NOT indicate tracked content; they only validate local outputs:
```
for d in out/tier2_A099_researchonly_5topos out/tier2_smoke_no_paper_v4; do
  echo "=== OUTDIR: $d ==="
  test -d "$d" && echo "exists" || echo "MISSING"
  rg --files -g "*.tex" "$d" || true
  rg --files -g "*.zip" "$d" || true
 done
```

## D) Chunked pytest (CI-friendly)
Full `pytest -q` can exceed 120s. Use chunked runs:
```
pytest -q tests/network/test_qn_parallel_verify.py \
  tests/network/test_qn_select_pairs_by_sp_distance.py \
  tests/network/test_qn_select_pairs_by_sp_distance_missing.py
pytest -q tests/network/test_qn_run_topology_policy_upgrade_curves_smoke.py \
  tests/network/test_qn_run_topology_policy_upgrade_curves_preflight_smoke.py \
  tests/network/test_qn_run_topology_policy_upgrade_curves_auto_select_smoke.py
pytest -q tests/network/test_qn_run_topology_policy_upgrade_curves_no_node_filter.py \
  tests/network/test_qn_run_topology_policy_upgrade_curves_insufficient.py \
  tests/network/test_qn_tier2_pipeline_smoke.py
pytest -q tests/network/test_qn_topologybench_fetch.py \
  tests/network/test_qn_topologybench_generic_import_list_select.py \
  tests/network/test_qn_import_topologybench.py
pytest -q tests/network/test_qn_sweep_pair_tolerance_smoke.py \
  tests/network/test_qn_topology_feasibility_selection.py \
  tests/network/test_qn_generate_tier2_key_findings_smoke.py
```
