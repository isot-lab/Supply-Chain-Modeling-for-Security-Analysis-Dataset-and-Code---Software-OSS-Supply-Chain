import csv
import json
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import done_keys, eco_parser, ecos, http_get, input_dir

REMOVED, EXISTS, UNKNOWN = "removed", "exists", "unknown"


def probe_npm(pkg: str):
    url = "https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@")
    code, body = http_get(url)
    if code == 404:
        return REMOVED, []
    if code != 200:
        return UNKNOWN, []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return UNKNOWN, []
    versions = list((data.get("versions") or {}).keys())
    desc = (data.get("description") or "").lower()
    if "security holding package" in desc or (
        versions and all(v.endswith("-security") for v in versions)
    ):
        return REMOVED, []
    return EXISTS, versions


def probe_pypi(pkg: str):
    url = f"https://pypi.org/pypi/{urllib.parse.quote(pkg)}/json"
    code, body = http_get(url)
    if code == 404:
        return REMOVED, []
    if code != 200:
        return UNKNOWN, []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return UNKNOWN, []
    return EXISTS, list((data.get("releases") or {}).keys())


def probe_maven(pkg: str):
    if ":" not in pkg:
        return UNKNOWN, []
    group, artifact = pkg.split(":", 1)
    path = group.replace(".", "/")
    url = f"https://repo1.maven.org/maven2/{path}/{artifact}/maven-metadata.xml"
    code, body = http_get(url)
    if code == 404:
        return REMOVED, []
    if code != 200:
        return UNKNOWN, []
    try:
        root = ET.fromstring(body)
        return EXISTS, [v.text for v in root.iter("version") if v.text]
    except ET.ParseError:
        return UNKNOWN, []


PROBES = {"npm": probe_npm, "pypi": probe_pypi, "maven": probe_maven}


def label_for(state: str, published: list, affected: set) -> str:
    if state == UNKNOWN:
        return "unknown"
    if state == REMOVED:
        return "malicious_upload"
    if not published:
        return "unknown"                     # exists but no versions -> can't judge
    clean = set(published) - affected        # affected empty -> clean == published
    if not affected:
        return "malicious_upload"            # whole package condemned, still live
    return "compromised_release" if clean else "malicious_upload"


def run(eco: str, workers: int, limit: int | None) -> None:
    probe = PROBES[eco]
    in_file = input_dir(eco) / "malicious_all.csv"
    out_file = input_dir(eco) / "malicious_labeled.csv"

    with open(in_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    done = done_keys(out_file)
    todo = [r for r in rows if r["package"] not in done]
    print(f"{eco}: {len(rows)} candidates, {len(done)} already labeled, {len(todo)} to do")

    new = not out_file.exists()
    counts = {"malicious_upload": 0, "compromised_release": 0, "unknown": 0}
    processed = 0
    with open(out_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["package", "affected_versions", "label", "attack_timestamp"])

        def work(r):
            affected = {v for v in r["affected_versions"].split(";") if v}
            state, published = probe(r["package"])
            return r, label_for(state, published, affected)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, r) for r in todo]
            for fut in as_completed(futures):
                r, label = fut.result()
                counts[label] = counts.get(label, 0) + 1
                w.writerow([r["package"], r["affected_versions"], label, r["attack_timestamp"]])
                processed += 1
                if processed % 500 == 0:
                    f.flush()
                    print(f"  {processed}/{len(todo)}  {counts}")

    print(f"{eco} done: {counts}  -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    for eco in ecos(args):
        run(eco, args.workers, args.limit)


if __name__ == "__main__":
    main()
