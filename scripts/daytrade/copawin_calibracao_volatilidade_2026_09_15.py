# -*- coding: utf-8 -*-
"""copa_win -- LENTE 2/5: o MECANISMO da calibracao de alvo/stop pela
volatilidade, e se ele explica por que a 1a operacao do pregao morre de
stop 2,6x mais que a 2a e 3,4x mais que a 3a (fato ja medido, nao remedido
aqui: P(stop|1a)=18,8% contra 7,2%/5,6%, config de PRODUCAO, corte de
achatamento 5min, 191 pregoes, 564 trades, 58 stops).

HIPOTESE A DERRUBAR: o robo calibra `alvo_dist = alvo_vol * vol` e
`stop_dist = stop_vol * vol` (`CopaWin._entrada`) usando `vol =
CopaWin._volatilidade()` -- media de `high-low` das ultimas
`janela_rompimento` barras M1 (janela ROLANTE, nao "desde a abertura"). Na
config de PRODUCAO (`registry._KWARGS_PADRAO['copa_win']`):
`janela_rompimento=10`, `aquecimento_barras=45`. Ou seja: a janela usada
para calibrar a 1a entrada NAO e' literalmente "poucas barras" -- e' sempre
exatamente 10 barras, como em qualquer outra entrada do dia, so' que essas
10 barras caem sempre no MESMO lugar do pregao (logo depois do aquecimento,
~barras 36-45 apos a abertura) enquanto a vol de referencia das entradas
seguintes cai mais tarde no dia. A hipotese honesta, dado o codigo, nao e'
"amostra pequena" -- e' "REGIME": a vol medida logo apos a abertura pode ser
um estimador enviesado da vol do RESTO do pregao, por proximidade temporal
da abertura (leilao/repique), nao por tamanho de amostra. Isto e' testado
igual (o erro do estimador e' o mesmo objeto), so' a explicacao muda -- e a
correcao do item 4 (contraprova) usa isso: se o vies for de REGIME (abertura
sistematicamente mais/menos volatil que o resto), o dia ANTERIOR inteiro
(nao enviesado por horario) e' um estimador de referencia, e SE ele reduzir
P(stop) da 1a entrada, a hipotese de regime fica confirmada; se nao mudar
nada, fica refutada.

ANTI-LOOK-AHEAD: o unico estimador alternativo testado (item 4) usa a
volatilidade REALIZADA do PREGAO ANTERIOR (media de high-low de TODAS as
barras M1 daquele dia, ja fechado, conhecido antes da abertura de hoje).
NUNCA a volatilidade do proprio dia -- essa so' entra como REGUA de avaliacao
nos itens 1-3, nunca como insumo do robo.

Reaproveita o carregador/config de `copawin_onde_perde_2026_09_14.py` /
`copawin_encerrar_mais_cedo_2026_09_14.py` (config de PRODUCAO, capital
R$3.000, corte de achatamento 5min -- nada redigitado). Portao de capital
LIGADO (nao neutralizado) -- e' a config que roda em producao.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_calibracao_volatilidade_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL          # R$3.000 -- o que o slot usa hoje
FOLGA_PRODUCAO = 5               # corte de achatamento de producao
CORTE_OOS = pd.Timestamp("2026-06-13").date()
SYMBOL = _base.SYMBOL


def br(x, casas=2):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# classes instrumentadas -- NAO tocam strategy/daytrade/lab/copa_win.py.
# Sao subclasses que so' OBSERVAM (`CopaWinInstrumentado`) ou trocam o
# estimador da 1a entrada (`CopaWinVolDiaAnterior`), nunca a logica de
# decisao/execucao.
# ---------------------------------------------------------------------------

def _build_classes():
    from strategy.daytrade.lab.copa_win import CopaWin

    class CopaWinInstrumentado(CopaWin):
        """Grava, para cada posicao REALMENTE aberta, qual `vol` foi usada
        para calcular o alvo/stop dela. `IntradayTrade` (o registro final do
        motor) NAO carrega `metadata` da ordem que abriu a posicao -- mas a
        posicao ABERTA (`IntradayOpenPosition`, o que `on_bar` recebe) SIM
        carrega (`machine._position_view`: `metadata=dict(pos.metadata)`, e
        `_Position.metadata` e' uma copia de `order.metadata`, que
        `CopaWin._entrada` preenche com `{"vol_ref": vol, ...}`). Por isso a
        captura le' direto `pos.metadata["vol_ref"]` no primeiro `on_bar` em
        que a posicao aparece (`machine.py` confirma: o fill de uma ordem-
        limite de reteste e' resolvido ANTES de `strategy.on_bar` ser chamado
        na MESMA barra, com `current_stop`/`current_target` ainda nos
        valores ORIGINAIS da entrada -- nenhum trailing/defesa ja rodou)."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.log_entradas: list[dict] = []
            self._posicoes_logadas: set[tuple[str, pd.Timestamp]] = set()
            self._sessao_atual = None

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            self._sessao_atual = session_date
            self._posicoes_logadas = set()

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            for pos in positions:
                chave = (pos.side, pos.entry_ts)
                if chave not in self._posicoes_logadas:
                    self._posicoes_logadas.add(chave)
                    self.log_entradas.append(dict(
                        session_date=self._sessao_atual,
                        entry_ts=pos.entry_ts,
                        side=pos.side,
                        vol_ref=pos.metadata.get("vol_ref"),
                    ))
            return super().on_bar(ts, bar, positions, session_pnl_brl)

    class CopaWinVolDiaAnterior(CopaWinInstrumentado):
        """CONTRAPROVA (item 4). Substitui `_volatilidade()` pela vol
        REALIZADA do pregao ANTERIOR (`vol_dia_anterior[session_date]`, media
        de high-low de TODAS as barras M1 daquele dia -- ja fechado, portanto
        legitimo) enquanto `self._entradas_hoje == 0`, ou seja: ANTES da 1a
        entrada do pregao -- afeta o portao `vol_min_ticks`, a distancia de
        alvo/stop e o teto por risco da 1a entrada. A partir da 1a entrada
        (`_entradas_hoje >= 1`) volta ao estimador de sempre (janela rolante).
        A faixa de rompimento (`self._faixa`, os niveis teto/piso) NAO muda --
        so' o NUMERO usado para escalar alvo/stop/portao muda, que e'
        exatamente a variavel que a hipotese acusa de estar enviesada.

        Dias sem pregao anterior na amostra (o primeiro dia do historico)
        ficam sem override (`vol_dia_anterior.get(...)` devolve `None`) --
        caem no comportamento de producao, byte a byte."""

        def __init__(self, *a, vol_dia_anterior: dict, **kw):
            super().__init__(*a, **kw)
            self._vol_dia_anterior = vol_dia_anterior

        def _volatilidade(self):
            if self._entradas_hoje == 0:
                v = self._vol_dia_anterior.get(self._sessao_atual)
                if v is not None:
                    return v
            return super()._volatilidade()

    return CopaWinInstrumentado, CopaWinVolDiaAnterior


