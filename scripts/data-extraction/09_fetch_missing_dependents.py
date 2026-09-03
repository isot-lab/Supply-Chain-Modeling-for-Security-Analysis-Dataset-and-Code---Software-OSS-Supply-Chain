import csv
import json
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (ECOSYSTEMS_MS_API, ECOSYSTEMS_MS_REGISTRY, done_keys,
                    eco_parser, ecos, http_get, input_dir)

FIELDS = ["package", "dependent_packages_count", "dependent_repos_count",
          "downloads_last_month", "status"]


def fetch_one(registry: str, name: str) -> dict:
    url = f"{ECOSYSTEMS_MS_API}/{registry}/packages/{urllib.parse.quote(name, safe='')}"
    code, body = http_get(url, timeout=60)
    if code == 404:
        return {"package": name, "dependent_packages_count": "",
                "dependent_repos_count": "", "downloads_last_month": "",
                "status": "not_found"}
    if code != 200:
        return {"package": name, "dependent_packages_count": "",
                "dependent_repos_count": "", "downloads_last_month": "",
                "status": f"error:{code}"}
    d = json.loads(body)
    downloads = d.get("downloads") or ""
    if downloads != "" and d.get("downloads_period") not in (None, "last-month"):
        downloads = ""  # only trust monthly figures; other periods are not comparable
    return {
        "package": name,
        "dependent_packages_count": d.get("dependent_packages_count") or 0,
        "dependent_repos_count": d.get("dependent_repos_count") or 0,
        "downloads_last_month": downloads,
        "status": "ok",
    }


def load_targets(eco: str) -> list[str]:
    """Dataset packages without a positive count in top_packages.csv."""
    top_file = input_dir(eco) / "top_packages.csv"
    have = {}
    if top_file.exists():
        with open(top_file, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                have[row["package"]] = row.get("dependent_packages_count") or ""
    targets = []
    with open(input_dir(eco) / "dataset.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["package"]
            if str(have.get(name, "")).strip() in ("", "0"):
                targets.append(name)
    return targets


def run(eco: str, workers: int) -> None:
    registry = ECOSYSTEMS_MS_REGISTRY[eco]
    out_file = input_dir(eco) / "dependent_counts_fill.csv"
    done = done_keys(out_file, skip=lambda r: r["status"].startswith("error"))
    targets = [p for p in load_targets(eco) if p not in done]
    print(f"{eco}: {len(targets)} packages to fetch ({len(done)} already done)")
    if not targets:
        return

    write_header = not out_file.exists()
    lock = threading.Lock()
    n_done = 0
    with open(out_file, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(fetch_one, registry, name) for name in targets]
            for fut in as_completed(futures):
                row = fut.result()
                with lock:
                    w.writerow(row)
                    f.flush()
                    n_done += 1
                    if n_done % 200 == 0:
                        print(f"  {n_done}/{len(targets)}")
    print(f"{eco}: wrote {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    for eco in ecos(args):
        run(eco, args.workers)


if __name__ == "__main__":
    main()
