"""Placar forward de win_deslocamento_matinal (BASE, E100, P_10_100). Idempotente.
Uso: python placar_forward.py   (qualquer cwd)"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "mm"))
import comum as c  # noqa: E402
import run_mm_multi as m  # noqa: E402

M1_CSV = HERE / "m1_win_forward.csv"
PLACAR = HERE / "PLACAR.md"
SIMBOLO_MT5 = "WIN@D"
BAIXA_DESDE = datetime(2026, 8, 15)
FWD_INI = "2026-10-01"
CSV_PESQUISA = c.DATA / "WIN@D_M1_202110010900_202610011717.csv"
VARIANTES = {
    "BASE": {},
    "E100": dict(periodos=(100,), modo="P"),
    "P_10_100": dict(periodos=(10, 100), modo="P"),
    # adicionada 2026-10-06 (decisao do dono): regra do EA em producao -- teto de stop de 10% do
    # caixa, capital CONTINUO a partir de R$1.000 (as outras sao capital reposto por pregao).
    "BASE_R10_cap1000": "risco",
    # adicionada 2026-10-06: R10 + saida por clímax de volume CONTRA (WinCincoMedias v2.01, M30,
    # mediana do mesmo horario 20 pregoes, quantil 90) -- candidata de `alvo_volume/`.
    "R10_volM30_cap1000": "volume",
}
CAPITAL_RISCO = 1000.0
RISCO_PCT = 0.10


def baixa_mt5(avisos: list) -> pd.DataFrame | None:
    try:
        import MetaTrader5 as mt5
    except Exception as e:  # noqa: BLE001
        avisos.append(f"MetaTrader5 indisponivel: {e}")
        return None
    if not mt5.initialize():
        avisos.append(f"MT5 inacessivel: {mt5.last_error()}")
        return None
    try:
        mt5.symbol_select(SIMBOLO_MT5, True)
        partes = []
        d = BAIXA_DESDE
        hoje = datetime.now().date()
        while d.date() <= hoje:
            if d.weekday() < 5:
                # dia a dia, range de 24h: janela estreita devolve barras erradas em simbolos @D
                r = mt5.copy_rates_range(SIMBOLO_MT5, mt5.TIMEFRAME_M1, d, d + timedelta(hours=24))
                if r is not None and len(r):
                    x = pd.DataFrame(r)
                    x["dt"] = pd.to_datetime(x["time"], unit="s")   # rotulo BRT (confere com o CSV)
                    partes.append(x[x["dt"].dt.date == d.date()])
            d += timedelta(days=1)
        if not partes:
            avisos.append("MT5 nao devolveu barras")
            return None
        x = pd.concat(partes).drop_duplicates("dt").sort_values("dt")
        return pd.DataFrame({"dt": x["dt"], "open": x["open"], "high": x["high"], "low": x["low"],
                             "close": x["close"], "tickvol": x["tick_volume"], "vol": x["real_volume"],
                             "spread": x["spread"]})
    finally:
        mt5.shutdown()


def salva_csv(x: pd.DataFrame):
    out = pd.DataFrame({"<DATE>": x["dt"].dt.strftime("%Y.%m.%d"), "<TIME>": x["dt"].dt.strftime("%H:%M:%S"),
                        "<OPEN>": x["open"], "<HIGH>": x["high"], "<LOW>": x["low"], "<CLOSE>": x["close"],
                        "<TICKVOL>": x["tickvol"], "<VOL>": x["vol"], "<SPREAD>": x["spread"]})
    out.to_csv(M1_CSV, sep="\t", index=False)


def confere_com_csv(x: pd.DataFrame, avisos: list):
    ref = pd.read_csv(CSV_PESQUISA, sep="\t")
    ref.columns = [k.strip("<>").lower() for k in ref.columns]
    ref["dt"] = pd.to_datetime(ref["date"] + " " + ref["time"], format="%Y.%m.%d %H:%M:%S")
    ref = ref[ref["dt"] >= "2026-09-01"].set_index("dt")
    a = x.set_index("dt")
    comum = a.index.intersection(ref.index)
    if len(comum) == 0:
        avisos.append("conferencia: sem sobreposicao com o CSV de pesquisa")
        return
    dif = 0
    for col in ("open", "high", "low", "close", "vol"):
        dif += int((a.loc[comum, col].astype(float).values != ref.loc[comum, col].astype(float).values).sum())
    msg = f"conferencia vs CSV de pesquisa: {len(comum)} barras sobrepostas, {dif} campos diferentes"
    avisos.append(msg if dif == 0 else "ATENCAO " + msg)


def roda_risco(fim: str):
    import contextlib
    import io
    from dataclasses import dataclass
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_deslocamento_matinal import WinDeslocamentoMatinal

    @dataclass
    class _W(WinDeslocamentoMatinal):
        dia_ini: object = None

        def on_bar(self, ts, bar, positions, pnl):
            a = super().on_bar(ts, bar, positions, pnl)
            return [] if a and self.dia_ini is not None and ts.date() < self.dia_ini else a

    df = c.carregar("WIN@")
    sel, dias = c.janela(df, pd.Timestamp(FWD_INI), pd.Timestamp(fim))
    perf = c.profile_for("WIN@")
    est = _W(symbol="WIN@", tick_size=perf.price_tick_size, desloc_min_atr=0.3,
             risco_max_pct=RISCO_PCT, dia_ini=dias[0])
    cfg, _ = c.montar_config("WIN@", "P2", capital=CAPITAL_RISCO, nominal=False)
    with contextlib.redirect_stdout(io.StringIO()):
        res = run_intraday_backtest(sel, est, cfg)
    tr = [t for t in res.trades if t.entry_ts.date() in set(dias)]
    return c.linhas_trades(tr), len(dias)


def roda_volume(fim: str):
    import contextlib
    import io
    sys.path.insert(0, str(HERE.parent / "alvo_volume"))
    import run_alvo_volume as av
    from backtest.intraday.engine import run_intraday_backtest

    df = c.carregar("WIN@")
    aq = c.AQUECIMENTO
    c.AQUECIMENTO = 10 ** 6          # usa todo o historico baixado como aquecimento (quantil do volume)
    try:
        sel, dias = c.janela(df, pd.Timestamp(FWD_INI), pd.Timestamp(fim))
    finally:
        c.AQUECIMENTO = aq
    perf = c.profile_for("WIN@")
    est = av.WinAV(symbol="WIN@", tick_size=perf.price_tick_size, desloc_min_atr=0.3, risco_max_pct=RISCO_PCT,
                   dia_ini=dias[0], vol_modo="quantil", vol_tf=30, vol_contra=True)
    cfg, _ = c.montar_config("WIN@", "P2", capital=CAPITAL_RISCO, nominal=False)
    with contextlib.redirect_stdout(io.StringIO()):
        res = run_intraday_backtest(sel, est, cfg)
    tr = [t for t in res.trades if t.entry_ts.date() in set(dias)]
    return c.linhas_trades(tr), len(dias)


def roda_variante(nome: str, fim: str):
    if VARIANTES[nome] == "risco":
        return roda_risco(fim)
    if VARIANTES[nome] == "volume":
        return roda_volume(fim)
    c.WinDeslocamentoMatinal = m.WinMulti
    r = c.unidade("WIN@", FWD_INI, fim, {**m.BASE, **VARIANTES[nome]}, "P2", True)
    return r["trades"], r["n_dias"]


def resumo(t: list[dict]) -> dict:
    if not t:
        return dict(n=0, liq=0.0, rop=0.0, acerto=0.0, stops=0, gan=0.0, perda=0.0, dd=0.0, fr=float("nan"))
    p = np.array([x["pnl"] for x in t])
    g, l = p[p > 0], p[p < 0]
    dd = m.dd(p)
    return dict(n=len(p), liq=p.sum(), rop=p.mean(), acerto=100 * (p > 0).mean(),
                stops=sum(x["reason"] == "STOP" for x in t), gan=g.mean() if len(g) else 0.0,
                perda=l.mean() if len(l) else 0.0, dd=dd, fr=p.sum() / dd if dd else float("nan"))


def fmt(v, d=1):
    return "—" if v != v else f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha_tab(rotulo: str, s: dict) -> str:
    return (f"|{rotulo}|{s['n']}|{fmt(s['liq'])}|{fmt(s['rop'])}|{fmt(s['acerto'])}%|{s['stops']}|"
            f"{fmt(s['gan'])}|{fmt(s['perda'])}|{fmt(s['dd'])}|{fmt(s['fr'], 2)}|")


CAB = ("|variante|trades|líquido R$|R$/op|acerto|stops|ganho médio|perda média|MaxDD R$|fator recup.|\n"
       "|---|---|---|---|---|---|---|---|---|---|")


def escreve_falha(quando, avisos):
    ant = PLACAR.read_text(encoding="utf-8") if PLACAR.exists() else ""
    ant = ant.split("\n## Execução falhou")[0]
    PLACAR.write_text(ant + f"\n## Execução falhou ({quando})\n\n" + "\n".join(f"- {a}" for a in avisos) + "\n",
                      encoding="utf-8")
    print("falhou:", avisos, flush=True)


def main():
    avisos: list[str] = []
    quando = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    x = baixa_mt5(avisos)
    if x is None:
        escreve_falha(quando, avisos)
        return
    hoje = pd.Timestamp(datetime.now().date())
    ult = x["dt"].max()
    if ult.normalize() == hoje and (ult.hour * 60 + ult.minute) < 17 * 60 + 50:
        x = x[x["dt"].dt.normalize() < hoje]
        avisos.append(f"pregao de {hoje.date()} incompleto (ultima barra {ult:%H:%M}) descartado")
    confere_com_csv(x, avisos)
    salva_csv(x)
    c.DATA = HERE
    c.ARQ["WIN@"] = M1_CSV.name
    df = c.carregar("WIN@")
    dias = sorted(d for d in set(df.index.date) if d >= pd.Timestamp(FWD_INI).date())
    if not dias:
        avisos.append("nenhum pregao completo na janela forward")
        escreve_falha(quando, avisos)
        return
    fim = str(dias[-1])
    res, ndias = {}, 0
    for nome in VARIANTES:
        t, ndias = roda_variante(nome, fim)
        res[nome] = t
        pd.DataFrame(t).to_csv(HERE / f"trades_{nome}.csv", index=False, sep=";", decimal=",")

    md = ["# Placar forward -- win_deslocamento_matinal (WIN@D)\n",
          f"Janela: {FWD_INI} a {fim} ({ndias} pregões completos). Regras em `CONGELADO_FORWARD.md`. "
          "Placar mensal só informativo; decisão formal com BASE ≥ 40 operações.\n",
          "## Total\n", CAB]
    md += [linha_tab(n, resumo(res[n])) for n in VARIANTES]
    meses = sorted({x_["entry_ts"][:7] for t in res.values() for x_ in t})
    md.append("\n## Por mês\n")
    for mes in meses:
        md += [f"\n**{mes}**\n", CAB]
        md += [linha_tab(n, resumo([x_ for x_ in res[n] if x_["entry_ts"][:7] == mes])) for n in VARIANTES]
    md.append("\n## Operações por dia\n\n|data|variante|lado|entrada|saída|motivo|R$|\n|---|---|---|---|---|---|---|")
    linhas = [(x_["entry_ts"], n, x_) for n, t in res.items() for x_ in t]
    for _, n, x_ in sorted(linhas, key=lambda z: (z[0], z[1])):
        md.append(f"|{x_['entry_ts'][:10]}|{n}|{x_['side']}|{x_['entry_ts'][11:16]} @ {x_['entry_price']:.0f}|"
                  f"{x_['exit_ts'][11:16]} @ {x_['exit_price']:.0f}|{x_['reason']}|{fmt(x_['pnl'])}|")
    md.append("\n*Horários em UTC ingênuo (BRT + 3h), como no motor.*")
    md.append("\n## Log de execução\n")
    md.append(f"- rodou em {quando}; último pregão coberto: {fim}; {ndias} pregões; M1 em `m1_win_forward.csv`")
    md += [f"- {a}" for a in avisos]
    PLACAR.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"ok {quando} ate {fim} " + " ".join(f"{n}={len(t)}" for n, t in res.items()), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        escreve_falha(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), [traceback.format_exc()[-1500:]])
        print(traceback.format_exc(), flush=True)
