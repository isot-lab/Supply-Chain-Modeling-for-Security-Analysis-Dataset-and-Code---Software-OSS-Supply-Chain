import csv
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import eco_parser, ecos, fetch_json, http_get, input_dir

NOW = datetime.now(timezone.utc)
DEP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")   # strips PEP 508 specifiers
DEV_SCOPES = {"test", "provided"}                        # Maven analog of devDependencies

INDEX_COLS_NPM = ["package", "version", "repo_url", "author", "author_email",
                  "maintainers", "contributors", "publisher", "publisher_email",
                  "created", "dependencies"]
INDEX_COLS_STD = ["package", "version", "repo_url", "author", "author_email",
                  "maintainers", "created", "dependencies"]

FEATURES_NPM = [
    "name_exist", "name_length",
    "dist_tags_exist", "dist_tags_length",
    "versions_exist", "versions_length", "versions_num_count",
    "maintainers_exist",
    "description_exist", "description_length",
    "readme_exist", "readme_length",
    "scripts_exist", "scripts_length",
    "author_exist", "author_name", "author_email",
    "license_exist", "license_length",
    "directories_exist", "directories_length",
    "keywords_exist", "keywords_length", "keywords_num_count",
    "homepage_exist", "homepage_length",
    "github_exist", "github_length",
    "bugslink_exist", "bugslink_length",
    "dependencies_exist", "dependencies_length",
    "devDependencies_exist", "devDependencies_length",
    "package_age_days", "package_modified_duration_days",
    "package_published_duration_days",
]
FEATURES_PYPI = [
    "name_exist", "name_length",
    "versions_exist", "versions_length", "versions_num_count",
    "maintainers_exist",
    "description_exist", "description_length",
    "readme_exist", "readme_length",
    "author_exist", "author_name", "author_email",
    "license_exist", "license_length",
    "keywords_exist", "keywords_length", "keywords_num_count",
    "homepage_exist", "homepage_length",
    "github_exist", "github_length",
    "bugslink_exist", "bugslink_length",
    "dependencies_exist", "dependencies_length",
    "package_age_days", "package_modified_duration_days",
    "package_published_duration_days",
]
FEATURES_MAVEN = [
    "name_exist", "name_length",
    "versions_exist", "versions_length", "versions_num_count",
    "description_exist", "description_length",
    "author_exist", "author_name", "author_email",
    "license_exist", "license_length",
    "homepage_exist", "homepage_length",
    "github_exist", "github_length",
    "bugslink_exist", "bugslink_length",
    "dependencies_exist", "dependencies_length",
    "devDependencies_exist", "devDependencies_length",
    "package_age_days", "package_modified_duration_days",
    "package_published_duration_days",
]


def days(a: str, b: str) -> float:
    ts = [datetime.fromisoformat(s.strip().replace("Z", "+00:00")) for s in (a, b)]
    return round((ts[1] - ts[0]).total_seconds() / 86400, 2)


def exist_length(value) -> tuple[int, int]:
    """(exist, length): char length for strings, JSON-serialized length otherwise."""
    if value is None or value == "" or value == {} or value == []:
        return 0, 0
    if isinstance(value, str):
        return 1, len(value)
    return 1, len(json.dumps(value))


def exist_length_mvn(value) -> tuple[int, int]:
    """Maven variant: entry counts for the dependency lists, char length for strings."""
    if not value:
        return 0, 0
    return 1, len(value) if isinstance(value, str) else int(value)


