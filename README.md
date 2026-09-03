# Supply-chain thesis: A production view framework for software supply chains

Code and data for the experiments over three package ecosystems (npm, PyPI, Maven
Central): a MeMPtec-style metadata baseline, its adversarial robustness, Noisy-OR risk
propagation over the dependency graph, Warfield ISM-MICMAC analysis, metadata-scarcity
detectors, temporal validation, and a 2026 case study.

## Getting the data

The data folder is too large for this repository, so it lives [here](https://drive.google.com/file/d/1_mNesuBrAO_XvFmDVeOtUMXW_c8qFA_g/view?usp=sharing). 



Download and unzip it into the repository root so that `data/input/<eco>/` sits next to
`notebooks/`. Everything below refers to the files in that folder.

## Running the experiments

With Python 3.13 and the pinned packages installed (`pip install -r requirements.txt`):

```
python notebooks\run_all.py --eco all --parallel
```

This runs the eight notebooks in order (01 through 08) for each ecosystem and writes the
results to `data/output/<eco>/`, one folder per experiment, plus executed notebook copies.
Takes about an hour on 12 cores with `--parallel`, a bit over two hours without.
Alternatively, open any notebook in Jupyter, set the ecosystem first (`%env ECO=pypi`,
default is npm) and go through each cell running each block until the end. The notebooks
build on one another, so keep the 01 to 08 order within an ecosystem. Every seed is fixed
at 42; apart from timing rows and figure bytes, re-runs reproduce the recorded results.

The dataset after preparation (notebook 01):

| ecosystem | packages | clean | vulnerable | compromised | dependency edges |
|---|---|---|---|---|---|
| npm | 101,350 | 96,265 | 2,931 | 2,154 | 388,416 |
| PyPI | 91,044 | 89,591 | 1,391 | 62 | 541,923 |
| Maven | 58,550 | 58,317 | 232 | 1 | 133,019 |

## Dataset description

One folder per ecosystem under `data/input/`. Labels: `1` = compromised (a MAL-* malware
advisory hit a later release; the row is pinned to the *last clean version* published
before the attack, so features describe the package as it looked the day before),
`-1` = vulnerable (non-malware advisory, pinned to the latest release), `0` = clean
control (popular package, latest release). Everything comes from a single crawl in
July 2026. Missing values are left empty, never zero-filled.

| file | what it is |
|---|---|
| `osv_raw.zip` | full OSV advisory mirror for the ecosystem |
| `malicious_all.csv` | packages named in MAL-* advisories, with affected versions and attack timestamp |
| `vulnerable_all.csv` | packages with non-malware advisories: ids, severity, affected ranges, first advisory timestamp |
| `pre_compromise_versions.csv` | for each compromised release, the last clean version and the compromise time |
| `top_packages.csv` | top ~100k packages by distinct direct dependents (deps.dev) |
| `dataset.csv` | the labeled corpus: package, pinned version, label |
| `latest_versions.csv` | latest release per package (cache used while building `dataset.csv`) |
| `dependent_counts_fill.csv` | dependent counts for compromised/vulnerable packages missing from the popularity crawl |
| `features.csv` | MeMPtec registry metadata features for the pinned version of every package |
| `metadata_index.csv` | raw identities behind the features: repo URL, author/maintainers, created time, declared dependencies |
| `github_features.csv` | stars, forks, watchers, issues, PRs for packages with a GitHub repository |
| `stakeholder_features.csv` | CPN / service_time / CCS per stakeholder role |
| `graph_edges.csv` | the dependency graph over the corpus packages (source depends on target) |
| `dependents.csv` | per-package in-corpus degrees and registry-wide dependent counts |
| `all_features.csv` | all of the above merged into one table per package; this is what the notebooks read (filter on `status == "ok"`) |


One warning when loading these files: npm has real packages named `nan` and
`null` (PyPI has `null`), so read CSVs with the default missing-value list disabled,
e.g. `pd.read_csv(..., keep_default_na=False, na_values=[""])`, or those rows are lost.

## Feature sets

### MeMPtec metadata features

The baseline feature set, following MeMPtec's ETM/DTM split: ETM (easy to manipulate) is
whatever the package metadata declares, DTM (difficult to manipulate) accrues over time.
Fields differ per registry; `x_exist` is a presence flag, `x_length` a character length,
`x_num_count` an item count.

ETM (npm 36, PyPI 26, Maven 22):

| feature | npm | PyPI | Maven |
|---|---|---|---|
| `name_exist`, `name_length` | ✓ | ✓ | ✓ |
| `versions_exist`, `versions_length`, `versions_num_count` | ✓ | ✓ | ✓ |
| `description_exist`, `description_length` | ✓ | ✓ | ✓ |
| `author_exist`, `author_name`, `author_email` | ✓ | ✓ | ✓ |
| `license_exist`, `license_length` | ✓ | ✓ | ✓ |
| `homepage_exist`, `homepage_length` | ✓ | ✓ | ✓ |
| `github_exist`, `github_length` | ✓ | ✓ | ✓ |
| `bugslink_exist`, `bugslink_length` | ✓ | ✓ | ✓ |
| `dependencies_exist`, `dependencies_length` | ✓ | ✓ | ✓ |
| `maintainers_exist` | ✓ | ✓ | — |
| `readme_exist`, `readme_length` | ✓ | ✓ | — |
| `keywords_exist`, `keywords_length`, `keywords_num_count` | ✓ | ✓ | — |
| `devDependencies_exist`, `devDependencies_length` | ✓ | — | ✓ |
| `dist_tags_exist`, `dist_tags_length` | ✓ | — | — |
| `scripts_exist`, `scripts_length` | ✓ | — | — |
| `directories_exist`, `directories_length` | ✓ | — | — |
| `issueslink_exist`, `issueslink_length` (mirrors `bugslink_*`) | ✓ | — | — |

DTM (npm 20, PyPI 14, Maven 14):

| feature | npm | PyPI | Maven |
|---|---|---|---|
| `package_age_days` | ✓ | ✓ | ✓ |
| `package_modified_duration_days` | ✓ | ✓ | ✓ |
| `package_published_duration_days` | ✓ | ✓ | ✓ |
| `author_CPN`, `author_service_time`, `author_CCS` | ✓ | ✓ | ✓ |
| `maintainer_CPN`, `maintainer_service_time`, `maintainer_CCS` | ✓ | ✓ | — |
| `developer_CPN`, `developer_service_time`, `developer_CCS` | — | — | ✓ |
| `contributor_CPN`, `contributor_service_time`, `contributor_CCS` | ✓ | — | — |
| `publisher_CPN`, `publisher_service_time`, `publisher_CCS` | ✓ | — | — |
| `star`, `fork_number`, `subscriber_count`, `issues`, `pull_request` | ✓ | ✓ | ✓ |

CPN counts the stakeholder's packages within the corpus, service_time their days active,
CCS = log2(service_time) × log2(CPN). Maven has no maintainer accounts, so its second
role is the POM `<developers>` list (unverified free text, hence the different name).
The five GitHub counts are missing as a block wherever no repository is linked.

### Production view features (proposed)

Eleven structural features computed from the dependency graph alone, identical across
ecosystems. Nothing here can be set from inside a package's own metadata.

| feature | meaning |
|---|---|
| `warfield_level` | longest production chain below the package (0 = manufacturer) |
| `in_degree` | direct dependents in the corpus |
| `out_degree` | direct dependencies in the corpus |
| `log1p_driving_power` | transitive dependents (blast radius), log1p |
| `log1p_dependence_power` | transitive dependencies (exposure surface), log1p |
| `scc_size` | size of the package's dependency cycle, 1 if none |
| `pagerank` | PageRank on the dependency orientation |
| `hits_hub` | HITS hub score |
| `hits_auth` | HITS authority score |
| `clustering` | local clustering coefficient (undirected) |
| `closeness` | harmonic closeness, landmark-approximated (undirected) |

### Two-stage propagated features (proposed)

Six features derived by training a metadata model on the level-0 manufacturers only and
pushing its risk scores up the production graph with a Noisy-OR gate. Every value comes
from *depended* packages, so a package is never scored from its own metadata. The two-stage
detector in the experiments uses these six together with the eleven production view
features above.

| feature | meaning |
|---|---|
| `prop_score` | Noisy-OR propagated risk reaching the package |
| `hop_dist` | hops from the nearest manufacturer (-1 if unreachable) |
| `pred_risk_mean` | mean propagated risk of its direct dependencies |
| `succ_risk_mean` | mean propagated risk of its direct dependents |
| `grandparent_risk` | mean risk two levels up the supply chain |
| `great_grandparent_risk` | mean risk three levels up |

## Data collection

The scripts under `scripts/` are what built `data/input/`: OSV advisory ingestion,
registry probes to separate hijacked packages from throwaway malware, popularity from
deps.dev BigQuery, and the feature extractors (registry, GitHub, stakeholder, graph).
They query live services, so running them again yields a newer snapshot, not this one.
The Drive copy is the dataset the recorded results were produced from.
