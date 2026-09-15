"""copa_win: as cinco perguntas do banco que ainda nao tinham sido tocadas.

Contexto. Vinte celulas de regra de gestao (limiar de MAE, recencia,
estagnacao, devolucao proporcional, cruzamentos) sairam TODAS negativas no
IS. O mecanismo ficou claro na decomposicao do MAE: cortar um trade que
sofre converte perda RECUPERAVEL em perda REALIZADA, e o vencedor vale muito
mais que o perdedor salvo. As cinco abaixo nao sao variacoes desse tema.

  Q22 STOP NA ENTRADA -- ao tocar x do alvo, move o stop para o preco de
      entrada. E' a unica alavanca do banco que NAO paga derrapagem nem fila
      (`AdjustStop` ja existe no motor e so' aperta), e o mapa Q27 mostrou
      que so' 2 dos 182 alvos sofreram >=50% do stop: a populacao que a
      regra mataria e' minuscula. A candidata mais promissora.

  Q1  CONTRAFACTUAL DAS SAIDAS POR SINAL -- na base LIVRE (as duas regras
      desligadas) sabemos em que instante o `corte_persistencia` e a
      `defesa` TERIAM disparado, e o que o trade virou sem elas. Responde
      direto: as saidas por sinal (+R$97/trade em producao) estao trocando
      stop cheio por prejuizo pequeno, ou estao abortando alvo?

  Q7  POSICAO DO FECHAMENTO NA BARRA (CLV) -- a unica variavel do banco
      estruturalmente desacoplada de "ja estou perdendo": mede pressao
      DENTRO do minuto, nao deslocamento. Se algo tem chance de acrescentar
      informacao alem de `u(tau)`, e' ela.

  Q4  O CAMINHO ATE tau PREVE O SINAL DO RESULTADO? -- versao honesta:
      sobre a coorte ainda ABERTA em tau (nao condicionada ao desfecho, que
      seria olhar o futuro), o caminho ate ali separa quem termina positivo?

  Q21 WDO COMO VARIAVEL EXOGENA -- o dolar futuro andando no mesmo intervalo
      acrescenta informacao que a trajetoria do WIN nao contem?

Convencoes de sempre: base PRODUCAO para o que vira regra (o ganho e' o
INCREMENTO sobre as regras ja ligadas), execucao na BARRA SEGUINTE, 1 tick +
tarifa, e delta positivo no IS **e** no OOS -- seis sign-flips ja apareceram.
"""
from __future__ import annotations

from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
TICK_PTS, PONTO_BRL, TARIFA_BRL = 5.0, 0.20, 0.50
CORTE_OOS = pd.Timestamp("2026-06-13")