# ---------------------------------------------------------------------------- npm
def extract_npm(pkg: str, version: str):
    url = "https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@")
    code, body = http_get(url)
    if code != 200:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    ver = (data.get("versions") or {}).get(version)
    times = data.get("time") or {}
    if ver is None or "created" not in times or version not in times:
        return None

    def as_dict(value, str_key):
        """Normalize npm's str | dict | list-of-either field shapes."""
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, str):
            return {str_key: value}
        return value if isinstance(value, dict) else {}

    author = as_dict(ver.get("author"), "name")
    lic = ver.get("license") or ver.get("licenses") or ""
    if isinstance(lic, list):
        lic = lic[0] if lic else ""
    if isinstance(lic, dict):
        lic = lic.get("type") or ""
    if not isinstance(lic, str):
        lic = str(lic)
    repo = as_dict(ver.get("repository"), "url")
    bugs = as_dict(ver.get("bugs"), "url")
    keywords = ver.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, list):
        keywords = [str(keywords)]

    f = {}
    f["name_exist"], f["name_length"] = exist_length(pkg)
    f["dist_tags_exist"], f["dist_tags_length"] = exist_length(data.get("dist-tags"))
    n_versions = len(data.get("versions") or {})
    f["versions_exist"] = int(n_versions > 0)
    f["versions_length"] = len(version)
    f["versions_num_count"] = n_versions
    f["maintainers_exist"] = int(bool(data.get("maintainers")))
    f["description_exist"], f["description_length"] = exist_length(ver.get("description"))
    f["readme_exist"], f["readme_length"] = exist_length(data.get("readme"))
    f["scripts_exist"], f["scripts_length"] = exist_length(ver.get("scripts"))
    f["author_exist"] = int(bool(author))
    f["author_name"] = int(bool(author.get("name")))
    f["author_email"] = int(bool(author.get("email")))
    f["license_exist"], f["license_length"] = exist_length(lic)
    f["directories_exist"], f["directories_length"] = exist_length(ver.get("directories"))
    f["keywords_exist"], f["keywords_length"] = exist_length(keywords)
    f["keywords_num_count"] = len(keywords)
    f["homepage_exist"], f["homepage_length"] = exist_length(ver.get("homepage"))
    f["github_exist"], f["github_length"] = exist_length(repo.get("url"))
    f["bugslink_exist"], f["bugslink_length"] = exist_length(bugs.get("url"))
    f["dependencies_exist"], f["dependencies_length"] = exist_length(ver.get("dependencies"))
    f["devDependencies_exist"], f["devDependencies_length"] = exist_length(ver.get("devDependencies"))
    f["package_age_days"] = days(times["created"], NOW.isoformat())
    f["package_modified_duration_days"] = days(times["created"],
                                               times.get("modified") or times[version])
    f["package_published_duration_days"] = days(times["created"], times[version])

    contributors = []
    for c in ver.get("contributors") or []:
        if isinstance(c, str):
            contributors.append(c)
        elif isinstance(c, dict) and (c.get("email") or c.get("name")):
            contributors.append(c.get("email") or c.get("name"))
    npm_user = ver.get("_npmUser")                # account that ran npm publish
    if not isinstance(npm_user, dict):
        npm_user = {}

    index = {
        "repo_url": repo.get("url") or "",
        "author": author.get("name") or "",
        "author_email": author.get("email") or "",
        "maintainers": ";".join(m.get("name", "") for m in (data.get("maintainers") or [])
                                if isinstance(m, dict) and m.get("name")),
        "contributors": ";".join(contributors),
        "publisher": npm_user.get("name") or "",
        "publisher_email": npm_user.get("email") or "",
        "created": times["created"],
        "dependencies": ";".join((ver.get("dependencies") or {}).keys()),
    }
    return f, index


