"""Rodada 16 (2026-10-08): stop inicial em NIVEIS do grafico (estrutura M15, H1/H4, dia, medias) sobre a v4.
Modos por nivel N (compra; venda = espelho), colchao b em ATR do M15:
  abaixo   : stop = N - b, se N < entrada; senao pivo
  extra1   : stop = min(pivo, N - b) se 0 <= pivo - N <= 1 ATR; senao pivo  (protecao extra limitada)
  aperto   : stop = max(pivo, N - b) se N < entrada - 0,25 ATR; senao pivo  (nivel entre o pivo e a entrada)
Tambem: pular a operacao se o risco no pivo > X ATR. Movimento do stop igual a base v4 (estrutura). 2 contratos, -10 pts/op.
"""
import numpy as np
import pandas as pd
import stops as st
import mtf
import confirma


def niveis(per, f, dias):
    R = confirma.PER[per]["out"]
    b15 = pd.read_pickle(R + "barras_M15_dia.pkl")
    a1, p1 = mtf.preparar_tf(mtf.agrega(b15, b15.index.floor("60min"), "15min"))
    h = b15.index.hour; bloco = np.where(h < 13, 9, np.where(h < 17, 13, 17))
    a4, p4 = mtf.preparar_tf(mtf.agrega(b15, b15.index.normalize() + pd.to_timedelta(bloco, unit="h"), "15min"))
    e34, e72 = b15.close.ewm(span=34, adjust=False).mean(), b15.close.ewm(span=72, adjust=False).mean()
    mms72 = b15.open.rolling(72).mean()
    dia_low = b15.groupby("dia").low.min(); dia_high = b15.groupby("dia").high.max(); dias_idx = list(dia_low.index)
    out = {k: np.full(len(f), np.nan) for k in ("fundo anterior M15", "topo anterior rompido M15", "fundo do H1", "fundo do H4",
                                                 "mínima do dia", "mínima do dia anterior", "abertura do dia", "MME34 M15", "MME72 M15",
                                                 "MMS72 open M15", "MME34 H1")}
    pivs = {}
    for j, e in enumerate(f.itertuples()):
        D = dias[e.seg]; lado = e.lado; t = e.t0 - 1; tc = b15.index[e.pos] + pd.Timedelta("15min")
        if e.seg not in pivs:
            import motor
            pivs[e.seg] = motor.zigzag(D["h"], D["l"], D["atr"], 1.5)
        pv = pivs[e.seg]
        if e.i >= 2: out["fundo anterior M15"][j] = pv[e.i - 2][2]
        if e.i >= 1: out["topo anterior rompido M15"][j] = pv[e.i - 1][2]
        for nome, (a, p) in (("fundo do H1", (a1, p1)), ("fundo do H4", (a4, p4))):
            q = p[(p.quando <= tc) & (p.tipo == ("F" if lado == 1 else "T"))]
            if len(q): out[nome][j] = q.preco.iloc[-1]
        out["mínima do dia"][j] = D["l"][:t + 1].min() if lado == 1 else D["h"][:t + 1].max()
        di = dias_idx.index(D["dia"])
        if di > 0: out["mínima do dia anterior"][j] = (dia_low if lado == 1 else dia_high).iloc[di - 1]
        out["abertura do dia"][j] = D["o"][0]
        out["MME34 M15"][j] = e34.iloc[e.pos]; out["MME72 M15"][j] = e72.iloc[e.pos]; out["MMS72 open M15"][j] = mms72.iloc[e.pos]
        i1 = a1.fim.searchsorted(tc, side="right") - 1
        if i1 >= 0: out["MME34 H1"][j] = a1.ema34.iloc[i1]
    return out


def stop_ini(f, dias, N, modo, buf):
    arr = {}
    for j, e in enumerate(f.itertuples()):
        D = dias[e.seg]; lado = e.lado; t = e.t0 - 1; atr = D["atr"][t]; ent = D["c"][t]; piv = e.stop; n = N[j]
        s = piv
        if n == n:
            nb = n - lado * buf * atr
            if modo == "abaixo" and (ent - n) * lado > 0: s = nb
            elif modo == "extra1" and 0 <= (piv - n) * lado <= atr: s = (min if lado == 1 else max)(piv, nb)
            elif modo == "aperto" and (ent - n) * lado > 0.25 * atr: s = (max if lado == 1 else min)(piv, nb)
        arr[e.Index] = s
    return arr


def sim_arr(f, dias, arr):
    g = f.copy(); g["stop"] = [arr[i] for i in g.index]
    return st.simular(g, dias, {})


def main():
    res = {}
    for per in ("pesquisa", "reserva"):
        f, dias = st.preparar(per); N = niveis(per, f, dias)
        rows = [dict(var="BASE v4 (pivô)", **st.resumo(st.simular(f, dias, {})))]
        for nome, arrN in N.items():
            for modo in ("abaixo", "extra1", "aperto"):
                for buf in (0.0, 0.1):
                    rows.append(dict(var=f"{nome} | {modo} | colchão {buf}", **st.resumo(sim_arr(f, dias, stop_ini(f, dias, arrN, modo, buf)))))
        risco = f.H11.to_numpy()  # R/ATR
        for x in (2.0, 2.5, 3.0):
            rows.append(dict(var=f"pula se risco > {x} ATR", **st.resumo(st.simular(f[risco <= x], dias, {}))))
        res[per] = pd.DataFrame(rows).set_index("var")
        print(per, "ok", flush=True)
    I, O = res["pesquisa"], res["reserva"]
    t = I.join(O, lsuffix="_IS", rsuffix="_OOS")
    b = t.iloc[0]
    t["passa_IS"] = (t.total_IS > b.total_IS) & (t.t_dd_IS > b.t_dd_IS)
    t["passa_OOS"] = t.passa_IS & (t.total_OOS > b.total_OOS) & (t.t_dd_OOS > b.t_dd_OOS)
    t.to_pickle("scripts/daytrade/topos_fundos/res_conf/stops2.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    cols = ["ops_IS", "total_IS", "dd_IS", "t_dd_IS", "acerto_IS", "ops_OOS", "total_OOS", "dd_OOS", "t_dd_OOS", "passa_IS", "passa_OOS"]
    print(t[cols].sort_values("total_IS", ascending=False).round(2).to_string())


if __name__ == "__main__":
    main()
