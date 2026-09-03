# Dataset description

Every data file in this repository, file by file. All data comes from a **single crawl
(July 2026)**; the experiment outputs were produced by the notebooks under `notebooks/`
(seeds fixed at 42). Layout: `data/input/<eco>/` holds the scraped/fetched inputs and
`data/output/<eco>/` the experiment artifacts, for `<eco>` in `npm`, `pypi`, `maven`.

Conventions used throughout:

- **Row counts** below are data rows (header excluded), given as npm / pypi / maven.
  A `-` means the file does not exist for that ecosystem.
- **`label`** encodes the package class: `1` compromised (a verified MAL-* advisory hit a
  later release; the row is pinned to the *last clean version* before the attack),
  `-1` vulnerable (non-malware advisory; pinned to the latest release), `0` clean control
  (popular package; pinned to the latest release).
- **`status` columns** record per-row fetch outcomes explicitly (`ok`, `error`,
  `not_found`, `no_repo_url`, `not_github`, ...); downstream code filters on them rather
  than receiving silently empty features.
- **Missing values are preserved as empty fields / NaN**, never zero-filled.
- The npm registry contains packages literally named `nan` and `null` (PyPI: `null`).
  All ingestion reads CSVs with the default NA vocabulary disabled so these names survive;
  any tooling you point at these files should do the same
  (`pd.read_csv(..., keep_default_na=False, na_values=[""])`).
- Metadata feature names follow the MeMPtec encoding: `<field>_exist` is a 0/1 presence
  flag, `<field>_length` a character length (JSON-serialised length for dict/list fields;
  entry counts for Maven dependency lists), `<field>_num_count` an item count.
  `author_name`/`author_email` are presence flags, not raw strings.

---

## data/input/`<eco>`/ — scraped & fetched inputs

### Advisory and dataset files (produced by `scripts/data-extraction/`)

#### `osv_raw.zip` — full OSV advisory mirror
Produced by `01_fetch_osv.py`. One JSON file per advisory (npm 223,083 / pypi 24,266 /
maven 6,803 entries; 211 / 32 / 10 MB). Source of every label in the corpus.
Note (npm): re-running script 02 on this zip yields 6 additional candidates
(the zip snapshot is slightly newer than `malicious_all.csv`); none reach `dataset.csv`.

#### `malicious_all.csv` — MAL-* advisory candidates — 215,982 / 11,479 / 2 rows
Produced by `02_extract_mal_list.py`. One row per package named in a non-retracted
malware (MAL-*) advisory.

| column | meaning |
|---|---|
| `package` | package name (Maven: `groupId:artifactId`) |
| `affected_versions` | `;`-joined sorted union of enumerated affected versions plus non-zero `introduced` range endpoints, across advisories (empty when advisories condemn the whole package via open ranges) |
| `attack_timestamp` | earliest advisory published/modified time |

Consumed by script 03 (registry triage) and by notebooks 07/08 as the compromise-time
source (`attack_timestamp` per package).

#### `vulnerable_all.csv` — vulnerability advisories — 3,201 / 1,766 / 3,252 rows
Produced by `05_extract_vuln_list.py`. One row per package with a non-malware,
non-retracted advisory (GHSA/PYSEC/CVE...). Advisories carrying a MAL-* alias or a
"malicious code/package in ..." GHSA title are excluded (they are malware, not
vulnerabilities). Maven's file contains ~109 non-Maven names leaked from cross-ecosystem
GHSA advisories; they drop out of `dataset.csv` at the empty-version filter.

| column | meaning |
|---|---|
| `package` | package name |
| `advisory_ids` | `;`-joined advisory identifiers |
| `max_severity` | highest GHSA severity across advisories (`LOW`/`MODERATE`/`HIGH`/`CRITICAL`, may be empty) |
| `affected_versions` | `;`-joined enumerated affected versions (often empty) |
| `affected_ranges` | `;`-joined `introduced..fixed` spans (`x..` = no fix at publication, `x..=y` = last_affected endpoint) |
| `first_advisory_timestamp` | earliest advisory time — the temporal anchor notebook 07 uses for the risky view |

#### `pre_compromise_versions.csv` — last clean version per compromise — 2,385 / 75 / 1 rows
Produced by `04_find_pre_compromise_version.py` from script 03's triage (03's
intermediate `malicious_labeled.csv` is not shipped). Only `compromised_release`
packages appear — packages that still exist on the registry with at least one version
outside the affected set.

