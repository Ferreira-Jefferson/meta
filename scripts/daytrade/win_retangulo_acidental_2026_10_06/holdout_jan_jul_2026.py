"""Confirmacao UNICA no holdout WIN@ jan-jul/2026 dos candidatos congelados das 3 lentes.
Custo R$2/op, 1 contrato. Nenhum parametro foi escolhido olhando este periodo."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import numpy as np, pandas as pd
from sim import Cfg, carregar, simula, PONTO_RS

INI, FIM, CUSTO = "2026-01-02", "2026-08-01", 2.0
_D = None
def _ini():
    global _D; _D = carregar("WIN@2026", INI, FIM)

def fade(d, H, limite, sempre_compra=False):
    """1 op/dia: lado contra (open da barra H - open do dia). limite=True: venda/compra limite no close da
    barra H-1, valida 10 barras; senao a mercado no open da barra H. Zera no open da 1a barra >= 18:20."""
    ops = []
    for dia, g in d.groupby(d.index.date):
        m = (g.index.hour * 60 + g.index.minute).to_numpy()
        ie = np.flatnonzero(m >= H); iz = np.flatnonzero(m >= 18 * 60 + 20)
        if not len(ie) or not len(iz) or ie[0] == 0: continue
        b = ie[0]; ref = g.close.iloc[b - 1] if limite else g.open.iloc[b]
        lado = 1 if sempre_compra else (-1 if ref > g.open.iloc[0] else 1 if ref < g.open.iloc[0] else 0)
        if lado == 0: continue
        ent = None
        if limite:
            for k in range(b, min(b + 10, iz[0])):
                if (lado == -1 and g.high.iloc[k] >= ref) or (lado == 1 and g.low.iloc[k] <= ref):
                    ent = ref; break
        else:
            ent = ref
        if ent is None: continue
        ops.append(dict(dia=dia, lado=lado, pts=(g.open.iloc[iz[0]] - ent) * lado))
    return pd.DataFrame(ops)

CANDS = {
    "EA como rodou (defeito)": ("sim", Cfg(modo_defeito=True)),
    "EA tick certo 4,5L/4,5L": ("sim", Cfg()),
    "L2-F3 13h stop4,5L alvo2L": ("sim", Cfg(stop_frac=4.5, alvo_frac=2.0, primeira_entrada=780)),
    "L2-F4 13h stop3L alvo2L": ("sim", Cfg(stop_frac=3.0, alvo_frac=2.0, primeira_entrada=780)),
    "L1-B W20 11h sem prot.": ("sim", Cfg(janela=20, alvo_frac=None, stop_frac=None, primeira_entrada=660)),
    "L1-A W20 sem prot.": ("sim", Cfg(janela=20, alvo_frac=None, stop_frac=None)),
    "H1 fade abertura 11:00 mercado": ("fade", (660, False, False)),
    "H1 fade abertura 11:00 LIMITE": ("fade", (660, True, False)),
    "H2 fade abertura 11:30 LIMITE": ("fade", (690, True, False)),
    "controle compra sempre 11:00": ("fade", (660, False, True)),
}

def _roda(nome):
    kind, a = CANDS[nome]
    t = simula(_D, a) if kind == "sim" else fade(_D, *a)
    for inv in ([False, True] if kind == "sim" else [False]):
        pass
    nulo = None
    if kind == "sim":
        tn = simula(_D, replace(a, inverte=True)); nulo = float((tn.pts * PONTO_RS - CUSTO).sum()) if len(tn) else 0.0
    t["rs"] = t.pts * PONTO_RS - CUSTO; t["mes"] = pd.to_datetime(t.dia).dt.month
    # nulo de lado sorteado (mesmas entradas): percentil do real
    rng = np.random.default_rng(7); p = t.pts.to_numpy() * PONTO_RS
    sim = np.array([(p * rng.choice([-1, 1], len(p))).sum() for _ in range(5000)]) - CUSTO * len(p)
    eq = t.rs.cumsum(); dia = t.groupby("dia").rs.sum()
    return dict(nome=nome, trades=len(t), rs=round(t.rs.sum()), win=round((t.rs > 0).mean() * 100),
                pior_dia=round(dia.min()), dd=round((eq.cummax() - eq).max()),
                nulo_inv=None if nulo is None else round(nulo), pct_sorteio=round((sim < t.rs.sum()).mean() * 100, 1),
                meses_pos=int((t.groupby("mes").rs.sum() > 0).sum()),
                **{f"m{m}": round(v) for m, v in t.groupby("mes").rs.sum().items()})

if __name__ == "__main__":
    d = carregar("WIN@2026", INI, FIM)
    mes = d.close.groupby(d.index.month).agg(["first", "last"])
    print("Mes (pts, 1o open->ult close):", {m: round(r["last"] - r["first"]) for m, r in mes.iterrows()}, flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=4, initializer=_ini) as ex:
        fs = [ex.submit(_roda, n) for n in CANDS]
        for f in as_completed(fs):
            r = f.result(); rows.append(r); print(r, flush=True)
    pd.DataFrame(rows).to_csv("holdout_jan_jul_2026.csv", index=False)