def br(x, casas=2):
    if pd.isna(x):
        return "-"
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def mw(a, b):
    """Mann-Whitney z/p bicaudal, aproximacao normal."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan, np.nan
    todos = np.concatenate([a, b])
    r = pd.Series(todos).rank().to_numpy()
    u = r[:len(a)].sum() - len(a) * (len(a) + 1) / 2
    mu = len(a) * len(b) / 2
    _, c = np.unique(todos, return_counts=True)
    n = len(todos)
    var = len(a) * len(b) / 12 * ((n + 1) - (c ** 3 - c).sum() / (n * (n - 1)))
    if var <= 0:
        return np.nan, np.nan
    z = (u - mu) / sqrt(var)
    return z, 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))


def auc(y, s):
    y, s = np.asarray(y, bool), np.asarray(s, float)
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(np.concatenate([s[y], s[~y]])).rank().to_numpy()
    u = r[:y.sum()].sum() - y.sum() * (y.sum() + 1) / 2
    return u / (y.sum() * (~y).sum())


# ---------------------------------------------------------------- Q22
def q22(tr, ba):
    print("\n" + "=" * 118)
    print("Q22 -- STOP NA ENTRADA ao tocar x do alvo (a alavanca que nao paga fila)")
    print("=" * 118)
    ba = ba.sort_values(["trade_id", "bar_idx"])
    hdr = (f"{'x (frac. alvo)':>16}{'armados':>9}{'acionados':>11}{'v.mortos':>10}"
           f"{'p.salvos':>10}{'liquido':>13}{'delta':>11}{'IS':>11}{'OOS':>11}")
    print("  " + hdr)
    print("  " + "-" * len(hdr))
    for x in (0.40, 0.50, 0.60, 0.75):
        arm = ba[ba["exc_favoravel_acum_frac_alvo"] >= x].groupby("trade_id")["bar_idx"].min()
        novos = {}
        for tid, b0 in arm.items():
            g = ba[(ba["trade_id"] == tid) & (ba["bar_idx"] > b0)]
            if g.empty:
                continue
            lado = g.iloc[0]["lado"]
            ent = float(g.iloc[0]["entry_price"])
            toca = (g["low"] <= ent) if lado == "long" else (g["high"] >= ent)
            if toca.any():
                novos[tid] = ent
        out = tr.copy()
        sinal = np.where(out["lado"] == "long", 1.0, -1.0)
        saiu = out["trade_id"].map(novos)
        custo = (TICK_PTS * PONTO_BRL + TARIFA_BRL) * out["quantity"]
        # stop na entrada e' ordem a MERCADO: sai na entrada menos 1 tick + tarifa
        out["pnl"] = np.where(saiu.notna(), -custo, out["pnl_brl"])
        out["tocado"] = saiu.notna()
        toc = out[out["tocado"]]
        d = out["pnl"].sum() - tr["pnl_brl"].sum()
        dis = (out[out["data"] < CORTE_OOS]["pnl"].sum()
               - tr[tr["data"] < CORTE_OOS]["pnl_brl"].sum())
        doos = (out[out["data"] >= CORTE_OOS]["pnl"].sum()
                - tr[tr["data"] >= CORTE_OOS]["pnl_brl"].sum())
        marca = "  <<< positivo nas DUAS" if (dis > 0 and doos > 0) else ""
        print(f"  {br(x, 2):>16}{len(arm):>9}{len(toc):>11}"
              f"{int((toc['pnl_brl'] > 0).sum()):>10}{int((toc['pnl_brl'] < 0).sum()):>10}"
              f"{br(out['pnl'].sum()):>13}{br(d):>11}{br(dis):>11}{br(doos):>11}{marca}")
    print("\n  'armados' = chegaram a tocar x do alvo. 'acionados' = depois disso voltaram")
    print("  a entrada e foram fechados no zero a zero (menos 1 tick + tarifa).")


# ---------------------------------------------------------------- Q1
def q1(trB):
    print("\n" + "=" * 118)
    print("Q1 -- o que as saidas por SINAL teriam virado? (base LIVRE, sombra das duas regras)")
    print("=" * 118)
    for col, nome in (("corte_persistencia_teria_disparado_ts", "corte_persistencia"),
                      ("defesa_teria_disparado_ts", "defesa")):
        if col not in trB.columns:
            print(f"  [{nome}] coluna ausente na base -- pulado")
            continue
        m = trB[trB[col].notna()]
        if m.empty:
            print(f"  [{nome}] nenhuma marca de sombra")
            continue
        print(f"\n  --- {nome}: teria disparado em {len(m)} trades ---")
        g = m.groupby("exit_reason").agg(n=("pnl_brl", "size"), pnl=("pnl_brl", "sum"))
        g["por_trade"] = g["pnl"] / g["n"]
        print(g.round(2).to_string())
        print(f"    total desses trades, SEM a regra: R$ {br(m['pnl_brl'].sum())} "
              f"({br(m['pnl_brl'].mean())}/trade)")
        print(f"    em PRODUCAO as saidas por sinal deram +R$97,37/trade "
              f"-> a regra {'GANHA' if m['pnl_brl'].mean() < 97.37 else 'PERDE'} "
              "valor nesta populacao")


# ---------------------------------------------------------------- Q7 / Q4
def q7_q4(tr, ba):
    print("\n" + "=" * 118)
    print("Q7/Q4 -- o caminho ate tau separa quem termina positivo? (coorte ainda ABERTA em tau)")
    print("=" * 118)
    ba = ba.sort_values(["trade_id", "bar_idx"]).copy()
    rng = (ba["high"] - ba["low"]).replace(0, np.nan)
    lado = np.where(ba["lado"] == "long", 1.0, -1.0)
    ba["clv"] = (((ba["close"] - ba["low"]) - (ba["high"] - ba["close"])) / rng) * lado
    tr = tr.set_index("trade_id")
    for tau in (10, 20):
        sub = ba[ba["minutos_desde_entrada"] <= tau]
        dur = ba.groupby("trade_id")["minutos_desde_entrada"].max()
        vivos = dur[dur > tau].index
        f = sub[sub["trade_id"].isin(vivos)].groupby("trade_id").agg(
            clv_medio=("clv", "mean"),
            pos=("pos_fechamento_norm", "last"),
            mfe=("exc_favoravel_acum_frac_alvo", "max"),
            mae=("exc_adversa_acum_frac_stop", "max"),
            frac_adv=("lado_adverso_fechamento", "mean"),
            cruz=("cruzamentos_acumulados", "max"))
        f = f.join(tr[["pnl_brl", "data", "exit_reason"]])
        f["venceu"] = f["pnl_brl"] > 0
        f["data"] = pd.to_datetime(f["data"])
        ist, oos = f[f["data"] < CORTE_OOS], f[f["data"] >= CORTE_OOS]
        print(f"\n  --- tau = {tau} min | coorte aberta: {len(f)} trades "
              f"({int(f['venceu'].sum())} terminam positivos) | IS {len(ist)} / OOS {len(oos)} ---")
        hdr = f"{'variavel':<14}{'IS AUC':>9}{'IS p':>9}{'OOS AUC':>10}{'OOS p':>9}{'direcao':>10}"
        print("  " + hdr)
        print("  " + "-" * len(hdr))
        for c in ["clv_medio", "pos", "mfe", "mae", "frac_adv", "cruz"]:
            ai = auc(ist["venceu"].to_numpy(bool), ist[c].to_numpy())
            ao = auc(oos["venceu"].to_numpy(bool), oos[c].to_numpy())
            _, pi = mw(ist.loc[ist["venceu"], c], ist.loc[~ist["venceu"], c])
            _, po = mw(oos.loc[oos["venceu"], c], oos.loc[~oos["venceu"], c])
            dirr = "SIM" if (np.sign(ai - 0.5) == np.sign(ao - 0.5)) else "INVERTE"
            print(f"  {c:<14}{br(ai, 3):>9}{br(pi, 4):>9}{br(ao, 3):>10}{br(po, 4):>9}{dirr:>10}")
        print("  (AUC 0,5 = moeda. `pos`/`mae`/`mfe` sao o baseline trivial 'ja estou ganhando';")
        print("   `clv_medio` e' a unica desacoplada disso -- e' nela que mora a pergunta.)")


# ---------------------------------------------------------------- Q21
def q21(tr, ba):
    print("\n" + "=" * 118)
    print("Q21 -- o WDO andando no mesmo intervalo acrescenta informacao?")
    print("=" * 118)
    p = ROOT / "data" / "raw_intraday" / "WDO_A_.parquet"
    if not p.exists():
        print("  parquet do WDO ausente -- pulado")
        return
    w = pd.read_parquet(p)[["close"]].rename(columns={"close": "wdo"})
    w.index = pd.to_datetime(w.index, utc=True)
    tr = tr.copy()
    tr["entry_ts"] = pd.to_datetime(tr["entry_ts"], utc=True)
    tr["exit_ts"] = pd.to_datetime(tr["exit_ts"], utc=True)
    # `merge_asof` exige a chave ORDENADA em cada chamada -- a segunda usava
    # `exit_ts` como chave num quadro ordenado por `entry_ts`, o que quebrava.
    w = w.sort_index()
    por_ent = pd.merge_asof(tr.sort_values("entry_ts"), w, left_on="entry_ts",
                            right_index=True, direction="backward")[["trade_id", "wdo"]]
    por_sai = pd.merge_asof(tr.sort_values("exit_ts"), w, left_on="exit_ts",
                            right_index=True, direction="backward")[["trade_id", "wdo"]]
    t = tr.merge(por_ent.rename(columns={"wdo": "wdo_ent"}), on="trade_id")
    t = t.merge(por_sai.rename(columns={"wdo": "wdo_sai"}), on="trade_id")
    t["wdo_ret"] = (t["wdo_sai"] / t["wdo_ent"] - 1.0) * 100.0
    t["venceu"] = t["pnl_brl"] > 0
    t["data"] = pd.to_datetime(t["data"])
    print(f"  n com dado de WDO: {int(t['wdo_ret'].notna().sum())} de {len(t)}")
    for nome, s in (("IS", t[t["data"] < CORTE_OOS]), ("OOS", t[t["data"] >= CORTE_OOS])):
        a = auc(s["venceu"].to_numpy(bool), s["wdo_ret"].fillna(0).to_numpy())
        _, pp = mw(s.loc[s["venceu"], "wdo_ret"], s.loc[~s["venceu"], "wdo_ret"])
        med_v = s.loc[s["venceu"], "wdo_ret"].median()
        med_p = s.loc[~s["venceu"], "wdo_ret"].median()
        print(f"  {nome}: AUC {br(a, 3)}  p {br(pp, 4)}  | retorno WDO mediano: "
              f"vencedor {br(med_v, 3)}%  perdedor {br(med_p, 3)}%")
    print("\n  CUIDADO: o retorno do WDO no intervalo do trade e' CONTEMPORANEO, nao anterior --")
    print("  isto e' DIAGNOSTICO (explica), nao preditor (nao antecipa). Viraria preditor so' na")
    print("  forma 'WDO nos primeiros N minutos preve o resto', que exige outra montagem.")


def main():
    trA = pd.read_csv(SCRATCH / "copawin_trajetoria_trades_producao_2026_09_15.csv")
    baA = pd.read_csv(SCRATCH / "copawin_trajetoria_barras_producao_2026_09_15.csv")
    trB = pd.read_csv(SCRATCH / "copawin_trajetoria_trades_livre_2026_09_15.csv")
    trA["data"] = pd.to_datetime(trA["data"])
    print("=" * 118)
    print("copa_win -- AS CINCO PERGUNTAS RESTANTES DO BANCO DE TRAJETORIA")
    print("=" * 118)
    print(f"base PRODUCAO {len(trA)} trades (liquido R$ {br(trA['pnl_brl'].sum())}) | "
          f"base LIVRE {len(trB)} trades")
    q22(trA, baA)
    q1(trB)
    q7_q4(trA, baA)
    q21(trA, baA)
    print("\n\nFIM.")


if __name__ == "__main__":
    main()
