"""R1 -- RDT no HOLDOUT 2026, UMA vez, celula congelada. NAO altera n2_rdt.py: importa as funcoes de regra dele.

Adaptacao (unica): troca a fonte de dados. n2_rdt/explora_lib fazem `import dados_dev as D`; aqui o modulo
`dados_dev` e' substituido por um shim que serve `dados.m1()/ticks()/dias()` de 2026 (ticks reais desde 20/02,
sinteticos antes) e BLOCOS = 2026-01-02..2026-10-05. Mais uma adaptacao: `explora_lib.vencimentos` passa a incluir
2025-2026 (default parava em 2025; o ajuste por diferenca do ATR D1 precisa dos vencimentos de dez/25, fev/26...).
Prova de mesma regra: modo `val` roda o MESMO adaptador (shim = dados_dev real + vencimentos ampliados) e tem de dar
12 ops / +R$215 = n2_val_ops.csv.
Uso: python r1_holdout.py val | python r1_holdout.py hold
"""
import sys, types, json, hashlib
from datetime import date
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent.parent))
import numpy as np, pandas as pd

modo = sys.argv[1]
if modo == "hold":
    import dados as W
    shim = types.ModuleType("dados_dev")
    shim.BLOCOS = {"DEV": (date(2026, 1, 2), date(2026, 10, 5)), "VAL": (date(2026, 1, 2), date(2026, 10, 5))}
    shim.m1 = W.m1
    shim.dias = lambda bloco="DEV": sorted(d for d in set(W.m1().index.date) if date(2026, 1, 2) <= d <= date(2026, 10, 5))
    shim.ticks = W.ticks
    for a in ("_sinteticos", "ms", "ts", "TICK", "RS_PONTO", "CAPITAL", "COLUNAS", "trade"):
        setattr(shim, a, getattr(W, a))
    sys.modules["dados_dev"] = shim
import explora_lib as L
_orig = L.vencimentos
L.vencimentos = lambda anos=range(2021, 2027): _orig(anos)
import n2_rdt as R
import dados_dev as D

cong = json.load(open(AQUI / "n2_celula_congelada.json"))
h = hashlib.sha256((AQUI / "n2_rdt.py").read_bytes()).hexdigest()
assert h == cong["sha256"] == "ed31fee66739a54ebea4884bafc25abe645071825040b7ed07700f0e1ae1fd36", "hash"
f, ate, k = cong["f"], cong["ate"], cong["k"]
info = R.preparar()
bloco = "VAL" if modo == "val" else "DEV"
dias = D.dias(bloco)
ops, sin = R.rodar_celula(dias, info, f, ate, k)
m = R.metricas(ops, dias, sin)
print(R.linha(modo, m), flush=True)

if modo == "val":
    ref = pd.read_csv(AQUI / "n2_val_ops.csv")
    cols = ["dia", "lado", "limite", "stop", "t_ent", "t_sai", "pe", "px", "motivo", "pts"]
    a = ops.sort_values("t_sai").reset_index(drop=True)[cols].astype({"dia": str})
    b = ref.sort_values("t_sai").reset_index(drop=True)[cols].astype({"dia": str})
    print("VAL reproduz n2_val_ops.csv identico:", a.equals(b), "| ops", len(a), "liq", m["liq"], flush=True)
    sys.exit(0)

saida = AQUI / "r1_RDT_2026.csv"
assert not saida.exists(), "holdout ja rodou -- nao roda de novo"
rows = [D.trade("RDT", int(o.t_ent), int(o.t_sai), int(o.lado), 1.0, o.pe, o.px, o.motivo) for o in ops.sort_values("t_sai").itertuples()]
pd.DataFrame(rows, columns=D.COLUNAS).to_csv(saida, index=False)
print("\nPOR MES (R$ com custo R$2/op)", flush=True)
t = m["tab"].copy(); t["mes"] = pd.to_datetime(t.dia).dt.to_period("M")
tab = t.groupby("mes").agg(ops=("rs", "size"), sem_custo=("rs0", "sum"), com_custo=("rs", "sum"))
tab = tab.reindex(pd.PeriodIndex(sorted({pd.Timestamp(d).to_period("M") for d in dias}))).fillna(0)
print(tab.round(0).to_string(), flush=True)
print(f"TOTAL ops {m['ops']} sem custo {m['liq0']:.0f} com custo {m['liq']:.0f} PF {m['pf']:.2f} DD {m['dd']:.0f} caixa_min {m['caixa_min']:.0f} "
      f"quebrou {m['quebrou']} sem2 {m['sem2']:.0f} sinais {sin} real/sint ticks: ops reais {(pd.to_datetime(t.dia) >= '2026-02-20').sum()}", flush=True)
sd = [d for d in dias if d in info and R.eh_sinal(info[d], k)]
c = R.controle(dias, info, sd, f, ate, k)
pct = float((c < m["liq"]).mean() * 100)
print(f"controle 200 sorteios: media {c.mean():.0f} p50 {np.percentile(c,50):.0f} p90 {np.percentile(c,90):.0f} p95 {np.percentile(c,95):.0f} "
      f"max {c.max():.0f}; RDT {m['liq']:.0f} percentil {pct:.1f}; pior das 6 (+841): {'SUPERA' if m['liq'] > 841 else 'NAO supera'}", flush=True)
