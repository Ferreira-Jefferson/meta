import subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
A = Path(__file__).resolve().parent
jobs = [(r,tf,per) for tf in (1,2,3,10,15,30) for r in ("Win","Win_c1") for per in ("2026","2225")]
def go(j):
    r,tf,per = j
    if (A/"trades"/f"{r}_M{tf}_{per}.csv").exists(): return j,"ja existe"
    o = subprocess.run([sys.executable, str(A/"roda_y1.py"), r, str(tf), per], capture_output=True, text=True)
    return j, (o.stdout+o.stderr).strip()[-300:]
with ThreadPoolExecutor(2) as ex:
    fs=[ex.submit(go,j) for j in jobs]
    for f in as_completed(fs): print(*f.result(), flush=True)
print("FIM", flush=True)
