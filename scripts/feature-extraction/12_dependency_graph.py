import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import eco_parser, ecos, input_dir


def normalizer(eco: str):
    if eco == "pypi":
        return lambda name: re.sub(r"[-_.]+", "-", name.strip().lower())  # PEP 503
    return lambda name: name.strip()


def run(eco: str) -> None:
    in_file = input_dir(eco) / "metadata_index.csv"
    if not in_file.exists():
        print(f"{eco}: {in_file} not found, skipping (run the 09 script first)")
        return
    norm = normalizer(eco)

    with open(in_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"{eco}: {in_file} is empty, skipping (rerun the 09 script)")
        return
    canonical = {norm(r["package"]): r["package"] for r in rows}

    edges = set()
    for r in rows:
        src = r["package"]
        for dep in r["dependencies"].split(";"):
            target = canonical.get(norm(dep)) if dep else None
            if target and target != src:
                edges.add((src, target))
    out_degree = Counter(s for s, _ in edges)
    in_degree = Counter(t for _, t in edges)

    global_counts = {}
    top_file = input_dir(eco) / "top_packages.csv"
    if top_file.exists():
        with open(top_file, encoding="utf-8") as f:
            global_counts = {r["package"]: r["dependent_packages_count"]
                             for r in csv.DictReader(f)}
    else:
        print(f"  {eco}: {top_file} not found, global counts left empty")

    edges_file = input_dir(eco) / "graph_edges.csv"
    with open(edges_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "target"])
        w.writerows(sorted(edges))

    dep_file = input_dir(eco) / "dependents.csv"
    with open(dep_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "dependents_in_dataset", "dependencies_in_dataset",
                    "global_dependent_packages_count"])
        for r in rows:
            pkg = r["package"]
            w.writerow([pkg, in_degree.get(pkg, 0), out_degree.get(pkg, 0),
                        global_counts.get(pkg, "")])

    print(f"{eco}: {len(rows)} nodes, {len(edges)} edges, "
          f"{sum(1 for r in rows if r['package'] in global_counts)} with global "
          f"counts -> {edges_file}, {dep_file}")


def main() -> None:
    args = eco_parser(__doc__).parse_args()
    for eco in ecos(args):
        run(eco)


if __name__ == "__main__":
    main()
