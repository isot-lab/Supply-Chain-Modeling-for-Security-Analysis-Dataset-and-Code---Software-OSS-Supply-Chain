import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import earliest, eco_parser, ecos, input_dir, is_retracted, iter_osv_records

# GitHub publishes its own malware advisories as GHSA records without a
# MAL-* alias; their summaries follow a fixed "Malicious code/package in x"
# pattern (sometimes "Embedded malicious code in x").
MALWARE_TITLE = re.compile(r"^(embedded )?malicious (code|package)", re.I)

SEVERITY_RANK = {"": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


def is_malware(rec: dict) -> bool:
    if rec.get("id", "").startswith("MAL"):
        return True
    if any(a.startswith("MAL") for a in rec.get("aliases", []) or []):
        return True
    return bool(MALWARE_TITLE.match(rec.get("summary", "") or ""))


def severity_of(rec: dict) -> str:
    sev = (rec.get("database_specific") or {}).get("severity", "") or ""
    return sev.upper() if sev.upper() in SEVERITY_RANK else ""


def range_spans(aff: dict) -> list:
    """Flatten OSV range events into 'introduced..fixed' span strings."""
    spans = []
    for r in aff.get("ranges", []):
        intro = None
        for e in r.get("events", []):
            if "introduced" in e:
                if intro is not None:
                    spans.append(f"{intro}..")
                intro = e["introduced"]
            elif "fixed" in e:
                spans.append(f"{intro or '0'}..{e['fixed']}")
                intro = None
            elif "last_affected" in e:
                spans.append(f"{intro or '0'}..={e['last_affected']}")
                intro = None
        if intro is not None:
            spans.append(f"{intro}..")
    return spans


def extract(eco: str) -> None:
    # package -> [advisory_ids, versions, spans, max_severity, earliest_ts]
    rows: dict[str, list] = {}
    for rec in iter_osv_records(eco):
        if is_malware(rec) or is_retracted(rec):
            continue
        ts = rec.get("published", "") or rec.get("modified", "")
        sev = severity_of(rec)
        for aff in rec.get("affected", []):
            pkg = aff.get("package", {}).get("name")
            if not pkg:
                continue
            ids, versions, spans, max_sev, prev_ts = rows.setdefault(
                pkg, [set(), set(), set(), "", ""])
            ids.add(rec.get("id", ""))
            versions.update(aff.get("versions", []))
            spans.update(range_spans(aff))
            if SEVERITY_RANK[sev] > SEVERITY_RANK[max_sev]:
                rows[pkg][3] = sev
            rows[pkg][4] = earliest(prev_ts, ts)

    out_file = input_dir(eco) / "vulnerable_all.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "advisory_ids", "max_severity", "affected_versions",
                    "affected_ranges", "first_advisory_timestamp"])
        for pkg in sorted(rows):
            ids, versions, spans, max_sev, ts = rows[pkg]
            w.writerow([pkg, ";".join(sorted(ids)), max_sev,
                        ";".join(sorted(versions)), ";".join(sorted(spans)), ts])
    print(f"{eco:6}: {len(rows):>7} vulnerable packages -> {out_file}")


def main() -> None:
    args = eco_parser(__doc__).parse_args()
    for eco in ecos(args):
        extract(eco)


if __name__ == "__main__":
    main()
