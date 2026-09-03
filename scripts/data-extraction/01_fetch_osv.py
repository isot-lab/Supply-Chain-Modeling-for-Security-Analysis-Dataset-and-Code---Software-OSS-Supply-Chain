"""Download the OSV all-vulnerabilities dump for each ecosystem.

Input:  https://osv-vulnerabilities.storage.googleapis.com/<OSV name>/all.zip
Output: data/input/<eco>/osv_raw.zip
"""

import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import OSV_NAMES, UA, eco_parser, ecos, osv_zip

OSV_BASE = "https://osv-vulnerabilities.storage.googleapis.com"


def fetch(url: str, out: Path, chunk: int = 1 << 20) -> int:
    """Stream url to out in 1 MiB chunks; returns bytes written."""
    with urlopen(Request(url, headers=UA)) as resp, open(out, "wb") as f:
        downloaded = 0
        while block := resp.read(chunk):
            f.write(block)
            downloaded += len(block)
    return downloaded


def main() -> None:
    args = eco_parser(__doc__).parse_args()
    for eco in ecos(args):
        url = f"{OSV_BASE}/{OSV_NAMES[eco]}/all.zip"
        print(f"GET {url}")
        n = fetch(url, osv_zip(eco))
        print(f"{eco}: {n / 2**20:.1f} MB -> {osv_zip(eco)}")


if __name__ == "__main__":
    main()
