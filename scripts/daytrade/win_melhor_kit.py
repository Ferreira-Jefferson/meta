"""Kit comum para testar melhorias sobre a MELHOR ATUAL do WIN (2026-10-06).

Uso:
    import importlib.util as u
    s = u.spec_from_file_location("kit", ".../win_melhor_kit.py"); kit = ...
    m5 = kit.carregar_m5()                         # WIN@ sem ajuste, M5, 2026
    res = kit.rodar_meses(m5, **hooks)             # mesma janela mes a mes do baseline
    print(kit.tabela_meses(res)); print(kit.resumo(res))

hooks = permite_long/permite_short/qtd_long/qtd_short — FUNCOES f(seg) que
recebem o DataFrame M5 do contrato (colunas o,h,l,c,vol; indice = inicio da
barra) e devolvem array alinhado a seg.index. A decisao vale para a barra do
SINAL; so' pode usar informacao ate o FECHAMENTO dessa barra (sem look-ahead).

Regras do motor (nao mudar): entrada limite no fechamento do sinal, TTL 5
barras; saida a mercado na abertura da barra seguinte a quebra do
alinhamento (1 tick de deslize); R$0,50/contrato ida+volta; 1 pt = R$0,20;
zera no fim do pregao. Cada janela comeca com R$1.000.
"""
import importlib.util as u
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
_s = u.spec_from_file_location("win_base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(_s); _s.loader.exec_module(b)

DADOS = b.RAIZ / "data" / "wdo-mt5"
ROLAGENS = ["2026-01-02", "2026-02-19", "2026-04-16", "2026-06-18", "2026-08-13", "2026-10-02"]
CONTRATO = ["WING26", "WINJ26", "WINM26", "WINQ26", "WINV26"]
COLS = ["pnl", "dia", "pts", "t", "lado", "t_saida", "qty"]


def carregar_m5() -> pd.DataFrame:
    p = DADOS / "WIN@_M1_202601020900_202610051831.csv"
    d = pd.read_csv(p, sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"OPEN": "o", "HIGH": "h", "LOW": "l", "CLOSE": "c", "VOL": "vol"})[["o", "h", "l", "c", "vol"]]
    return d.resample("5min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "vol": "sum"}).dropna()


def segmentos(m5):
    """(contrato, seg, ini_op): EMAs recomecam na rolagem; opera do 3o pregao."""
    for k, nome in enumerate(CONTRATO):
        seg = m5[ROLAGENS[k]:pd.Timestamp(ROLAGENS[k + 1]) - pd.Timedelta(minutes=1)]
        dias = sorted(set(seg.index.normalize()))
        if len(dias) >= 4:
            yield nome, seg, dias[3], dias[-1]


def rodar_meses(m5, permite_long=None, permite_short=None, qtd_long=None, qtd_short=None, **kw):
    """Roda a MELHOR (com os hooks) nas mesmas 14 janelas do baseline.
    kw sobrescreve MELHOR (ex.: periodos=...). Devolve lista de dicts."""
    cfg = dict(b.MELHOR); cfg.update(kw)
    out = []
    for nome, seg, ini_op, ult in segmentos(m5):
        h = {k: (f(seg) if f is not None else None) for k, f in
             (("permite_long", permite_long), ("permite_short", permite_short),
              ("qtd_long", qtd_long), ("qtd_short", qtd_short))}
        for mes in pd.period_range(ini_op, ult, freq="M"):
            a = max(ini_op, mes.start_time); z = min(mes.end_time, ult + pd.Timedelta(days=1))
            tr, eq = b.simula(seg, ini=a, fim=z, **cfg, **h)
            jan = seg[a:z]
            if not len(jan):
                continue
            df = pd.DataFrame(tr, columns=COLS)
            out.append(dict(janela=f"{mes} {nome} {a:%d}-{jan.index[-1]:%d}", contrato=nome,
                            mercado_pts=float(jan.c.iloc[-1] - jan.o.iloc[0]), trades=df, eq=eq))
    return out


def tabela_meses(res, extras=("mercado pts", "PF", "pts/op", "BE emp%", "compras R$", "vendas R$", "min caixa")):
    L = []
    for r in res:
        tr = [tuple(x) for x in r["trades"].itertuples(index=False)]
        ln = b.linha(r["janela"], tr, r["eq"])
        df = r["trades"]
        ln.extras["mercado pts"] = b.num_br(r["mercado_pts"], 0)
        ln.extras["compras R$"] = b.num_br(df.pnl[df.lado == 1].sum() if len(df) else 0)
        ln.extras["vendas R$"] = b.num_br(df.pnl[df.lado == -1].sum() if len(df) else 0)
        L.append(ln)
    return b.tabela(L, extras=extras)


def resumo(res) -> dict:
    """Numeros agregados para comparar variantes (soma das janelas)."""
    liq = [r["eq"].iloc[-1] - b.CAP0 for r in res]
    dd = [float((r["eq"].cummax() - r["eq"]).max()) for r in res]
    ddp = [float(((r["eq"].cummax() - r["eq"]) / r["eq"].cummax()).max() * 100) for r in res]
    t = pd.concat([r["trades"] for r in res]) if res else pd.DataFrame(columns=COLS)
    g, p = t.pnl[t.pnl > 0], -t.pnl[t.pnl < 0]
    return {
        "liquido_total": round(sum(liq), 2),
        "janelas_pos": f"{sum(x > 0 for x in liq)}/{len(liq)}",
        "pior_janela": round(min(liq), 2),
        "trades": len(t),
        "acerto%": round(100 * len(g) / max(len(t), 1), 1),
        "PF": round(g.sum() / p.sum(), 2) if p.sum() else None,
        "pts/op": round(t.pts.mean(), 1) if len(t) else None,
        "maior_DD_R$": round(max(dd), 2),
        "maior_DD%": round(max(ddp), 1),
        "DD_medio%": round(float(np.mean(ddp)), 1),
        "fator_recup": round(sum(liq) / max(dd), 2) if max(dd) else None,
    }


if __name__ == "__main__":
    m5 = carregar_m5()
    res = rodar_meses(m5)
    print(tabela_meses(res))
    print(resumo(res))
