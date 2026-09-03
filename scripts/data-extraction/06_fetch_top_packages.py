import csv
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (ECOSYSTEMS_MS_API, ECOSYSTEMS_MS_REGISTRY, eco_parser,
                    ecos, http_get, input_dir)

PER_PAGE = 1000
SORT_KEY = "dependent_packages_count"  # same popularity metric for every ecosystem


def fetch_page(eco: str, page: int) -> list | None:
    """One sorted page, or None once the API's depth ceiling is hit (500)."""
    url = (f"{ECOSYSTEMS_MS_API}/{ECOSYSTEMS_MS_REGISTRY[eco]}/packages"
           f"?sort={SORT_KEY}&order=desc&per_page={PER_PAGE}&page={page}")
    code, body = http_get(url, tries=3, timeout=60)
    if code == 500:
        return None
    if code != 200:
        raise RuntimeError(f"{eco}: HTTP {code} on page {page}")
    return json.loads(body)


def fetch_top(eco: str, k: int, workers: int) -> list[dict]:
    """Fetch pages in parallel waves; page order (= rank order) is preserved.

    Waves are capped at `workers` pages so hitting the API's depth ceiling
    doesn't fire dozens of doomed 30-second queries; keep workers low (default
    2) since concurrent sorted pages contend server-side and start timing out.
    """
    top, seen = [], set()
    next_page = 1
    done = False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        while len(top) < k and not done:
            n = min(workers, math.ceil((k - len(top)) / PER_PAGE))
            pages = range(next_page, next_page + n)
            next_page += n
            for batch in ex.map(partial(fetch_page, eco), pages):
                if batch is None:
                    print(f"  {eco}: API popularity sort caps out here; "
                          f"got {len(top)} of the requested {k}")
                    done = True
                    break
                if len(batch) < PER_PAGE:
                    done = True
                for p in batch:
                    name = p.get("name")
                    if not name or name in seen or len(top) >= k:
                        continue
                    seen.add(name)
                    top.append({
                        "package": name,
                        "downloads_last_month": p.get("downloads") or "",
                        "dependent_repos_count": p.get("dependent_repos_count") or 0,
                        "dependent_packages_count": p.get("dependent_packages_count") or 0,
                        "latest_version": p.get("latest_release_number") or "",
                    })
    return top


def run(eco: str, k: int, workers: int) -> None:
    top = fetch_top(eco, k, workers)
    out_file = input_dir(eco) / "top_packages.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "package", "downloads_last_month",
                    "dependent_repos_count", "dependent_packages_count",
                    "latest_version"])
        for i, p in enumerate(top, 1):
            w.writerow([i, p["package"], p["downloads_last_month"],
                        p["dependent_repos_count"], p["dependent_packages_count"],
                        p["latest_version"]])
    print(f"{eco:6}: {len(top):>5} top packages -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--k", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    for eco in ecos(args):
        run(eco, args.k, args.workers)


if __name__ == "__main__":
    main()
