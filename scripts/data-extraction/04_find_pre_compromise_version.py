import csv
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import done_keys, eco_parser, ecos, fetch_json, input_dir


def fetch_npm(pkg: str):
    """Return {version: iso_publish_time} of installable versions, or None."""
    data = fetch_json("https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@"))
    if data is None:
        return None
    installable = set((data.get("versions") or {}).keys())
    return {v: t for v, t in (data.get("time") or {}).items()
            if v in installable and not v.endswith("-security")}


def fetch_pypi(pkg: str):
    data = fetch_json(f"https://pypi.org/pypi/{urllib.parse.quote(pkg)}/json")
    if data is None:
        return None
    times = {}
    for v, files in (data.get("releases") or {}).items():
        uploads = [f["upload_time_iso_8601"] for f in files if not f.get("yanked")]
        if uploads:
            times[v] = min(uploads)
    return times


def fetch_maven(pkg: str):
    if ":" not in pkg:
        return None
    group, artifact = pkg.split(":", 1)
    times = {}
    start = 0
    while True:
        q = urllib.parse.quote(f'g:"{group}" AND a:"{artifact}"')
        data = fetch_json("https://search.maven.org/solrsearch/select"
                          f"?q={q}&core=gav&rows=200&start={start}&wt=json")
        if data is None:
            return None
        resp = data.get("response") or {}
        docs = resp.get("docs") or []
        for d in docs:
            ts = datetime.fromtimestamp(d["timestamp"] / 1000, tz=timezone.utc)
            times[d["v"]] = ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        start += len(docs)
        if start >= resp.get("numFound", 0) or not docs:
            return times


FETCHERS = {"npm": fetch_npm, "pypi": fetch_pypi, "maven": fetch_maven}


def resolve(times: dict | None, affected: set, attack_ts: str):
    """Return (first_affected, compromise_time, pre_version, pre_time, status)."""
    if times is None:
        return "", "", "", "", "registry_error"

    affected_times = sorted((times[v], v) for v in affected if v in times)
    if affected_times:
        compromise_time, first_affected = affected_times[0]
    elif attack_ts:
        compromise_time, first_affected = attack_ts, ""
    else:
        return "", "", "", "", "no_compromise_time"

    clean = sorted((t, v) for v, t in times.items()
                   if v not in affected and t < compromise_time)
    if not clean:
        return first_affected, compromise_time, "", "", "no_prior_clean_version"

    pre_time, pre_version = clean[-1]
    return first_affected, compromise_time, pre_version, pre_time, "ok"


def run(eco: str, workers: int, limit: int | None) -> None:
    fetch = FETCHERS[eco]
    in_file = input_dir(eco) / "malicious_labeled.csv"
    out_file = input_dir(eco) / "pre_compromise_versions.csv"

    if not in_file.exists():
        print(f"{eco}: {in_file} not found, skipping (run 03 first)")
        return

    with open(in_file, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] == "compromised_release"]
    if limit:
        rows = rows[:limit]

    done = done_keys(out_file)
    todo = [r for r in rows if r["package"] not in done]
    print(f"{eco}: {len(rows)} compromised_release, {len(done)} already resolved, {len(todo)} to do")

    new = not out_file.exists()
    counts: dict[str, int] = {}
    processed = 0
    with open(out_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["package", "affected_versions", "first_affected_version",
                        "compromise_time", "pre_compromise_version",
                        "pre_compromise_time", "status"])

        def work(r):
            affected = {v for v in r["affected_versions"].split(";") if v}
            times = fetch(r["package"])
            return r, resolve(times, affected, r["attack_timestamp"])

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, r) for r in todo]
            for fut in as_completed(futures):
                r, (first_aff, ctime, pre_v, pre_t, status) = fut.result()
                counts[status] = counts.get(status, 0) + 1
                w.writerow([r["package"], r["affected_versions"], first_aff,
                            ctime, pre_v, pre_t, status])
                processed += 1
                if processed % 50 == 0:
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