# ---------------------------------------------------------------------------- pypi
def extract_pypi(pkg: str, version: str):
    quoted = urllib.parse.quote(pkg)
    release = fetch_json(f"https://pypi.org/pypi/{quoted}/{urllib.parse.quote(version)}/json")
    packument = fetch_json(f"https://pypi.org/pypi/{quoted}/json")
    if release is None or packument is None:
        return None
    info = release.get("info") or {}

    times = {}
    for v, files in (packument.get("releases") or {}).items():
        uploads = [x["upload_time_iso_8601"] for x in files]
        if uploads:
            times[v] = min(uploads)
    if not times or version not in times:
        return None
    created, modified = min(times.values()), max(times.values())

    urls = {k.lower(): v for k, v in (info.get("project_urls") or {}).items() if v}
    repo = next((v for k, v in urls.items()
                 if any(w in k for w in ("source", "repository", "code", "github"))), "")
    bugs = next((v for k, v in urls.items()
                 if any(w in k for w in ("bug", "issue", "tracker"))), "")
    keywords = [k for k in (info.get("keywords") or "").replace(";", ",").split(",")
                if k.strip()]

    f = {}
    f["name_exist"], f["name_length"] = exist_length(pkg)
    f["versions_exist"] = int(len(times) > 0)
    f["versions_length"] = len(version)
    f["versions_num_count"] = len(times)
    f["maintainers_exist"] = int(bool(info.get("maintainer") or info.get("maintainer_email")))
    f["description_exist"], f["description_length"] = exist_length(info.get("summary"))
    f["readme_exist"], f["readme_length"] = exist_length(info.get("description"))
    f["author_exist"] = int(bool(info.get("author") or info.get("author_email")))
    f["author_name"] = int(bool(info.get("author")))
    f["author_email"] = int(bool(info.get("author_email")))
    f["license_exist"], f["license_length"] = exist_length(info.get("license"))
    f["keywords_exist"], f["keywords_length"] = exist_length(keywords)
    f["keywords_num_count"] = len(keywords)
    f["homepage_exist"], f["homepage_length"] = exist_length(
        info.get("home_page") or urls.get("homepage"))
    f["github_exist"], f["github_length"] = exist_length(repo)
    f["bugslink_exist"], f["bugslink_length"] = exist_length(bugs)
    f["dependencies_exist"], f["dependencies_length"] = exist_length(
        info.get("requires_dist"))
    f["package_age_days"] = days(created, NOW.isoformat())
    f["package_modified_duration_days"] = days(created, modified)
    f["package_published_duration_days"] = days(created, times[version])

    deps = []
    for d in info.get("requires_dist") or []:
        m = DEP_NAME.match(d.strip())
        if m:
            deps.append(m.group(0))
    index = {
        "repo_url": repo,
        "author": info.get("author") or "",
        "author_email": info.get("author_email") or "",
        "maintainers": info.get("maintainer") or "",
        "created": created,
        "dependencies": ";".join(dict.fromkeys(deps)),
    }
    return f, index


# ---------------------------------------------------------------------------- maven
def timeline(base: str, artifact: str):
    """(versions, created_iso, modified_iso) from maven-metadata.xml plus a HEAD on the
    first listed version's .pom (Central preserves upload time in Last-Modified)."""
    code, body, _ = http_get(f"{base}/maven-metadata.xml", last_modified=True)
    if code != 200:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    versions = [v.text for v in root.iter("version") if v.text]
    if not versions:
        return None
    lu = next((e.text for e in root.iter("lastUpdated") if e.text), "")
    modified = (datetime.strptime(lu, "%Y%m%d%H%M%S")
                .replace(tzinfo=timezone.utc).isoformat()) if lu else ""
    first = urllib.parse.quote(versions[0])
    code, _, created = http_get(
        f"{base}/{first}/{artifact}-{first}.pom", method="HEAD", last_modified=True)
    if code != 200 or not created:
        return None
    return versions, created, modified


