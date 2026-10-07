"""VALIDACAO da rodada f (candle/figuras/indicadores) — lista CONGELADA antes de tocar 2025:
  base v2.02; f1: saida_pavio0.5_rng1.0, saida_pavio0.6_rng0.75; f2: nenhuma;
  f3: ST_H1_SAIDA, ADX_DI_ENTRADA, COMBO.
Etapa 1 (2025, rodada uma vez). Criterio fixado antes: liquido 2025 > base E janelas+ >= base.
Etapa 2 (WIN@ 2022-2024, NUNCA usado nesta estrategia): so' quem passou na etapa 1, ao lado da base, uma vez.
Cada familia roda em processo proprio (f1 e f3 trocam w.simula por copias com gancho).
Uso: python validacao_blocos.py <familia> <ano> [<ano>...]  -> imprime JSON por linha."""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import win_cinco_medias as w

w.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"; w.FIM_DADOS[2025] = "2025-10-01"
for a in (2022, 2023, 2024):
    w.ARQUIVOS[a] = "WIN@_M1_202112010900_202412301824.csv"

fam, anos = sys.argv[1], [int(x) for x in sys.argv[2:]]
if fam == "base":
    C = {"v2.02 (atual)": lambda ano, d: w.rodar_janelas(ano, dados=d)[1]}
elif fam == "f1":
    import f1_candidatas as m; C = m.CANDIDATAS
elif fam == "f3":
    import f3_candidatas as m; C = m.CANDIDATAS
import os
if os.environ.get("SO"):
    C = {k: v for k, v in C.items() if k == os.environ["SO"]}
cache = {}
for ano in anos:
    arq = w.ARQUIVOS[ano]
    if arq not in cache:
        cache.clear(); cache[arq] = w.carregar(ano)
    d = cache[arq]
    for nome, fn in C.items():
        r = fn(ano, d)
        print(json.dumps(dict(familia=fam, ano=ano, nome=nome, **{k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()})), flush=True)