| column | meaning |
|---|---|
| `package` | package name |
| `affected_versions` | affected set carried through from `malicious_all.csv` |
| `first_affected_version` | earliest-published affected version (empty if compromise time fell back to the advisory timestamp) |
| `compromise_time` | earliest publish time among affected versions, else the advisory timestamp |
| `pre_compromise_version` | latest version published strictly before `compromise_time`, outside the affected set, still installable (ordering by publish time, not semver) |
| `pre_compromise_time` | its publish time |
| `status` | `ok` \| `no_prior_clean_version` \| `no_compromise_time` \| `registry_error` |

Status counts: npm 2,156 ok / 228 no_prior_clean_version / 1 registry_error;
pypi 62 ok / 13 no_prior_clean_version; maven 1 ok.

#### `top_packages.csv` — popularity-ranked clean controls — 100,000 / 97,257 / 100,000 rows
Produced by `07_fetch_top_packages_bq.py` (deps.dev BigQuery, latest snapshot;
popularity = count of distinct packages depending directly on the target;
`06_fetch_top_packages.py` is an unused ecosyste.ms alternative).
Columns: `rank`, `package`, `dependent_packages_count`.

#### `dataset.csv` — the labeled corpus — 101,361 / 96,879 / 95,267 rows
Produced by `08_build_dataset.py`, merging compromised (from
`pre_compromise_versions.csv`), vulnerable (from `vulnerable_all.csv`) and clean controls
(from `top_packages.csv`) with precedence compromised > vulnerable > clean; rows without
a resolvable version are dropped. Sorted by label descending, then package.
Columns: `package`, `version` (the pinned version features are extracted for), `label`.
Label counts: npm 2,156 / 2,931 / 96,274; pypi 62 / 1,485 / 95,332; maven 1 / 2,803 / 92,463.

#### `latest_versions.csv` — latest-release cache — 101,557 / 97,970 / 101,913 rows
Produced by `08_build_dataset.py` (BigQuery semver-aware latest release per package,
cached so re-runs skip the query). Columns: `package`, `version` (empty when no release
release resolved — those rows are dropped from `dataset.csv`).

#### `dependent_counts_fill.csv` — popularity backfill — 3,180 / 479 / 1,480 rows
Produced by `09_fetch_missing_dependents.py` (per-package ecosyste.ms lookups) for
dataset packages with no positive count in `top_packages.csv` — in practice compromised
and vulnerable rows, which would otherwise look like unused typosquats in any
popularity-aware analysis (many others already appear in `top_packages.csv`). Read by
notebook 01 (and 08) to build the global-dependents column.

| column | meaning |
|---|---|
| `package` | package name |
| `dependent_packages_count` | registry-wide direct dependent packages |
| `dependent_repos_count` | dependent repositories |
| `downloads_last_month` | monthly downloads (blanked when the API reports a period other than `last-month`) |
| `status` | `ok` \| `not_found` \| `error:<code>` |

### MeMPtec feature files (produced by `scripts/feature-extraction/`)

