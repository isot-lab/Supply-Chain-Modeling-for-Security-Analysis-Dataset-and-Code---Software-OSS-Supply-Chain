"""Extract malicious package candidates (MAL-* advisories) from the OSV dump.
Input:  data/input/<eco>/osv_raw.zip
Output: data/input/<eco>/malicious_all.csv (package, affected_versions, attack_timestamp)
Caveat: deliberately does not filter advisories by the OSV ecosystem field.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import earliest, eco_parser, ecos, input_dir, is_retracted, iter_osv_records


def is_malware(rec: dict) -> bool:
    _id = rec.get("id", "")
    if _id.startswith("MAL"):
        return True
    return False


def enumerated_versions(aff: dict) -> list:
    """Enumerated malicious versions; ranges without explicit versions -> []."""
    vers = list(aff.get("versions", []))
    for r in aff.get("ranges", []):
        for e in r.get("events", []):
            if "introduced" in e and e["introduced"] not in ("0", "0.0.0"):
                vers.append(e["introduced"])
    return vers


def extract(eco: str) -> None:
    rows: dict[str, tuple[set, str]] = {}
    for rec in iter_osv_records(eco):
        if not is_malware(rec) or is_retracted(rec):
            continue
        ts = rec.get("published", "") or rec.get("modified", "")
        for aff in rec.get("affected", []):
            pkg = aff.get("package", {}).get("name")
            if not pkg:
                continue
            versions, prev_ts = rows.get(pkg, (set(), ts))
            versions.update(enumerated_versions(aff))
            rows[pkg] = (versions, earliest(prev_ts, ts))

    out_file = input_dir(eco) / "malicious_all.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "affected_versions", "attack_timestamp"])
        for pkg in sorted(rows):
            versions, ts = rows[pkg]
            w.writerow([pkg, ";".join(sorted(versions)), ts])
    print(f"{eco:6}: {len(rows):>7} candidate packages -> {out_file}")


def main() -> None:
    args = eco_parser(__doc__).parse_args()
    for eco in ecos(args):
        extract(eco)


if __name__ == "__main__":
    main()
