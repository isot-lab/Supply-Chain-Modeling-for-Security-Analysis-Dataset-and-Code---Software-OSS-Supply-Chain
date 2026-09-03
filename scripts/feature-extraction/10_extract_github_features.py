import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, done_keys, eco_parser, ecos, input_dir

API = "https://api.github.com/graphql"
GITHUB_RE = re.compile(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git|[/#?]|$)",
                       re.I)
FIELDS = ["star", "fork_number", "subscriber_count", "issues", "pull_request"]


def token_from_env() -> str:
    """GITHUB_TOKEN from the environment, falling back to the repo-root .env."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GITHUB_TOKEN"):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def parse_repo(url: str):
    """'owner/name' from any of the git/scm/https URL shapes, or None."""
    m = GITHUB_RE.search(url or "")
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    if owner.lower() in ("orgs", "topics", "search", "sponsors"):
        return None
    return f"{owner}/{name}"


def graphql(token: str, query: str, tries: int = 5):
    """POST one GraphQL query; retries 403/429/5xx (a first-attempt 401 is fatal)."""
    payload = json.dumps({"query": query}).encode()
    delay = 5.0
    for attempt in range(tries):
        try:
            req = Request(API, data=payload, headers={
                "Authorization": f"bearer {token}",
                "User-Agent": "solomon-supply-chain/github-features",
                "Content-Type": "application/json",
            })
            with urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except HTTPError as e:
            if e.code == 401 and attempt == 0:
                raise RuntimeError("GitHub rejected the token (401)")
            if e.code in (403, 429, 502, 503) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_repos(token: str, repos: list[str]) -> dict:
    """repo -> feature dict (or None for missing repos), one batched query."""
    parts = []
    for i, repo in enumerate(repos):
        owner, name = repo.split("/", 1)
        owner, name = owner.replace('"', ""), name.replace('"', "")
        parts.append(
            f'r{i}: repository(owner:"{owner}", name:"{name}") {{'
            " stargazerCount forkCount watchers{totalCount}"
            " issues{totalCount} pullRequests{totalCount} }")
    resp = graphql(token, "query {" + " ".join(parts) + "}")
    if "data" not in resp or resp["data"] is None:
        raise RuntimeError(f"GraphQL failure: {json.dumps(resp)[:400]}")
    out = {}
    for i, repo in enumerate(repos):
        node = resp["data"].get(f"r{i}")
        if node is None:
            out[repo] = None
            continue
        out[repo] = {
            "star": node["stargazerCount"],
            "fork_number": node["forkCount"],
            "subscriber_count": node["watchers"]["totalCount"],
            "issues": node["issues"]["totalCount"],
            "pull_request": node["pullRequests"]["totalCount"],
        }
    return out


def run(eco: str, token: str, batch: int, limit: int | None) -> None:
    in_file = input_dir(eco) / "metadata_index.csv"
    out_file = input_dir(eco) / "github_features.csv"
    if not in_file.exists():
        print(f"{eco}: {in_file} not found, skipping (run the 09 script first)")
        return

    with open(in_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    done = done_keys(out_file)
    todo = [r for r in rows if r["package"] not in done]
    print(f"{eco}: {len(rows)} packages, {len(done)} done, {len(todo)} to resolve")

    new = not out_file.exists()
    counts: dict[str, int] = {}
    cache: dict[str, dict | None] = {}  # monorepo packages share one repo's numbers
    with open(out_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["package", "repo", *FIELDS, "status"])

        def emit(pkg, repo, feats, status):
            counts[status] = counts.get(status, 0) + 1
            vals = [feats[k] for k in FIELDS] if feats else [""] * len(FIELDS)
            w.writerow([pkg, repo or "", *vals, status])

        pending = []  # (package, repo) awaiting a batch
        for r in todo:
            url = r["repo_url"]
            if not url.strip():
                emit(r["package"], None, None, "no_repo_url")
                continue
            repo = parse_repo(url)
            if repo is None:
                emit(r["package"], None, None, "not_github")
                continue
            pending.append((r["package"], repo))

        for start in range(0, len(pending), batch):
            chunk = pending[start:start + batch]
            need = sorted({repo for _, repo in chunk if repo not in cache})
            if need:
                cache.update(fetch_repos(token, need))
            for pkg, repo in chunk:
                feats = cache.get(repo)
                emit(pkg, repo, feats, "ok" if feats else "not_found")
            f.flush()
            if (start // batch) % 20 == 0:
                print(f"  {start + len(chunk)}/{len(pending)}  {counts}")

    print(f"{eco} done: {counts} -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--token", default=token_from_env())
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if not args.token:
        raise SystemExit("no GitHub token: pass --token or set GITHUB_TOKEN")
    for eco in ecos(args):
        run(eco, args.token, args.batch, args.limit)


if __name__ == "__main__":
    main()