def _kwargs_producao() -> dict:
    from strategy.daytrade.registry import _KWARGS_PADRAO
    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    return kwargs


def _vol_por_dia(df: pd.DataFrame, dias: list) -> dict:
    """`date -> media(high-low)` de TODAS as barras M1 daquele pregao --
    a REGUA de avaliacao (itens 1-3) e a materia-prima do estimador
    "dia anterior" (item 4)."""
    out = {}
    idx_date = df.index.date
    for d in dias:
        sub = df[idx_date == d]
        if len(sub):
            out[d] = float((sub["high"] - sub["low"]).mean())
    return out


def _vol_resto_do_dia(df: pd.DataFrame, dia, entry_ts: pd.Timestamp) -> float | None:
    """Media de `high-low` das barras do MESMO pregao `dia`, ESTRITAMENTE
    APOS `entry_ts` (a regua de avaliacao do item 1 -- nunca usada como
    insumo do robo, so' para medir o erro do estimador a posteriori)."""
    sub = df[(df.index.date == dia) & (df.index > entry_ts)]
    if len(sub) == 0:
        return None
    return float((sub["high"] - sub["low"]).mean())


def _vol_dia_anterior_map(dias: list, vol_por_dia: dict) -> dict:
    """`date -> vol_por_dia[pregao IMEDIATAMENTE anterior NA LISTA]` -- e' o
    pregao anterior na sequencia de pregoes COMPLETOS da amostra, nao o dia
    de calendario anterior (fins de semana/feriado nao contam)."""
    out = {}
    for i in range(1, len(dias)):
        out[dias[i]] = vol_por_dia.get(dias[i - 1])
    return out


