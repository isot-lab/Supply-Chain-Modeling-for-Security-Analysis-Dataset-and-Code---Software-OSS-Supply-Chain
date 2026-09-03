import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import eco_parser, ecos, input_dir


def read_indexed(path: Path, drop: tuple = ("package", "version"),
                 rename: dict | None = None):
    """(columns, {package: row}) with key columns dropped/renamed."""
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rename = rename or {}
    cols = [rename.get(c, c) for c in rows[0].keys() if c not in drop] if rows else []
    data = {r["package"]: {rename.get(k, k): v for k, v in r.items()
                           if k not in drop} for r in rows}
    return cols, data


def run(eco: str) -> None:
    base_file = input_dir(eco) / "features.csv"
    if not base_file.exists():
        print(f"{eco}: {base_file} not found, skipping (run the 09 script first)")
        return
    with open(base_file, encoding="utf-8") as f:
        base = list(csv.DictReader(f))
    if not base:
        print(f"{eco}: {base_file} has no rows, skipping")
        return
    columns = list(base[0].keys())

    joins = []
    for name, drop, rename in (
        ("stakeholder_features.csv", ("package", "version"), None),
        ("github_features.csv", ("package", "repo"), {"status": "github_status"}),
        ("dependents.csv", ("package",), None),
    ):
        path = input_dir(eco) / name
        if not path.exists():
            print(f"  {eco}: {name} not found, merging without it")
            continue
        cols, data = read_indexed(path, drop, rename)
        joins.append((cols, data))
        columns += cols

    out_file = input_dir(eco) / "all_features.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in base:
            row = list(r.values())
            for cols, data in joins:
                extra = data.get(r["package"], {})
                row += [extra.get(c, "") for c in cols]
            w.writerow(row)

    print(f"{eco}: {len(base)} rows x {len(columns)} columns -> {out_file}")


def main() -> None:
    args = eco_parser(__doc__).parse_args()
    for eco in ecos(args):
        run(eco)


if __name__ == "__main__":
    main()