#### `features.csv` — registry metadata features — 101,361 / 96,879 / 95,267 rows
Produced by `09_extract_features.py --eco <eco>`, one row per `dataset.csv` row.
Columns: `package`, `version`, `label`, `status` (`ok`/`error`) + the ecosystem-native
MeMPtec feature set — 37 features on npm, 29 on PyPI, 25 on Maven (per-ecosystem field
sources and omissions are documented in each folder's `README.md`). The three temporal
features are shared: `package_age_days` (creation → extraction date),
`package_modified_duration_days` (creation → last modification event),
`package_published_duration_days` (creation → pinned version's publish time).
`status=ok` counts: npm 101,350 / pypi 91,044 / maven 58,550 (maven's 36,717 errors carry
a single `error` status; the extractor records no failure cause).

#### `metadata_index.csv` — raw identities — 101,350 / 91,044 / 58,550 rows
Written alongside `features.csv` for `ok` rows only; the input for scripts 10/11/12
(11 and 12 are offline; 10 queries the GitHub API — no further registry access).
Columns: `package`, `version`, `repo_url`,
`author`, `author_email`, `maintainers` (npm: registry-verified maintainer names;
PyPI: the single `info.maintainer` field; Maven: the full POM `<developers>` list),
`created` (first-release time), `dependencies` (`;`-joined declared dependency names of
the pinned version). npm adds `contributors`, `publisher`, `publisher_email` (the
account that ran `npm publish` — 11 columns vs 8 elsewhere).

#### `github_features.csv` — repository interaction — 101,350 / 91,044 / 58,550 rows
Produced by `10_extract_github_features.py --eco <eco>` (GitHub GraphQL, batched).
Columns: `package`, `repo` (`owner/name`), `star`, `fork_number`, `subscriber_count`
(watchers), `issues` (open+closed), `pull_request`, `status`
(`ok` / `no_repo_url` / `not_github` / `not_found`). Current-time counts, not as of the
pinned version; `ok` coverage npm 78,539 / pypi 27,746 / maven 29,771 — the origin of the
block-structured missingness the notebooks preserve as NaN.

#### `stakeholder_features.csv` — stakeholder history — 101,350 / 91,044 / 58,550 rows
Produced by `11_stakeholder_features.py --eco <eco>` from a within-dataset index.
Columns: `package`, `version`, then `<role>_CPN` (packages associated with the
stakeholder *within this corpus*), `<role>_service_time` (days from their earliest
package creation to the extraction date) and `<role>_CCS`
(= `log2(service_time) * log2(CPN)`, 0 when either ≤ 1) per role. Roles: npm
`author`/`maintainer`/`contributor`/`publisher` (14 columns); PyPI `author`/`maintainer`;
Maven `author`/`developer` (unverified POM `<developers>`; 8 columns).

#### `graph_edges.csv` — dependency edges — 388,416 / 541,923 / 133,019 rows
Produced by `12_dependency_graph.py --eco <eco>`. The induced dependency graph over the
corpus packages, from the pinned versions' declared dependencies: `source` depends on
`target` (both corpus package names; deduplicated, self-edges removed, sorted; PyPI names
PEP 503-normalised before matching).

#### `dependents.csv` — degree counts — 101,350 / 91,044 / 58,550 rows
Also from script 12; one row per `metadata_index.csv` row. Columns: `package`,
`dependents_in_dataset` (in-corpus in-degree), `dependencies_in_dataset` (in-corpus
out-degree), `global_dependent_packages_count` (from `top_packages.csv`, empty when the
package is not in it). The notebooks recompute degrees from `graph_edges.csv`; only the
global count is merged onward.

#### `all_features.csv` — the merged feature table — 101,361 / 96,879 / 95,267 rows
Produced by `13_merge_features.py --eco <eco>`: `features.csv` left-joined with
`stakeholder_features.csv`, `github_features.csv` (its `status` renamed
`github_status`) and `dependents.csv` on `package`. **The single entry point the
notebooks read**; filter on `status == "ok"`. 62 columns on npm, 48 on PyPI, 41 on Maven —
the Maven file carries no dependents columns; notebook 01 reads the global counts from
`top_packages.csv` instead.

### `README.md`
Per-ecosystem provenance notes: which script produced each file, ecosystem-specific
field mappings, and caveats.

---

## data/output/`<eco>`/ — experiment artifacts

Each folder `NN_*` is written by the notebook of the same number; `notebooks/` holds the
executed notebook copies (with printed outputs and the numbered verification checks).
Files named `*_<view>` exist only where the label view is usable: `compromised` variants
exist for npm and PyPI (maven has a single compromised package) and, in notebook 06,
for npm only (PyPI has no compromised level-0 manufacturers). `summary.csv` files are
two-column key/value dumps of the notebook's headline quantities; their `runtime_min`
row is machine-dependent, everything else reproduces exactly.

### 01_data_prep/ — corpus, schema, label views, structural features

- **`model_ready_dataset.csv`** — 101,350 / 91,044 / 58,550 rows. The de-duplicated,
  `status=ok` corpus: `package`, `label`, then every metadata feature coerced to numeric
  with NaN preserved (58 / 42 / 38 columns). npm adds `issueslink_exist`/`issueslink_length`
  mirrored from `bugslink_*`. The base table every later notebook loads.
- **`graph_features.csv`** — same rows. `package`, `scc_id` (strongly-connected-component
  id), `connected` (participates in ≥1 edge), then the canonical 11 structural features:
  `warfield_level` (longest dependency chain below the package), `in_degree`,
  `out_degree`, `log1p_driving_power` (log1p transitive dependents),
  `log1p_dependence_power` (log1p transitive dependencies), `scc_size`, `pagerank`,
  `hits_hub`, `hits_auth`, `clustering`, `closeness` (landmark-approximated harmonic).
- **`edges.csv`** — 388,416 / 541,923 / 133,019 rows. `graph_edges.csv` restricted to the
  final corpus, as package names (`source`, `target`).
- **`feature_audit.csv`** — one row per metadata feature (56 / 40 / 36): `feature`,
  `group` (ETM/DTM), `n_missing`, `pct_missing`, `n_unique`, `constant`, `min`, `median`,
  `max`, `description`.
- **`global_dependents.csv`** — same rows as the corpus: `package`, `global_dependents`
  (registry-wide direct dependents from `top_packages.csv` backfilled with
  `dependent_counts_fill.csv`, 0 when unknown). Deliberately kept OUT of the structural
  features; reloaded only by notebook 05 as the second impact currency (notebook 08
  recomputes the same quantity from the raw inputs).
- **`schema.json`** — the contract later notebooks assert against: ecosystem, row count,
  seed, `etm_features`/`dtm_features`/`meta_features`/`graph_features` lists (order
  matters), label view sizes/prevalence/usability, label counts, edge counts,
  missing-value policy.
- **`missingness.png`** — per-feature missingness bar chart (ETM blue / DTM orange).
- **`summary.csv`** — corpus counts, feature counts, missingness, edges, max Warfield
  level, view usability.

### 02_model_training/ — MeMPtec baseline

- **`training_results.csv`** — one row per configuration (60 / 60 / 30 = views × 2 class
  ratios × 3 feature sets × 5 models): `view`, `dataset` (balanced 1:1 / imbalanced 1:10),
  `feature_set` (`MeMPtec_E` = ETM, `MeMPtec_D` = DTM, `MeMPtec` = both), `model`
  (SVM/GLM/GBM/DRF/DL), then mean±std over 5-fold CV of precision, recall, f1, accuracy,
  rmse, roc_auc, pr_auc (positive class, threshold tuned on the validation fold),
  `f1_at_0.5` (untuned threshold) and `threshold`.
- **`view_comparison.csv`** (npm, PyPI) — F1 pivot per config with
  `delta (risky - compromised)`.
- **`best_model.json`** — best configuration per view (imbalanced variant, mean F1 then
  PR-AUC): model, feature set, F1/PR-AUC/ROC-AUC. The contract notebook 04 reads.
- **`f1_comparison.png`**, **`summary.csv`**.

### 03_adversarial_robustness/ — ETM manipulation attack

- **`adversarial_results.csv`** — 220 / 220 / 110 rows: `view`, `feature_set`
  (`MeMPtec_E`, `MeMPtec`), `model`, `pct_manipulated` (0–100 in steps of 10),
  `accuracy` on a 1:1 rebalanced test set (0.5 = coin flip). The attacker overwrites ETM
  features in the model's own SHAP order with values resampled from clean training rows;
  DTM features are never touched.
- **`degradation_summary.csv`** — per (view, model, feature set): accuracy at 0/50/100 %
  manipulated and the drops.
- **`dtm_protection.csv`** — per (view, model): accuracy at 100 % manipulation for
  ETM-only vs ETM+DTM and their difference (`DTM protection`).
- **`adversarial_<view>.png`** (5-panel figure per view), **`summary.csv`**.

### 04_noisy-or-sweep/ — risk propagation calibration

- **`alpha_sweep.csv`** — 66 / 66 / 33 rows: per `view`, transmission `variant`
  (`Unweighted`, `Weighted (dp)`, `Weighted (log dp)`) and `alpha` (0.0–1.0):
  `auroc`, `prauc` of the propagated score, `mean_level_auroc`, `n_level_buckets`,
  `n_lifted` (packages whose score rose), `mean_lift_exposed`. `alpha=0` reproduces the
  base model exactly.
- **`noninferiority.csv`** — 18 / 18 / 9 rows: paired-bootstrap (300 resamples) deltas
  vs the base model at three headline alphas per variant: ΔAUROC and ΔPR-AUC with 95 % CI
  bounds and per-metric + overall `verdict` (`superior`/`non-inferior`/`DEGRADED`; both
  margins must clear).
- **`best_alpha.json`** — per view: selected `alpha`/`variant`/`verdict`, propagated and
  base AUROC/PR-AUC, `propagation_recommended`, plus the PR-AUC-argmax fallback
  (`alpha_best_prauc`, `variant_best_prauc`) notebook 06 uses when nothing survived.
  The contract notebooks 05/06 read.
- **`base_scores.csv`** — 202,700 / 182,088 / 58,550 rows (corpus × usable views):
  `view`, `package`, `base` (out-of-fold probability from notebook 02's chosen model),
  `prop` (propagated score — at the recommended configuration where one survived, else at
  the diagnostic least-bad α>0 setting, since α=0 would simply equal `base`),
  `ancestor_risk` (inherited-risk component alone), `exposed` (clean package with ≥1
  positive transitive dependency). The ranking input for notebook 05.
- **`audit_priority.csv`** — top-50 per view: exposed clean packages
  (base < 0.05) ranked by propagation lift; adds `label`, `level_bucket`,
  `n_positive_deps`, `lift`.
- **`alpha_sweep.png`**, **`noninferiority_<view>.png`**, **`summary.csv`**.

### 05_warfield_exploration/ — ISM-MICMAC and the method comparison

- **`method_metrics.csv`** — one row per (view, ranking method); methods: Random,
  In-degree, PageRank, ISM driving power, Global dependents, REI worst-case impact,
  ML P(positive), Expected impact (in-data), Expected impact (registry), and (npm only)
  Noisy-OR propagated. Columns: ROC-AUC, PR-AUC, recall@K and precision@K for
  K ∈ {100,500,1000,2000,5000}, impact-weighted recalls `wrecall_ds@K` (weighted by
  1+driving power) and `wrecall_rw@K` (weighted by 1+registry dependents) at K ∈ {100,1000},
  and TPR at fixed FPR targets.
- **`method_metrics_per_level.csv`** — ROC-AUC per (view, Warfield level bucket, method),
  buckets with ≥5 of each class only.
- **`micmac_quadrant_composition.csv`** — per (view, quadrant ∈ Independent/Linkage/
  Dependent/Autonomous/Isolated): `n`, `n_positive`, `pct_positive`, `lift_vs_base`.
- **`warfield_level_stats.csv`** — per (view, level bucket): `n`, `n_positive`,
  `pct_positive`.
- **`cross_currency.csv`** — the circularity check: both impact-weighted recalls at
  K=1000 per method, with `optimises` marking which currency each expected-impact
  ranking multiplies by.
- **`rank_spearman_<view>.csv`**, **`topk_jaccard_<view>.csv`** — method × method
  Spearman rank correlation and top-1000 Jaccard overlap matrices (first column = method
  name; the Noisy-OR column appears only where propagation was recommended).
- **`micmac_quadrants.png`**, **`warfield_levels.png`**, **`recall_at_k.png`**,
  **`rank_agreement_<view>.png`**, **`summary.csv`**.

### 06_metadata_scarcity/ — detectors under evasion and absence

Evaluated on the connected level-≥1 packages; detectors: Metadata, Graph-11,
Metadata+Graph, Two-stage Warfield (Graph-11 plus six propagation features from a
level-0 metadata seeder pushed up the DAG by Noisy-OR — no package sees its own
manifest), Two-stage + metadata.

- **`detectors_clean.csv`** — AUROC/AUPRC per (view, detector) on clean metadata
  (out-of-fold RandomForest).
- **`robustness.csv`** — AUROC/AUPRC per (view, detector, condition) for conditions
  Clean, Benign-imputation, Greedy evasion (adaptive score-aware attack),
  No metadata (zeroed). Structure-only detectors are bit-identical across conditions.
- **`coverage_sweep.csv`** — AUROC per detector as the share of packages retaining
  metadata falls 100 % → 0 % (`coverage` ∈ {1.0, 0.75, 0.5, 0.25, 0.1, 0.0}).
- **`robustness_<view>.png`**, **`coverage_sweep_<view>.png`**, **`summary.csv`**
  (includes the inherited alpha and its provenance note).

### 07_temporal_validation/ — prospective validation across the connectivity ladder

- **`temporal_ladder.csv`** — one row per (view, rung, feature family) with rungs
  A: full corpus / B: has dependents / C: fully connected and families Metadata /
  Graph-11 / Metadata+Graph. Columns: rung sizes, the data-derived `cutoff` (55th
  percentile of positive timestamps), train/test positive counts, ROC-AUC and PR-AUC for
  the temporal split (train past, test future) and the size-matched random control, and
  the optimism gaps (random − temporal). All 11 structural features are recomputed on
  each rung's induced subgraph.
- **`graph_importance.csv`** — permutation importance (AUROC drop on the future test
  set) of each of the 11 structural features per (view, rung).
- **`temporal_ladder.png`**, **`graph_importance.png`**, **`summary.csv`**.

### 08_case_study_2026/ — 2026 campaign case study (npm and PyPI only)

- **`case_study_2026.csv`** — one row per named 2026-compromised package (10 npm, 4 PyPI).
  Self-contained prospective scoring at a fixed 2026-01-01 cutoff with three detectors
  (metadata — the 56-name feature list filtered to the ecosystem's available columns, so
  42 on PyPI; a graph-11 variant; union-22): `package`, `date` (attack date), `deps`
  (registry dependents), then for each of metadata-clean, metadata-greedy-evaded, union
  and graph detectors the predicted risk `*_P` and the package's percentile `*_pct`
  among the held-out test pool (higher = ranked more suspicious).

### notebooks/ — executed copies

The exact notebooks that produced the folder's artifacts, with cell outputs and the
numbered verification checks (46 per ecosystem) preserved.