def _roda(strat_cls, kwargs_extra: dict, dias_janela: list, df: pd.DataFrame):
    from backtest.intraday.engine import run_intraday_backtest

    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    kwargs = _kwargs_producao()
    kwargs.update(kwargs_extra)
    strat = strat_cls(**kwargs)
    cfg, _corte = _base._cfg_com_folga(FOLGA_PRODUCAO, CAPITAL, strat)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def _ordinal_no_pregao(trades) -> dict:
    """`id(trade) -> 1, 2, 3...` pela ordem de ENTRADA dentro do proprio
    pregao -- mesma definicao de `copawin_onde_perde_2026_09_14.py`."""
    por_dia = defaultdict(list)
    for t in trades:
        por_dia[t.entry_ts.date()].append(t)
    ordem = {}
    for _dia, ts in por_dia.items():
        for i, t in enumerate(sorted(ts, key=lambda x: x.entry_ts), start=1):
            ordem[id(t)] = i
    return ordem


def _monta_dataset(res, strat, df: pd.DataFrame) -> pd.DataFrame:
    """Casa `strat.log_entradas` (vol_ref por posicao) com `res.trades`
    (resultado realizado) por `(side, entry_ts)`, e computa a regua de
    avaliacao (`vol_resto`, `erro`, `erro_rel`) para cada trade."""
    trades = list(res.trades)
    ordem = _ordinal_no_pregao(trades)
    log_por_chave = {(l["side"], l["entry_ts"]): l for l in strat.log_entradas}

    linhas = []
    faltando_log = 0
    faltando_resto = 0
    for t in trades:
        chave = (t.side, t.entry_ts)
        log = log_por_chave.get(chave)
        if log is None or log["vol_ref"] is None:
            faltando_log += 1
            continue
        dia = t.entry_ts.date()
        vol_resto = _vol_resto_do_dia(df, dia, t.entry_ts)
        if vol_resto is None or vol_resto <= 0:
            faltando_resto += 1
            continue
        vol_ref = log["vol_ref"]
        linhas.append(dict(
            dia=dia, entry_ts=t.entry_ts, side=t.side,
            ordinal=ordem[id(t)], exit_reason=t.exit_reason.value,
            pnl_brl=t.pnl_brl, vol_ref=vol_ref, vol_resto=vol_resto,
            erro=vol_ref - vol_resto, erro_rel=(vol_ref - vol_resto) / vol_resto,
        ))
    print(f"    ({len(trades)} trades no run | {faltando_log} sem log casado | "
          f"{faltando_resto} sem barra depois da entrada no mesmo pregao (ultimo trade do dia) "
          f"| {len(linhas)} usaveis)")
    return pd.DataFrame(linhas)


def _dispersao(serie: pd.Series) -> dict:
    s = serie.dropna()
    n = len(s)
    if n == 0:
        return dict(n=0, media=float("nan"), mediana=float("nan"),
                    dp=float("nan"), lo=float("nan"), hi=float("nan"))
    media = float(s.mean())
    dp = float(s.std(ddof=1)) if n > 1 else 0.0
    erro_pad = dp / math.sqrt(n) if n > 1 else 0.0
    return dict(n=n, media=media, mediana=float(s.median()), dp=dp,
                lo=media - 1.96 * erro_pad, hi=media + 1.96 * erro_pad)


def _welch_t(a: pd.Series, b: pd.Series) -> tuple[float, float]:
    """Welch t-test manual (sem scipy nesta maquina) + p bicaudal via
    aproximacao NORMAL (valida para os n grandes desta amostra; para n
    pequeno e' so' indicativo, marcado no relatorio)."""
    a = a.dropna().to_numpy(); b = b.dropna().to_numpy()
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan"), float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return float("nan"), float("nan")
    t = (a.mean() - b.mean()) / se
    # normal approx para o p-valor bicaudal (erf)
    p = math.erfc(abs(t) / math.sqrt(2))
    return t, p


def _fmt_dispersao(d: dict, casas=2) -> str:
    return (f"n={d['n']:>5}  media={br(d['media'],casas):>10}  "
            f"mediana={br(d['mediana'],casas):>10}  dp={br(d['dp'],casas):>9}  "
            f"IC95%media=[{br(d['lo'],casas)} ; {br(d['hi'],casas)}]")


