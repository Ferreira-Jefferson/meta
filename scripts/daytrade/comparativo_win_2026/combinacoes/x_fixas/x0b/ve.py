import os, sys
os.environ["DADOS_VAL_MODO"] = "continuo"
from pathlib import Path
A = Path(__file__).resolve().parent
sys.path.insert(0, str(A.parent / "x0"))
import gera_votos_eventos as G
G.RES = A / "resultados_2022_2025"
G.V.ARQ = A / "votos_2022_2025.parquet"; G.E.ARQ_VOTOS = G.V.ARQ; G.E.ARQ = A / "eventos_2022_2025.parquet"
modo = sys.argv[1]
G.V.gerar() if modo == "votos" else G.E.gerar()
