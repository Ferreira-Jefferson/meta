"""X0b -- Desloc e Cinco com zeragem no fim REAL do pregao (fim = abertura da ultima M1 do dia + 1 min).
Uso: python roda_x0b.py <WinDeslocamentoMatinal|WinCincoMedias>   (sempre continuo 2022-01-03..2025-09-30, R$1.000)
Nenhum port e' editado: o fonte e' lido, patchado em memoria e executado.
 - Desloc: zera em (fim_dia - 5 min) como o EA; fim_dia limitado a 18:25 (dias com sessao >= 18:25 ficam como no port).
 - Cinco: ZERAR = min(18:24, fim_dia - 1 min), atribuido por dia no shim de ticks."""
import os, sys
from pathlib import Path
os.environ["DADOS_VAL_MODO"] = "continuo"
AQUI = Path(__file__).resolve().parent
X0 = AQUI.parent / "x0"
sys.path.insert(0, str(X0))
import dados_val
import numpy as np, pandas as pd
BASE = AQUI.parents[2]
robo = sys.argv[1]
G = {"__name__": "__main__"}
FIM = {}
for d, g in dados_val._por_dia().items():
    FIM[d] = g.index.max().hour * 60 + g.index.max().minute + 1
class Shim:
    def __getattr__(self, k): return getattr(dados_val, k)
    def ticks(self, dia):
        if robo == "WinCincoMedias":
            G["ZERAR"] = min(18 * 60 + 24, FIM[dia] - 1)
        return dados_val.ticks(dia)
    def salvar(self, nome, trades):
        out = AQUI / "resultados_2022_2025" / f"{nome}.csv"
        pd.DataFrame(trades, columns=dados_val.COLUNAS).to_csv(out, index=False); return out
sys.modules["dados"] = Shim()
sys.path.insert(0, str(BASE))
arq = {"WinDeslocamentoMatinal": "port_deslocamento.py", "WinCincoMedias": "port_cinco_medias.py"}[robo]
src = (BASE / arq).read_text(encoding="utf-8")
if robo == "WinDeslocamentoMatinal":
    a = 't_zera = ini + (p["fim_min"] - p["zerar_min"]) * 60000'
    assert src.count(a) == 1
    src = src.replace(a, 't_zera = ini + (min(FIM_DIA[dia], p["fim_min"]) - p["zerar_min"]) * 60000')
    G["FIM_DIA"] = FIM
G["__file__"] = str(BASE / arq)
sys.argv = [arq]
print(f"[{robo}] X0b {dados_val.INICIO}..{dados_val.FIM} dias={len(dados_val.dias())}", flush=True)
exec(compile(src, str(BASE / arq), "exec"), G)