def main() -> None:
    CopaWinInstrumentado, CopaWinVolDiaAnterior = _build_classes()

    df, dias = _base._df()
    vol_dia = _vol_por_dia(df, dias)
    vol_ontem = _vol_dia_anterior_map(dias, vol_dia)

    janelas = {
        "IS (<2026-06-13)": [d for d in dias if d < CORTE_OOS],
        "OOS (>=2026-06-13)": [d for d in dias if d >= CORTE_OOS],
    }

    print("=" * 100)
    print("copa_win -- LENTE 2/5: mecanismo da calibracao por VOLATILIDADE (config de PRODUCAO)")
    print("=" * 100)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]}) | "
          f"janela_rompimento={_kwargs_producao()['janela_rompimento']} | "
          f"aquecimento_barras={_kwargs_producao()['aquecimento_barras']} | "
          f"alvo_vol={_kwargs_producao()['alvo_vol']} | stop_vol={_kwargs_producao()['stop_vol']} | "
          f"capital R$ {br(CAPITAL,0)} | folga achatamento {FOLGA_PRODUCAO}min\n", flush=True)

    # ------------------------------------------------------------------
    # FASE 1: roda a config de PRODUCAO instrumentada, IS e OOS separados
    # ------------------------------------------------------------------
    datasets = {}
    resultados_base = {}
    for nome, dias_janela in janelas.items():
        print(f"Rodando BASELINE instrumentado -- {nome} ({len(dias_janela)} pregoes)...", flush=True)
        res, strat = _roda(CopaWinInstrumentado, {}, dias_janela, df)
        ds = _monta_dataset(res, strat, df)
        datasets[nome] = ds
        resultados_base[nome] = res
        stops = (ds["exit_reason"] == "stop").sum()
        print(f"  trades casados={len(ds)}  stops={stops}  "
              f"P(stop) geral={br(100*stops/len(ds),1) if len(ds) else '--'}%", flush=True)

    ds_soma_janelas = pd.concat(datasets.values(), ignore_index=True)

    # RUN C: HISTORICO COMPLETO como UMA UNICA simulacao continua (191 dias),
    # nao a soma das duas janelas isoladas acima. Motivo de rodar as DUAS
    # formas: o fato ja medido na missao (191 pregoes, 564 trades, 58 stops,
    # P(stop|1a)=18,8%) vem de uma corrida CONTINUA (mesmo padrao de
    # `copawin_onde_perde_2026_09_14.py`/`copawin_folga_achatamento_2026_09_
    # 14.py`, que tratam IS-sozinho/OOS-sozinho/HISTORICO-completo como TRES
    # simulacoes independentes, nao "IS + OOS"). Rodar so' as janelas
    # isoladas (acima) reinicia o caixa em R$3.000 no comeco do OOS, o que
    # muda QUANTOS DIAS o portao de capital deixa operar (a decisao de
    # ENTRAR nunca depende de caixa, mas o portao de capital e' por-DIA) --
    # por isso o total de trades pode diferir entre as duas formas mesmo
    # com a MESMA geometria. Ambas sao reportadas; a CONTINUA e' a que bate
    # com o fato ja medido.
    print(f"\nRodando BASELINE instrumentado -- HISTORICO COMPLETO CONTINUO ({len(dias)} pregoes)...",
          flush=True)
    res_hist, strat_hist = _roda(CopaWinInstrumentado, {}, dias, df)
    ds_hist = _monta_dataset(res_hist, strat_hist, df)
    stops_hist = (ds_hist["exit_reason"] == "stop").sum()
    primeira_hist = ds_hist[ds_hist["ordinal"] == 1]
    pstop1_hist = 100 * (primeira_hist["exit_reason"] == "stop").mean() if len(primeira_hist) else float("nan")
    print(f"  trades casados={len(ds_hist)}  stops={stops_hist}  "
          f"P(stop|1a)={br(pstop1_hist,1)}%  (n 1a={len(primeira_hist)})")
    print(f"  CONFERENCIA contra o fato ja medido na missao: 564 trades, 58 stops, P(stop|1a)=18,8% "
          f"-- aqui: {len(ds_hist)} trades, {stops_hist} stops, P(stop|1a)={br(pstop1_hist,1)}%")

    ds_hist_janelas = {
        "IS (continuo, pos-hoc)": ds_hist[ds_hist["dia"] < CORTE_OOS],
        "OOS (continuo, pos-hoc)": ds_hist[ds_hist["dia"] >= CORTE_OOS],
    }

    # ------------------------------------------------------------------
    # ITEM 1: erro do estimador na 1a operacao vs realizado no resto do dia
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("ITEM 1 -- erro do estimador (vol_ref usada - vol REALIZADA no resto do pregao)")
    print("erro > 0: robo calibrou GRANDE demais (alvo longe, stop longe) | "
          "erro < 0: calibrou PEQUENO demais (stop perto, morre de ruido)")
    print("(duas formas reportadas: janelas ISOLADAS -- caixa reinicia em R$3.000 no OOS -- "
          "e HISTORICO CONTINUO -- a populacao do fato ja medido)")
    print("=" * 100)
    for nome, ds in (list(datasets.items())
                     + [("SOMA janelas isoladas", ds_soma_janelas)]
                     + list(ds_hist_janelas.items())
                     + [("HISTORICO COMPLETO CONTINUO", ds_hist)]):
        for ordinal_desc, sub in [("1a operacao do dia", ds[ds["ordinal"] == 1]),
                                   ("2a operacao do dia", ds[ds["ordinal"] == 2]),
                                   ("3a operacao do dia", ds[ds["ordinal"] == 3]),
                                   ("4a+ operacao do dia", ds[ds["ordinal"] >= 4])]:
            d = _dispersao(sub["erro"])
            dr = _dispersao(sub["erro_rel"] * 100)
            print(f"  {nome:<26} {ordinal_desc:<20} erro(pts) {_fmt_dispersao(d)}   "
                  f"erro_rel%={br(dr['media'],1)}% (mediana {br(dr['mediana'],1)}%)")

    # ------------------------------------------------------------------
    # ITEM 2: o erro PREVE o stop? stop vs nao-stop, IS/OOS separados
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("ITEM 2 -- erro do estimador: STOP vs NAO-STOP (so' 1a operacao do dia), IS/OOS separados")
    print("(PRIMARIO: HISTORICO CONTINUO, pos-hoc por data -- populacao do fato ja medido; "
          "janelas ISOLADAS reportadas junto como robustez)")
    print("=" * 100)
    for nome, ds in list(ds_hist_janelas.items()) + list(datasets.items()):
        primeira = ds[ds["ordinal"] == 1]
        stop = primeira[primeira["exit_reason"] == "stop"]["erro"]
        nao_stop = primeira[primeira["exit_reason"] != "stop"]["erro"]
        d_stop = _dispersao(stop)
        d_nao = _dispersao(nao_stop)
        t, p = _welch_t(stop, nao_stop)
        print(f"\n  {nome} -- 1a operacao do dia (n={len(primeira)})")
        print(f"    STOP     : {_fmt_dispersao(d_stop)}")
        print(f"    NAO-STOP : {_fmt_dispersao(d_nao)}")
        print(f"    Welch t={br(t,3)}  p(aprox. normal, bicaudal)={br(p,4)}")

    # mesma quebra para TODAS as operacoes (nao so' a 1a), sanity check
    print("\n  (mesma quebra, TODAS as operacoes do dia, nao so' a 1a -- referencia)")
    for nome, ds in list(ds_hist_janelas.items()) + list(datasets.items()):
        stop = ds[ds["exit_reason"] == "stop"]["erro"]
        nao_stop = ds[ds["exit_reason"] != "stop"]["erro"]
        t, p = _welch_t(stop, nao_stop)
        print(f"    {nome}: STOP {_fmt_dispersao(_dispersao(stop))}")
        print(f"    {nome}: N-ST {_fmt_dispersao(_dispersao(nao_stop))}  "
              f"Welch t={br(t,3)} p={br(p,4)}")

    # ------------------------------------------------------------------
    # ITEM 3: o erro ENCOLHE conforme o dia avanca, junto com P(stop)?
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("ITEM 3 -- |erro| e P(stop) por ORDEM DA OPERACAO NO PREGAO")
    print("PRIMARIO: HISTORICO COMPLETO CONTINUO (populacao do fato ja medido)")
    print("=" * 100)
    for rotulo_ds, ds_alvo in [("HISTORICO CONTINUO", ds_hist), ("soma janelas isoladas", ds_soma_janelas)]:
        print(f"\n  -- {rotulo_ds} --")
        hdr = f"{'ordinal':<10}{'n':>6}{'P(stop)%':>10}{'media|erro|':>14}{'mediana|erro|':>15}{'dp|erro|':>10}"
        print("  " + hdr); print("  " + "-" * len(hdr))
        for k, rot in [(1, "1a"), (2, "2a"), (3, "3a"), (4, "4a+")]:
            sub = ds_alvo[ds_alvo["ordinal"] == k] if k < 4 else ds_alvo[ds_alvo["ordinal"] >= 4]
            n = len(sub)
            if n == 0:
                continue
            pstop = 100 * (sub["exit_reason"] == "stop").mean()
            abs_erro = sub["erro"].abs()
            d = _dispersao(abs_erro)
            print(f"  {rot:<10}{n:>6}{br(pstop,1):>9}%{br(d['media']):>14}{br(d['mediana']):>15}{br(d['dp']):>10}")
        corr = ds_alvo[["ordinal", "erro"]].copy()
        corr["abs_erro"] = corr["erro"].abs()
        rho = corr["ordinal"].corr(corr["abs_erro"])
        print(f"\n  correlacao (Pearson) ordinal x |erro|: {br(rho,3)}  (n={len(corr)})")
    print("\n  leitura: se |erro| encolhe com o ordinal (rho<0) NA MESMA proporcao que P(stop) "
          "cai (18,8%->7,2%->5,6%), e' evidencia a FAVOR do mecanismo; senao, refuta.")

    # ------------------------------------------------------------------
    # ITEM 4: contraprova -- vol do pregao ANTERIOR substitui a 1a entrada
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("ITEM 4 -- CONTRAPROVA: vol de referencia da 1a entrada = vol REALIZADA do pregao ANTERIOR")
    print("=" * 100)
    from backtest.intraday.report import linha_de_resultado, tabela
    EXTRAS = ("P(stop|1a)%", "n(1a)", "stops(1a)")

    resultados_cf = {}
    for nome, dias_janela in janelas.items():
        print(f"\nRodando CONTRAPROVA (vol dia anterior) -- {nome} ({len(dias_janela)} pregoes)...",
              flush=True)
        res_cf, strat_cf = _roda(CopaWinVolDiaAnterior,
                                  dict(vol_dia_anterior=vol_ontem), dias_janela, df)
        ds_cf = _monta_dataset(res_cf, strat_cf, df)
        resultados_cf[nome] = dict(res=res_cf, ds=ds_cf)

        primeira_base = datasets[nome][datasets[nome]["ordinal"] == 1]
        primeira_cf = ds_cf[ds_cf["ordinal"] == 1]
        pstop_base = 100 * (primeira_base["exit_reason"] == "stop").mean() if len(primeira_base) else float("nan")
        pstop_cf = 100 * (primeira_cf["exit_reason"] == "stop").mean() if len(primeira_cf) else float("nan")
        stops_base = int((primeira_base["exit_reason"] == "stop").sum())
        stops_cf = int((primeira_cf["exit_reason"] == "stop").sum())

        print(f"\n  {nome} -- P(stop) da 1a operacao do dia:")
        print(f"    BASELINE     : n={len(primeira_base):>4}  stops={stops_base:>3}  "
              f"P(stop)={br(pstop_base,1)}%")
        print(f"    CONTRAPROVA  : n={len(primeira_cf):>4}  stops={stops_cf:>3}  "
              f"P(stop)={br(pstop_cf,1)}%")

        extras_base = {"P(stop|1a)%": br(pstop_base, 1), "n(1a)": str(len(primeira_base)),
                       "stops(1a)": str(stops_base)}
        extras_cf = {"P(stop|1a)%": br(pstop_cf, 1), "n(1a)": str(len(primeira_cf)),
                     "stops(1a)": str(stops_cf)}
        linhas = [
            linha_de_resultado("baseline (janela rolante)", resultados_base[nome], CAPITAL,
                                extras=extras_base),
            linha_de_resultado("contraprova (vol dia anterior)", res_cf, CAPITAL,
                                extras=extras_cf),
        ]
        print("\n" + tabela(linhas, extras=EXTRAS))

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
