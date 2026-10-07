import subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
AQUI = Path(__file__).resolve().parent
PY = sys.executable
KS = ["0.5", "0", "0.2", "0.3", "0.4", "0.6", "0.7", "0.8", "1.0"]
jobs = []
for k in KS:
    jobs += [(k, "2026", ""), (k, "2026", "sempos"), (k, "2022_2025", "")]
def run(j):
    k, per, sp = j
    out = AQUI / "trades" / f"k{k}_{per}{'_sempos' if sp else ''}.csv"
    if out.exists(): return f"skip {out.name}"
    r = subprocess.run([PY, str(AQUI / "roda_z5.py"), per, k] + ([sp] if sp else []), capture_output=True, text=True)
    return (r.stdout + r.stderr).strip().splitlines()[-1]
with ThreadPoolExecutor(2) as ex:
    fs = [ex.submit(run, j) for j in jobs]
    for f in as_completed(fs): print(f.result(), flush=True)
