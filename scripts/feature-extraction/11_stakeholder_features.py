import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import eco_parser, ecos, input_dir

ROLES = {
    "npm": ["author", "maintainer", "contributor", "publisher"],
    "pypi": ["author", "maintainer"],
    "maven": ["author", "developer"],
}


def parse_ts(s: str):
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def keys_for(row: dict, stype: str) -> list[str]:
    """Identity keys of one stakeholder type on one package."""
    if stype == "author":
        k = row["author_email"].strip().lower() or row["author"].strip().lower()
        return [k] if k else []
    if stype == "publisher":
        k = row["publisher"].strip().lower() or row["publisher_email"].strip().lower()
        return [k] if k else []
    col = "maintainers" if stype in ("maintainer", "developer") else "contributors"
    return [m.strip().lower() for m in row[col].split(";") if m.strip()]


def ccs(service_days: float, cpn: int) -> float:
    if service_days <= 1 or cpn <= 1:
        return 0.0
    return round(math.log2(service_days) * math.log2(cpn), 4)


def run(eco: str, now: datetime) -> None:
    stypes = ROLES[eco]
    in_file = input_dir(eco) / "metadata_index.csv"
    out_file = input_dir(eco) / "stakeholder_features.csv"
    with open(in_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    index: dict[str, list] = {}       # key -> [package set, earliest created]
    for r in rows:
        created = parse_ts(r["created"])
        for stype in stypes:
            for key in keys_for(r, stype):
                pkgs, first = index.setdefault(key, [set(), created])
                pkgs.add(r["package"])
                if created and (first is None or created < first):
                    index[key][1] = created

    def stats(key: str) -> tuple[int, float]:
        if not key or key not in index:
            return 0, 0.0
        pkgs, first = index[key]
        service = (now - first).total_seconds() / 86400 if first else 0.0
        return len(pkgs), round(service, 2)

    header = ["package", "version"]
    for stype in stypes:
        header += [f"{stype}_CPN", f"{stype}_service_time", f"{stype}_CCS"]

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = [r["package"], r["version"]]
            for stype in stypes:
                s_stats = [stats(k) for k in keys_for(r, stype)] or [(0, 0.0)]
                cpn = max(s[0] for s in s_stats)
                service = max(s[1] for s in s_stats)
                out += [cpn, service, ccs(service, cpn)]
            w.writerow(out)

    print(f"{eco}: {len(rows)} packages, {len(index)} stakeholders -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--as-of", default=None,
                    help="ISO timestamp overriding 'now' for service_time (verification aid)")
    args = ap.parse_args()
    if args.as_of:
        now = datetime.fromisoformat(args.as_of)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    for eco in ecos(args):
        run(eco, now)


if __name__ == "__main__":
    main()
