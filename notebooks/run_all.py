"""Execute the experiment notebooks for one or all ecosystems.

  python notebooks/run_all.py --eco all --parallel
  python notebooks/run_all.py --eco maven --only 01 04

Sets ECO in the kernel environment; executed copies (with outputs) are written to
data/output/<eco>/notebooks/. Requires the repo venv (nbclient, ipykernel).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

NB_DIR = Path(__file__).resolve().parent
ECOS = ("npm", "pypi", "maven")
ORDER = [
    ("01", "01_data_preparation"),
    ("02", "02_model_training"),
    ("03", "03_adversarial_robustness"),
    ("04", "04_Noisy_OR"),
    ("05", "05_Warfield_Exploration"),
    ("06", "06_Metadata_scarcity"),
    ("07", "07_temporal_validation"),
    ("08", "08_case_study_2026"),
]
OUT_DIRS = {
    "01": "01_data_prep", "02": "02_model_training", "03": "03_adversarial_robustness",
    "04": "04_noisy-or-sweep", "05": "05_warfield_exploration", "06": "06_metadata_scarcity",
    "07": "07_temporal_validation", "08": "08_case_study_2026",
}


def run_eco(eco, only, clean):
    import nbformat
    from jupyter_client.manager import KernelManager
    from nbclient import NotebookClient

    os.environ["ECO"] = eco
    os.environ["PYTHONUTF8"] = "1"
    out_root = NB_DIR.parent / "data" / "output" / eco
    exec_dir = out_root / "notebooks"
    exec_dir.mkdir(parents=True, exist_ok=True)
    todo = [(num, name) for num, name in ORDER if not only or num in only]
    if clean:
        for num, _ in todo:
            d = out_root / OUT_DIRS[num]
            if d.exists():
                shutil.rmtree(d)
    n_checks = 0
    for num, name in todo:
        nb = nbformat.read(NB_DIR / f"{name}.ipynb", as_version=4)
        km = KernelManager(kernel_name="python3")
        km.kernel_cmd = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        client = NotebookClient(nb, km=km, timeout=None,
                                resources={"metadata": {"path": str(NB_DIR)}})
        t0 = time.time()
        print(f"[{eco}] {name} ...", flush=True)
        client.execute()
        nbformat.write(nb, exec_dir / f"{name}.ipynb")
        checks = 0
        for cell in nb.cells:
            for out in cell.get("outputs", []):
                text = out.get("text", "")
                if isinstance(text, list):
                    text = "".join(text)
                checks += len(re.findall(r"^\[\d+\]", text, re.M))
        n_checks += checks
        print(f"[{eco}] {name} done in {(time.time()-t0)/60:.1f} min "
              f"({checks} checks)", flush=True)
    print(f"[{eco}] complete: {n_checks} verification checks printed", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eco", choices=[*ECOS, "all"], required=True)
    ap.add_argument("--only", nargs="*", default=None, help="notebook numbers, e.g. 01 04")
    ap.add_argument("--clean", action="store_true",
                    help="delete each target output dir before running")
    ap.add_argument("--parallel", action="store_true",
                    help="run the ecosystems as separate processes")
    args = ap.parse_args()
    ecos = list(ECOS) if args.eco == "all" else [args.eco]

    if args.parallel and len(ecos) > 1:
        procs = {}
        for eco in ecos:
            cmd = [sys.executable, str(Path(__file__).resolve()), "--eco", eco]
            if args.only:
                cmd += ["--only", *args.only]
            if args.clean:
                cmd += ["--clean"]
            env = {**os.environ, "PYTHONUTF8": "1"}
            procs[eco] = subprocess.Popen(cmd, env=env)
        rc = {eco: p.wait() for eco, p in procs.items()}
        print(f"exit codes: {rc}")
        sys.exit(max(rc.values()))
    for eco in ecos:
        run_eco(eco, args.only, args.clean)


if __name__ == "__main__":
    main()
