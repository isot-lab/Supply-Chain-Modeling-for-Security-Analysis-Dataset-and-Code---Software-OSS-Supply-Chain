import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (DEPS_DEV_DATASET, DEPS_DEV_SYSTEMS, bq_query, eco_parser,
                    ecos, input_dir, latest_snapshot_day)


def top_query(eco: str, day: str, k: int) -> str:
    return f"""
        SELECT Dependency.Name AS package,
               COUNT(DISTINCT Name) AS dependent_packages_count
        FROM `{DEPS_DEV_DATASET}.Dependencies`
        WHERE System = '{DEPS_DEV_SYSTEMS[eco]}'
          AND SnapshotAt >= TIMESTAMP '{day}'
          AND MinimumDepth = 1
        GROUP BY package
        ORDER BY dependent_packages_count DESC
        LIMIT {k}
    """


def run(eco: str, day: str, k: int, project: str, max_gb: float) -> None:
    sql = top_query(eco, day, k)

    est = bq_query(project, ["--dry_run"], sql)
    est_gb = int("".join(c for c in est if c.isdigit())) / 1e9
    print(f"{eco}: query will scan ~{est_gb:.1f} GB", flush=True)
    if est_gb > max_gb:
        print(f"{eco}: exceeds --max-gb {max_gb}, skipping. "
              f"Raise --max-gb to allow (free tier is 1 TB/month).")
        return

    cap = int(max_gb * 1e9)  # also enforced server-side, not just by the dry run
    out = bq_query(project, ["--format=csv", f"--max_rows={k}",
                             f"--maximum_bytes_billed={cap}"], sql)

    rows = list(csv.DictReader(io.StringIO(out)))
    out_file = input_dir(eco) / "top_packages.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "package", "dependent_packages_count"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["package"], r["dependent_packages_count"]])
    print(f"{eco:6}: {len(rows):>6} top packages -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--k", type=int, default=100000)
    ap.add_argument("--project", required=True)
    ap.add_argument("--max-gb", type=float, default=450,
                    help="abort any query estimated to scan more than this")
    args = ap.parse_args()

    day = latest_snapshot_day(args.project)
    print(f"deps.dev latest snapshot: {day}")
    for eco in ecos(args):
        run(eco, day, args.k, args.project, args.max_gb)


if __name__ == "__main__":
    main()
