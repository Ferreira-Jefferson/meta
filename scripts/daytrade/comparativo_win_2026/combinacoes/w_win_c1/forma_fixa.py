"""W etapa 1 -- traduz a regra C1 (tabela de frequencia walk-forward) para a forma fixa "fav >= K".

Uso: python forma_fixa.py 2026|val   (um processo por janela; v1_regras.init so' pode ser chamado uma vez)

Para cada mes da janela: tabela P(acerto | fav) treinada nos meses anteriores (sem Win_c1), limiar escolhido pela
regra da frente (comum.escolhe_limiar), e o CONJUNTO de valores de fav (0..3) que ficam acima do limiar.
Depois aplica "fav >= K" FIXO (K = 0..3) a todas as entradas do Win_c1 da janela e compara com a walk-forward.
Nada aqui escolhe K pelo resultado: so' tabela.
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

AQ = Path(__file__).resolve().parent
sys.path.insert(0, str(AQ.parent / "v_validacao" / "v1"))
import v1_regras as R  # noqa: E402

modo = sys.argv[1]
R.init(modo)
votos, eventos, res, dados = R.carrega_ctx()
comum = R.mods["comum"]

# --- a regra aprovada, exatamente como congelada
trades_wf, est = R._core_c1(votos, eventos, res, dados, com_wdo=False)

# --- reconstrucao mes a mes (mesmas funcoes)
e = R._carrega_b(eventos, False)
D, y, P = R._previsoes_b(e, ("tabela",))
p = P["tabela"]
mes = e.mes.to_numpy(); fav = D["fav"]; estr = e.estrategia.to_numpy(); rs = e.rs.to_numpy()
rsl_sel = np.where(estr != "Win_c1", rs - R.CUSTO, 0.0)
linhas = []
for mkey in R.MESES:
    m = mkey - R.MK0 + 1
    f, thr = comum.escolhe_limiar(mes, p, m, rsl_sel)
    tr = (mes < m) & (estr != "Win_c1")
    tab = {k: (y[tr & (fav == k)].sum() + 1) / ((tr & (fav == k)).sum() + 2) for k in range(4)}
    ntr = {k: int((tr & (fav == k)).sum()) for k in range(4)}
    if m < 2:
        mant = [0, 1, 2, 3]           # sem previsao (nan) -> mantem tudo
    elif f > 0:
        mant = [k for k in range(4) if tab[k] >= thr]
    else:
        mant = [0, 1, 2, 3]
    forma = "todos" if mant == [0, 1, 2, 3] else (f"fav>={min(mant)}" if mant == list(range(min(mant), 4)) else f"conjunto {mant}")
    wc = (estr == "Win_c1") & (mes == m)
    linhas.append(dict(mes=f"{(mkey - 1) // 12}-{(mkey - 1) % 12 + 1:02d}", frac=f,
                       limiar=round(thr, 4) if np.isfinite(thr) else None,
                       **{f"P(fav={k})": round(tab[k], 4) for k in range(4)},
                       **{f"n{k}": ntr[k] for k in range(4)},
                       mantidos=str(mant), forma=forma,
                       win_c1_ops=int(wc.sum()),
                       win_c1_por_fav=str([int((wc & (fav == k)).sum()) for k in range(4)])))
tm = pd.DataFrame(linhas)

# --- K fixo
jan = R.na_janela(e.entrada) & (estr == "Win_c1")
orig = R.original_janela(res, "Win_c1")
fixos = []
def resumo(nome, rsv):
    fixos.append(dict(versao=nome, ops=len(rsv), liq_sem_custo=round(float(rsv.sum()), 1),
                      liq_R2=round(float((rsv - R.CUSTO).sum()), 1)))
resumo("original (sem filtro)", orig.rs.to_numpy())
resumo("walk-forward C1 (aprovada)", trades_wf.rs.to_numpy())
for K in range(4):
    resumo(f"fav >= {K} fixo", e.rs.to_numpy()[jan & (fav >= K)])
resumo("fav em {0,3} fixo (ultimo conjunto do VAL)", e.rs.to_numpy()[jan & np.isin(fav, [0, 3])])
tf = pd.DataFrame(fixos)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(f"=== {modo}: mes a mes ===", flush=True)
print(tm.to_string(index=False), flush=True)
print(f"\n=== {modo}: K fixo x walk-forward ===", flush=True)
print(tf.to_string(index=False), flush=True)
tm.to_csv(AQ / f"forma_fixa_mes_{modo}.csv", index=False)
tf.to_csv(AQ / f"forma_fixa_k_{modo}.csv", index=False)
