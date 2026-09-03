import csv
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (DEPS_DEV_DATASET, DEPS_DEV_SYSTEMS, bq_cmd, bq_query,
                    eco_parser, ecos, input_dir, latest_snapshot_day)

TMP_DATASET = "thesis_tmp"


def latest_versions(eco: str, names: list[str], project: str) -> dict[str, str]:
    """package -> latest release version via BigQuery temp-table join, cached."""
    cache = input_dir(eco) / "latest_versions.csv"
    if cache.exists():
        with open(cache, encoding="utf-8") as f:
            cached = {r["package"]: r["version"] for r in csv.DictReader(f)}
        if set(names) <= set(cached):
            return cached
        print(f"  {cache} is missing {len(set(names) - set(cached))} packages, refreshing")

    r = bq_cmd(["mk", f"--project_id={project}", "--dataset", TMP_DATASET])
    if r.returncode != 0 and "already exists" not in r.stdout + r.stderr:
        raise RuntimeError(f"bq mk failed:\n{r.stdout}\n{r.stderr}")

    table = f"{TMP_DATASET}.pkgs_{eco}"
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="", encoding="utf-8") as tf:
        csv.writer(tf).writerows([n] for n in names)
    r = bq_cmd(["load", f"--project_id={project}", "--replace",
                "--source_format=CSV", table, tf.name, "name:STRING"])
    Path(tf.name).unlink()
    if r.returncode != 0:
        raise RuntimeError(f"bq load failed:\n{r.stdout}\n{r.stderr}")

    day = latest_snapshot_day(project)
    sql = f"""
        SELECT t.name AS package, IFNULL(pv.Version, '') AS version
        FROM `{project}.{table}` t
        LEFT JOIN (
            SELECT Name, Version FROM `{DEPS_DEV_DATASET}.PackageVersions`
            WHERE System = '{DEPS_DEV_SYSTEMS[eco]}'
              AND SnapshotAt >= TIMESTAMP '{day}'
              AND VersionInfo.IsRelease
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY Name ORDER BY VersionInfo.Ordinal DESC) = 1
        ) pv ON pv.Name = t.name
    """
    out = bq_query(project, ["--format=csv", f"--max_rows={len(names)}"], sql)
    versions = {r["package"]: r["version"]
                for r in csv.DictReader(io.StringIO(out))}

    with open(cache, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "version"])
        for n in names:
            w.writerow([n, versions.get(n, "")])
    return versions


def read_column(path: Path, column: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [r[column] for r in csv.DictReader(f)]


def run(eco: str, project: str) -> None:
    print(f"== {eco}")

    top, vuln = [], []
    top_file = input_dir(eco) / "top_packages.csv"
    if top_file.exists():
        top = read_column(top_file, "package")
    else:
        print(f"  {top_file} not found, no top packages (run 07)")

    vuln_file = input_dir(eco) / "vulnerable_all.csv"
    if vuln_file.exists():
        vuln = read_column(vuln_file, "package")
    else:
        print(f"  {vuln_file} not found, no vulnerable packages (run 05)")

    compromised: dict[str, str] = {}
    dropped = {"top": 0, "vuln": 0, "compromised": 0}
    comp_file = input_dir(eco) / "pre_compromise_versions.csv"
    if comp_file.exists():
        with open(comp_file, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["pre_compromise_version"]:
                    compromised[r["package"]] = r["pre_compromise_version"]
                else:
                    dropped["compromised"] += 1
    else:
        print(f"  {comp_file} not found, no compromised packages (run 03+04)")

    latest = {}
    if top or vuln:
        latest = latest_versions(eco, sorted(set(top) | set(vuln)), project)

    dataset: dict[str, tuple[str, int]] = {}
    for pkg in top:  # lowest precedence first
        if latest.get(pkg):
            dataset[pkg] = (latest[pkg], 0)
        else:
            dropped["top"] += 1
    for pkg in vuln:
        if latest.get(pkg):
            dataset[pkg] = (latest[pkg], -1)
        elif pkg not in compromised:
            dropped["vuln"] += 1
    for pkg, version in compromised.items():
        dataset[pkg] = (version, 1)

    out_file = input_dir(eco) / "dataset.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "version", "label"])
        for pkg, (version, label) in sorted(dataset.items(),
                                            key=lambda x: (-x[1][1], x[0])):
            w.writerow([pkg, version, label])

    counts = {1: 0, -1: 0, 0: 0}
    for _, label in dataset.values():
        counts[label] += 1
    print(f"  dataset: {counts[1]} compromised, {counts[-1]} vuln, "
          f"{counts[0]} top (dropped, no version: {dropped}) -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    for eco in ecos(args):
        run(eco, args.project)


if __name__ == "__main__":
    main()
