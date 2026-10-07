import subprocess, sys, filecmp
from pathlib import Path
A = Path(__file__).resolve().parent; B = A.parents[1] if False else A.parents[2]
X = B/"combinacoes/x_fixas/x0b/resultados_2022_2025"
alvo = [("Win","2026",B/"resultados/Win.csv"),("Win_c1","2026",B/"resultados/Win_c1.csv"),
        ("Win","2225",X/"Win.csv"),("Win_c1","2225",X/"Win_c1.csv")]
for r,per,ref in alvo:
    subprocess.run([sys.executable, str(A/"roda_y1.py"), r, "5", per], check=True)
    novo = A/"trades"/f"{r}_M5_{per}.csv"
    print(r, per, "BYTE-IGUAL" if novo.read_bytes()==ref.read_bytes() else "DIFERE", flush=True)