def extract_maven(pkg: str, version: str):
    if ":" not in pkg:
        return None
    group, artifact = pkg.split(":", 1)
    base = f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{artifact}"
    quoted = urllib.parse.quote(version)
    code, body, published = http_get(f"{base}/{quoted}/{artifact}-{quoted}.pom",
                                     last_modified=True)
    if code != 200 or not published:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    tl = timeline(base, artifact)
    if tl is None:
        return None
    versions, created, modified = tl
    modified = modified or published

    def find(pattern: str) -> str:
        el = root.find(pattern)
        return (el.text or "").strip() if el is not None and el.text else ""

    deps, dev_deps = [], 0
    for dep in root.findall("{*}dependencies/{*}dependency"):
        def dep_text(tag):
            el = dep.find("{*}" + tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        if dep_text("scope") in DEV_SCOPES:
            dev_deps += 1
        elif dep_text("groupId") and dep_text("artifactId"):
            deps.append(f'{dep_text("groupId")}:{dep_text("artifactId")}')
        else:
            deps.append("")

    author = find("{*}developers/{*}developer/{*}name") or \
        find("{*}developers/{*}developer/{*}id")
    author_email = find("{*}developers/{*}developer/{*}email")
    developers = []
    for d in root.findall("{*}developers/{*}developer"):
        for tag in ("name", "id"):
            el = d.find("{*}" + tag)
            if el is not None and el.text and el.text.strip():
                developers.append(el.text.strip())
                break

    f = {}
    f["name_exist"], f["name_length"] = 1, len(pkg)
    f["versions_exist"] = int(len(versions) > 0)
    f["versions_length"] = len(version)
    f["versions_num_count"] = len(versions)
    f["description_exist"], f["description_length"] = exist_length_mvn(find("{*}description"))
    f["author_exist"] = int(bool(author or author_email))
    f["author_name"] = int(bool(author))
    f["author_email"] = int(bool(author_email))
    f["license_exist"], f["license_length"] = exist_length_mvn(
        find("{*}licenses/{*}license/{*}name"))
    f["homepage_exist"], f["homepage_length"] = exist_length_mvn(find("{*}url"))
    f["github_exist"], f["github_length"] = exist_length_mvn(
        find("{*}scm/{*}url") or find("{*}scm/{*}connection"))
    f["bugslink_exist"], f["bugslink_length"] = exist_length_mvn(
        find("{*}issueManagement/{*}url"))
    f["dependencies_exist"], f["dependencies_length"] = int(len(deps) > 0), len(deps)
    f["devDependencies_exist"], f["devDependencies_length"] = int(dev_deps > 0), dev_deps
    f["package_age_days"] = days(created, NOW.isoformat())
    f["package_modified_duration_days"] = days(created, modified)
    f["package_published_duration_days"] = days(created, published)

    index = {
        "repo_url": find("{*}scm/{*}url") or find("{*}scm/{*}connection"),
        "author": author,
        "author_email": author_email,
        "maintainers": ";".join(developers),
        "created": created,
        "dependencies": ";".join(d for d in deps if d),
    }
    return f, index


ADAPTERS = {
    "npm": (FEATURES_NPM, INDEX_COLS_NPM, extract_npm, 16),
    "pypi": (FEATURES_PYPI, INDEX_COLS_STD, extract_pypi, 16),
    "maven": (FEATURES_MAVEN, INDEX_COLS_STD, extract_maven, 8),
}


def run(eco: str, workers: int | None, limit: int | None) -> None:
    features, index_cols, extract, default_workers = ADAPTERS[eco]
    workers = workers or default_workers
    in_file = input_dir(eco) / "dataset.csv"
    out_file = input_dir(eco) / "features.csv"
    index_file = input_dir(eco) / "metadata_index.csv"

    with open(in_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    done = set()
    if out_file.exists():
        with open(out_file, encoding="utf-8") as f:
            done = {r["package"] for r in csv.DictReader(f)}
    todo = [r for r in rows if r["package"] not in done]
    print(f"{eco}: {len(rows)} rows, {len(done)} done, {len(todo)} to fetch")

    new_out, new_idx = not out_file.exists(), not index_file.exists()
    counts = {"ok": 0, "error": 0}
    with open(out_file, "a", newline="", encoding="utf-8") as f, \
            open(index_file, "a", newline="", encoding="utf-8") as fi:
        w = csv.writer(f)
        wi = csv.writer(fi)
        if new_out:
            w.writerow(["package", "version", "label", "status"] + features)
        if new_idx:
            wi.writerow(index_cols)

        def work(r):
            try:
                return r, extract(r["package"], r["version"])
            except Exception as e:                 # odd metadata shape: log, don't die
                print(f"  ! {r['package']}: {type(e).__name__}: {e}")
                return r, None

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, r) for r in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                r, res = fut.result()
                feats, idx = res if res else (None, None)
                status = "ok" if feats else "error"
                counts[status] += 1
                vals = [feats[k] for k in features] if feats else [""] * len(features)
                w.writerow([r["package"], r["version"], r["label"], status] + vals)
                if idx:
                    wi.writerow([r["package"], r["version"]] +
                                [idx[k] for k in index_cols[2:]])
                if i % 500 == 0:
                    f.flush()
                    fi.flush()
                    print(f"  {i}/{len(todo)}  {counts}")

    print(f"{eco} done: {counts} -> {out_file}")


def main() -> None:
    ap = eco_parser(__doc__)
    ap.add_argument("--workers", type=int, default=None,
                    help="default 16 (npm/pypi) or 8 (maven)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    for eco in ecos(args):
        run(eco, args.workers, args.limit)


if __name__ == "__main__":
    main()
