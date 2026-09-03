# Supply-chain thesis: A production view framework for software supply chains

Code and data for the experiments over three package ecosystems (npm, PyPI, Maven
Central): a MeMPtec-style metadata baseline, its adversarial robustness, Noisy-OR risk
propagation over the dependency graph, Warfield ISM-MICMAC analysis, metadata-scarcity
detectors, temporal validation, and a 2026 case study.

## Layout

```
data/dataset_description.md   what every data file is: schema, row counts, producer
data/input/<eco>/      scraped & fetched inputs (single crawl, July 2026) — see the README
                       in each folder for file-by-file provenance
data/output/<eco>/     experiment artifacts, one folder per notebook
notebooks/             the experiments: 01-08, parameterised by the ECO environment
                       variable; common.py (shared helpers); run_all.py (headless runner)
scripts/data-extraction/    01-09: OSV mirror -> labeled dataset (network + BigQuery)
scripts/feature-extraction/ 09-13: registry/GitHub/stakeholder/graph features -> all_features.csv
scripts/common.py      shared helpers for both script folders
```

## Running the experiments

```
.new-venv\Scripts\python.exe notebooks\run_all.py --eco all --parallel
```

runs notebooks 01→08 per ecosystem (01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 in order; ~1 h
wall-clock with `--parallel` on 12 cores) and writes executed copies to
`data/output/<eco>/notebooks/`. However, you can slowly go through each cell in the notebook running each block until the end. 

## Data pipeline 

The extraction scripts document how `data/input/` was built and are resumable, but they
query live services (OSV mirror, npm/PyPI/Maven registries, ecosyste.ms, GitHub GraphQL,
deps.dev BigQuery via the `bq` CLI).
