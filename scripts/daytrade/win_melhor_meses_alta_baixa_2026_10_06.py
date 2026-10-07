"""MELHOR ATUAL do WIN (EMA 9/21/34/100/200, saida na quebra, M5) mes a mes em
2026, separando meses de ALTA e de BAIXA. Pedido do dono, 2026-10-06: os dois
periodos testados (12-31/ago, set) foram de alta e so' as compras ganharam —
testar num mes que nao foi de alta.

Dado: WIN@ SEM ajuste baixado do MT5 (preco real do contrato principal do dia;
confere 100% com o WINV26 desde 13/08). Contratos vencidos (WINM26, WINQ26)
nao existem mais no MT5. As EMAs recomecam a cada troca de contrato (dia
seguinte ao vencimento) e o robo so' opera a partir do 3o pregao do contrato,
para o salto da rolagem nao contaminar as medias.

Tendencia diaria (so' para CLASSIFICAR as entradas): fechamento de D-1 contra a
EMA20 diaria, calculada no WIN@D (ajustado — serve para direcao, nao preco)."""
import importlib.util as u
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)
DADOS = b.RAIZ / "data" / "wdo-mt5"
ROLAGENS = ["2026-01-02", "2026-02-19", "2026-04-16", "2026-06-18", "2026-08-13", "2026-10-02"]
CONTRATO = ["WING26", "WINJ26", "WINM26", "WINQ26", "WINV26"]


def main():
    m5 = b.ler(DADOS / "WIN@_M1_202601020900_202610051831.csv", "M5")
    dd = pd.read_csv(DADOS / "WIN@D_M5_202110010900_202610011715.csv", sep="\t")
    dd.columns = [c.strip("<>") for c in dd.columns]
    dd.index = pd.to_datetime(dd.DATE + " " + dd.TIME)
    fd = dd.CLOSE.resample("D").last().dropna()
    tend_d = np.sign(fd - fd.ewm(span=20, adjust=False).mean()).shift()  # D-1 vs EMA20, conhecido na abertura de D

    linhas, todos = [], []
    for k in range(len(CONTRATO)):
        seg = m5[ROLAGENS[k]:pd.Timestamp(ROLAGENS[k + 1]) - pd.Timedelta(minutes=1)]
        dias = sorted(set(seg.index.normalize()))
        if len(dias) < 4:
            continue
        ini_op = dias[3]
        meses = pd.period_range(ini_op, dias[-1], freq="M")
        for mes in meses:
            a = max(ini_op, mes.start_time); z = min(mes.end_time, dias[-1] + pd.Timedelta(days=1))
            tr, eq = b.simula(seg, ini=a, fim=z, **b.MELHOR)
            if not tr:
                continue
            janela = seg[a:z]
            mov = janela.c.iloc[-1] - janela.o.iloc[0]
            nome = f"{mes} {CONTRATO[k]} {a:%d}-{janela.index[-1]:%d}"
            ln = b.linha(nome, tr, eq)
            df = pd.DataFrame(tr, columns=["pnl", "dia", "pts", "t", "lado", "t_saida", "qty"])
            ln.extras["mercado pts"] = b.num_br(mov, 0)
            ln.extras["regime"] = "ALTA" if mov > 0 else "BAIXA"
            ln.extras["compras R$"] = b.num_br(df.pnl[df.lado == 1].sum())
            ln.extras["vendas R$"] = b.num_br(df.pnl[df.lado == -1].sum())
            linhas.append(ln)
            df["regime"] = ln.extras["regime"]; df["janela"] = nome
            df["tend_d"] = df.t.dt.normalize().map(tend_d)
            todos.append(df)
    ex = ("mercado pts", "regime", "PF", "pts/op", "BE emp%", "compras R$", "vendas R$", "min caixa")
    print("=== MELHOR ATUAL mes a mes (cada janela comeca com R$1.000) ===", flush=True)
    print(b.tabela(linhas, extras=ex), flush=True)

    t = pd.concat(todos)
    t["lado_n"] = t.lado.map({1: "compra", -1: "venda"})
    t["vs_tend"] = np.where(t.tend_d == t.lado, "a favor", np.where(t.tend_d == -t.lado, "contra", "neutro"))

    def resumo(g):
        gan, per = g.pts[g.pts > 0], -g.pts[g.pts < 0]
        return pd.Series({"trades": len(g), "ganhos": len(gan), "perdas": len(per),
                          "acerto%": round(100 * len(gan) / len(g), 1),
                          "BE%": round(100 * per.mean() / (gan.mean() + per.mean()), 1) if len(gan) and len(per) else np.nan,
                          "pts/op": round(g.pts.mean(), 1), "liquido R$": round(g.pnl.sum(), 2)})

    pd.set_option("display.width", 200)
    print("\n=== por REGIME do mes x LADO ===", flush=True)
    print(t.groupby(["regime", "lado_n"]).apply(resumo, include_groups=False).to_string(), flush=True)
    print("\n=== por LADO x TENDENCIA DIARIA (D-1 vs EMA20 diaria) ===", flush=True)
    print(t.groupby(["lado_n", "vs_tend"]).apply(resumo, include_groups=False).to_string(), flush=True)
    print("\n=== REGIME x LADO x TENDENCIA DIARIA ===", flush=True)
    print(t.groupby(["regime", "lado_n", "vs_tend"]).apply(resumo, include_groups=False).to_string(), flush=True)


if __name__ == "__main__":
    main()
