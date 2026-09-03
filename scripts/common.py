import argparse
import csv
import email.utils
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("THESIS_DATA", ROOT / "data"))
ECOSYSTEMS = ("npm", "pypi", "maven")
OSV_NAMES = {"npm": "npm", "pypi": "PyPI", "maven": "Maven"}  # OSV mirror capitalisation
UA = {"User-Agent": "solomon-supply-chain"}


def input_dir(eco: str) -> Path:
    p = DATA / "input" / eco
    p.mkdir(parents=True, exist_ok=True)
    return p


def osv_zip(eco: str) -> Path:
    return input_dir(eco) / "osv_raw.zip"


def eco_parser(description: str = "") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--eco", choices=[*ECOSYSTEMS, "all"], default="all")
    return ap


def ecos(args) -> list[str]:
    return list(ECOSYSTEMS) if args.eco == "all" else [args.eco]


def http_get(url: str, tries: int = 4, timeout: int = 30, method: str = "GET",
             last_modified: bool = False):
    """(status, body) or, with last_modified, (status, body, last_modified_iso).
    Status is None on network failure; retries with backoff on 429/5xx."""
    def result(code, body, lm=""):
        return (code, body, lm) if last_modified else (code, body)
    delay = 1.0
    for attempt in range(tries):
        try:
            with urlopen(Request(url, headers=UA, method=method), timeout=timeout) as r:
                lm = ""
                if last_modified and r.headers.get("Last-Modified"):
                    try:
                        lm = email.utils.parsedate_to_datetime(
                            r.headers["Last-Modified"]).isoformat()
                    except (TypeError, ValueError):
                        lm = ""
                return result(r.getcode(), r.read(), lm)
        except HTTPError as e:
            if e.code == 404:
                return result(404, b"")
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return result(e.code, b"")
        except (URLError, TimeoutError, ConnectionError):
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return result(None, b"")
    return result(None, b"")


def fetch_json(url: str, timeout: int = 30):
    code, body = http_get(url, timeout=timeout)
    if code != 200:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def iter_osv_records(eco: str):
    """Parsed advisory JSON records from data/input/<eco>/osv_raw.zip."""
    with zipfile.ZipFile(osv_zip(eco)) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                yield json.load(zf.open(name))


FALSE_POSITIVE = re.compile(r"false positive|problematic ingestion", re.I)


def is_retracted(rec: dict) -> bool:
    """OSV `withdrawn` advisory, or one whose details self-declare a false positive."""
    return bool(rec.get("withdrawn")) or bool(FALSE_POSITIVE.search(rec.get("details", "") or ""))


def earliest(prev_ts: str, ts: str) -> str:
    return min(t for t in (prev_ts, ts) if t) if (prev_ts and ts) else (prev_ts or ts)


def done_keys(path: Path, key: str = "package", skip=None) -> set:
    """Keys already present in a resumable output CSV (skip(row) -> retry that row)."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {r[key] for r in csv.DictReader(f) if skip is None or not skip(r)}


# ---------------------------------------------------------------- ecosyste.ms (06, 09)
ECOSYSTEMS_MS_API = "https://packages.ecosyste.ms/api/v1/registries"
ECOSYSTEMS_MS_REGISTRY = {"npm": "npmjs.org", "pypi": "pypi.org", "maven": "repo1.maven.org"}

# ---------------------------------------------------------------- BigQuery (07, 08)
DEPS_DEV_DATASET = "bigquery-public-data.deps_dev_v1"
DEPS_DEV_SYSTEMS = {"npm": "NPM", "pypi": "PYPI", "maven": "MAVEN"}


def bq_cmd(args: list[str], sql: str | None = None,
           timeout: int = 600) -> subprocess.CompletedProcess:
    cmd = ["bq", *args]
    if sys.platform == "win32":
        cmd = ["cmd", "/c", *cmd]
    return subprocess.run(cmd, input=sql, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout)


def bq_query(project: str, args: list[str], sql: str, timeout: int = 3600) -> str:
    """Run `bq query` with the SQL on stdin (avoids quoting issues); returns stdout."""
    r = bq_cmd(["query", f"--project_id={project}", "--use_legacy_sql=false",
                "--quiet", *args], sql=sql, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"bq failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def latest_snapshot_day(project: str) -> str:
    out = bq_query(project, ["--format=csv"],
                   f"SELECT FORMAT_TIMESTAMP('%F', MAX(Time)) FROM `{DEPS_DEV_DATASET}.Snapshots`")
    return out.strip().splitlines()[-1]
