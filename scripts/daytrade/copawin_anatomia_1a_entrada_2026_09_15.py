# -*- coding: utf-8 -*-
"""copa_win: ANATOMIA da 1a entrada do pregao -- lente 1 de 5.

PERGUNTA DO DONO (2026-09-15). O fato ja esta medido e NAO e remedido aqui
(config de PRODUCAO, corte de achatamento de producao -- folga 5min --,
191 pregoes, capital R$3.000, 564 trades): a 1a operacao de cada pregao e
191 trades (33,9% do total), concentra 36 dos 58 STOPS (62,1%), P(stop)=18,8%
contra 7,2%/5,6%/11,5%/0% da 2a/3a/4a/5a+, rende +R$2,89/trade (IS) e
-R$0,31/trade (OOS) contra +R$45 a +R$85 das demais. Pular a 1a ou proibir
horario cedo FOI TESTADO E REFUTADO -- o defeito migra pra nova 1a.

Esta lente NAO busca preditor (lente 3) nem explica o MECANISMO (lente 2) --
so' faz o RETRATO: o que e' DIFERENTE na 1a entrada, no MOMENTO DO SINAL, em
relacao a 2a/3a/4a/5a+? Compara por ORDINAL tudo que e' propriedade da
ENTRADA e CONHECIDO quando ela e' emitida.

## Por que nao da pra ler isso do `IntradayTrade`

`IntradayTrade` (`backtest.intraday.machine`) so' carrega o que sobra DEPOIS
do trade fechar (side/entry_price/exit_price/quantity/exit_reason) -- nao
carrega a volatilidade de referencia, a distancia do stop/alvo EM PONTOS (so'
da pra inferir dos precos, que ja vem arredondados por `no_tick`), quantas
barras de pregao ja tinham passado, ou o nivel de faixa rompido. Esse estado
so' existe DENTRO de `CopaWin.on_bar`/`_entrada` no INSTANTE do sinal, e
morre quando a funcao retorna.

## Como a anatomia e' capturada -- instrumentacao, nao modificacao

Este script NAO toca `strategy/daytrade/lab/copa_win.py`. Ele embrulha o
metodo `on_bar` da INSTANCIA (`types.MethodType`, so' para esta run) para: (1)
copiar `self._faixa` ANTES de chamar o `on_bar` original -- e' exatamente o
snapshot que `_entrada` usa internamente para `teto_faixa`/`piso_faixa`/`vol`,
capturado no mesmo ponto do ciclo de vida (antes do `finally` que anexa a
barra corrente); (2) chamar o `on_bar` original, sem alterar nada do que ele
decide ou retorna; (3) se a acao devolvida for `Enter`/`EnterLimit` (um
SINAL de entrada), registrar o estado inteiro (vol_ref/nivel_rompido/
stop-alvo em pontos/quantidade/barras_hoje/range e volume acumulados do
dia/penetracao alem do nivel) num log proprio, fora do `self` do robo. O
comportamento do robo -- toda decisao, todo estado interno dele -- e'
byte a byte o mesmo com ou sem a instrumentacao.

## Sinal (tentativa) x trade REALIZADO -- por que precisa casar os dois

`entrada_maker=True` na config de producao: cada sinal e' uma ORDEM-LIMITE
de reteste (`EnterLimit`) parada no nivel rompido, com prazo
`entrada_ttl_barras=5`. Ela pode NUNCA preencher (o preco nao volta em 5
barras) -- nesse caso o robo re-arma no proximo sinal, possivelmente em outro
nivel (a faixa rolou). O FATO A EXPLICAR mede ORDINAL DO TRADE REALIZADO
(`_ordinal_no_pregao`, a mesma funcao de `copawin_onde_perde_2026_09_14.py`),
entao a anatomia tem de ser lida do sinal que de fato VIROU aquele trade, nao
do primeiro sinal do dia (podem ser sinais diferentes se o 1o foi cancelado).

O robo so' abre UMA posicao por vez (o motor recusa `Enter`/`EnterLimit` com
posicao aberta) -- por isso o casamento e' SEQUENCIAL e sem ambiguidade:
percorre os sinais do dia em ordem cronologica, e cada sinal ou (a) casa com
o PROXIMO trade realizado ainda nao casado (lado bate, preco de entrada bate
com `limit_price` dentro de 1 tick, e o fill aconteceu dentro da janela
[sinal, sinal + entrada_ttl_barras barras] -- ordem-limite so' fica viva
esse tempo) ou (b) foi cancelado (nenhum trade cabe na janela) e e'
descartado sem consumir nenhum trade. Population MATCHED := trades cujo
sinal de origem foi encontrado; a tabela reporta quantos trades ficaram SEM
sinal casado (deveria ser 0 -- serve de conferencia de sanidade).

Reaproveita o carregador/construtor de config de PRODUCAO de
`copawin_encerrar_mais_cedo_2026_09_14.py` (`_df`, `_construir_estrategia`,
`_cfg_com_folga`, `CAPITAL`) -- nada e' redigitado aqui.
"""
from __future__ import annotations

import importlib.util
import statistics
import sys
import types
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL
FOLGA_PRODUCAO = 5
TETO_ORDINAL = 6  # "6a+" agrega tudo dali pra frente, mesmo teto do script de origem


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# instrumentacao: embrulha on_bar da INSTANCIA, sem tocar copa_win.py
# ---------------------------------------------------------------------------

def _instrumentar(strat) -> list:
    """Troca `strat.on_bar` por uma versao que grava um registro por SINAL de
    entrada (Enter/EnterLimit devolvido), sem mudar nenhuma decisao do robo.
    Devolve a lista (vazia no inicio, populada durante a run) onde os
    registros vao caindo, em ordem cronologica."""
    from strategy.daytrade.base import Enter, EnterLimit

    original_on_bar = type(strat).on_bar
    sinais: list[dict] = []
    # acumuladores do PROPRIO DIA (fora do `self` do robo -- o robo nao sabe
    # que isto existe e nao le nada daqui). Resetados quando o `ts.date()`
    # muda.
    estado_dia = {"data": None, "alto": float("-inf"), "baixo": float("inf"),
                  "volume": 0.0, "n_barras": 0}

    def _on_bar_instrumentado(self, ts, bar, positions, session_pnl_brl):
        dia = ts.date()
        if estado_dia["data"] != dia:
            estado_dia.update(data=dia, alto=float("-inf"), baixo=float("inf"),
                               volume=0.0, n_barras=0)
        # Atualiza com a barra CORRENTE ANTES de decidir -- e' informacao ja
        # conhecida no fechamento desta barra, a mesma que o robo usa para o
        # proprio rompimento (`bar.close`).
        estado_dia["alto"] = max(estado_dia["alto"], bar.high)
        estado_dia["baixo"] = min(estado_dia["baixo"], bar.low)
        estado_dia["volume"] += bar.volume
        estado_dia["n_barras"] += 1

        # Snapshot da faixa rolante ANTES do on_bar original -- e' EXATAMENTE
        # o que `_entrada`/`_volatilidade` usam por dentro (o `finally` do
        # metodo original so' anexa a barra corrente DEPOIS de decidir).
        faixa_antes = list(self._faixa)

        acoes = original_on_bar(self, ts, bar, positions, session_pnl_brl)

        for acao in acoes:
            if not isinstance(acao, (Enter, EnterLimit)):
                continue
            meta = acao.metadata or {}
            nivel_rompido = meta.get("nivel_rompido")
            vol_ref = meta.get("vol_ref")
            base = nivel_rompido if isinstance(acao, EnterLimit) else bar.close
            stop_dist_pts = (abs(base - acao.initial_stop)
                              if acao.initial_stop is not None else None)
            alvo_dist_pts = (abs(acao.initial_target - base)
                              if acao.initial_target is not None else None)
            teto_faixa = max((b.high for b in faixa_antes), default=None)
            piso_faixa = min((b.low for b in faixa_antes), default=None)
            largura_faixa = (teto_faixa - piso_faixa
                              if teto_faixa is not None else None)
            volume_faixa = sum(b.volume for b in faixa_antes) if faixa_antes else None
            penetracao_pts = (abs(bar.close - nivel_rompido)
                               if nivel_rompido is not None else None)
            sinais.append(dict(
                ts=ts,
                dia=dia,
                side=acao.side,
                quantity=acao.quantity,
                is_maker=isinstance(acao, EnterLimit),
                limit_price=getattr(acao, "limit_price", None),
                vol_ref=vol_ref,
                nivel_rompido=nivel_rompido,
                fechamento_sinal=bar.close,
                penetracao_pts=penetracao_pts,
                stop_dist_pts=stop_dist_pts,
                alvo_dist_pts=alvo_dist_pts,
                largura_faixa_pts=largura_faixa,
                volume_faixa=volume_faixa,
                n_barras_faixa=len(faixa_antes),
                barras_hoje=self._barras_hoje,
                entradas_hoje=self._entradas_hoje,
                cash_atual_brl=self._cash_atual_brl,
                range_dia_pts=estado_dia["alto"] - estado_dia["baixo"],
                volume_dia=estado_dia["volume"],
                n_barras_dia=estado_dia["n_barras"],
                tick_size=self.tick_size,
                point_value_brl=self.point_value_brl,
                entrada_ttl_barras=self.entrada_ttl_barras,
            ))
        return acoes

    strat.on_bar = types.MethodType(_on_bar_instrumentado, strat)
    return sinais


def _rodar_instrumentado(capital: float, folga_min: int, dias_janela: list):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    df, _ = _base._df()
    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _base._construir_estrategia()
    sinais = _instrumentar(strat)
    cfg, corte = _base._cfg_com_folga(folga_min, capital, strat)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, sinais, corte, bars.index


# ---------------------------------------------------------------------------
# casamento sinal -> trade realizado (sequencial, 1 posicao por vez)
# ---------------------------------------------------------------------------

def _casar(trades: list, sinais: list, bars_index) -> tuple[list[dict], int]:
    """Devolve (registros, n_trades_sem_sinal) -- um registro por trade
    REALIZADO, com o ordinal do trade no pregao (1-based) e a anatomia do
    sinal que o originou (`None`s se nao achou -- conferencia de sanidade).

    O prazo da ordem de reteste (`entrada_ttl_barras`) e' contado em BARRAS
    pela maquina (`IntradaySessionMachine.resting_limit_bars_waited`), NUNCA
    em tempo de relogio -- ver `machine.py` linha ~1633. Um prazo aproximado
    por minutos erra sempre que a base M1 tem um buraco (minuto sem negocio),
    porque `entrada_ttl_barras` barras podem cobrir MAIS de `entrada_ttl_
    barras` minutos de relogio. Por isso o casamento usa a posicao REAL do
    sinal dentro da sequencia de barras do PROPRIO dia (`bars_index`, o mesmo
    DataFrame que foi de fato entregue ao motor) para achar o timestamp da
    barra-prazo, em vez de somar minutos."""
    por_dia_barras: dict = defaultdict(list)
    for ts in bars_index:
        por_dia_barras[ts.date()].append(ts)
    for dia in por_dia_barras:
        por_dia_barras[dia].sort()

    por_dia_trades: dict = defaultdict(list)
    for t in trades:
        por_dia_trades[t.entry_ts.date()].append(t)
    por_dia_sinais: dict = defaultdict(list)
    for s in sinais:
        por_dia_sinais[s["dia"]].append(s)

    registros = []
    sem_sinal = 0
    for dia, ts_dia in por_dia_trades.items():
        ts_dia = sorted(ts_dia, key=lambda t: t.entry_ts)
        sg_dia = sorted(por_dia_sinais.get(dia, []), key=lambda s: s["ts"])
        barras_dia = por_dia_barras.get(dia, [])
        ti = 0
        for sg in sg_dia:
            if ti >= len(ts_dia):
                break
            trade = ts_dia[ti]
            # prazo = timestamp da barra `entrada_ttl_barras` posicoes a
            # frente da barra do sinal, dentro da sequencia REAL de barras do
            # dia (cobre buracos de liquidez) -- ou o fim do dia, se a janela
            # estourar o pregao.
            try:
                idx_sinal = barras_dia.index(sg["ts"])
            except ValueError:
                idx_sinal = None
            if idx_sinal is not None:
                idx_prazo = min(idx_sinal + sg["entrada_ttl_barras"], len(barras_dia) - 1)
                prazo = barras_dia[idx_prazo]
            else:
                prazo = sg["ts"] + pd.Timedelta(minutes=sg["entrada_ttl_barras"] + 1)
            preco_esperado = sg["limit_price"] if sg["is_maker"] else sg["fechamento_sinal"]
            tick = sg["tick_size"] or 0.01
            bate_preco = (preco_esperado is None
                          or abs(trade.entry_price - preco_esperado) <= tick + 1e-6)
            if (trade.side == sg["side"] and trade.entry_ts >= sg["ts"]
                    and trade.entry_ts <= prazo and bate_preco):
                # `fatiar_saida_alvo=True` (`exit_split_unit=1`, producao)
                # fecha uma posicao de quantity>1 em VARIAS fatias
                # independentes -- cada fatia vira o SEU PROPRIO
                # `IntradayTrade`, com o MESMO `entry_ts`/`entry_price`/`side`
                # da posicao-mae, mas exit_ts/exit_price/exit_reason PROPRIOS
                # (uma fatia pode bater no alvo e outra no stop). Sao UMA
                # decisao de entrada so' -- consome TODAS as fatias-irmas
                # (mesmo entry_ts exato) deste MESMO sinal antes de passar
                # para o proximo, senao a fatia extra ficaria "sem sinal
                # casado" (foi o que gerou 103/564 nao-casados na primeira
                # versao deste script, concentrados no HISTORICO COMPLETO --
                # onde o capital composto ao longo de 191 pregoes corridos
                # produz mais entradas com quantity>1 do que IS/OOS medidos
                # SEPARADOS, cada um recomecando do capital inicial).
                entry_ts_grupo = trade.entry_ts
                while ti < len(ts_dia) and ts_dia[ti].entry_ts == entry_ts_grupo:
                    fatia = ts_dia[ti]
                    ordinal = ti + 1
                    tempo_fill_min = (fatia.entry_ts - sg["ts"]).total_seconds() / 60.0
                    registro = dict(sg)
                    registro.update(
                        ordinal=min(ordinal, TETO_ORDINAL),
                        ordinal_real=ordinal,
                        exit_reason=fatia.exit_reason.value,
                        pnl_brl=fatia.pnl_brl,
                        tempo_fill_min=tempo_fill_min,
                        fatia_de_saida=(fatia is not trade),
                    )
                    registros.append(registro)
                    ti += 1
            # senao: sinal cancelado (nunca preencheu) -- descarta sem consumir trade
        sem_sinal += len(ts_dia) - ti
    return registros, sem_sinal


# ---------------------------------------------------------------------------
# tabelas: media/mediana/desvio/n/intervalo por ordinal
# ---------------------------------------------------------------------------

def _stats(vals: list) -> dict:
    vals = [v for v in vals if v is not None and v == v]
    n = len(vals)
    if n == 0:
        return dict(n=0, media=float("nan"), mediana=float("nan"),
                    dp=float("nan"), mini=float("nan"), maxi=float("nan"))
    return dict(
        n=n, media=statistics.fmean(vals), mediana=statistics.median(vals),
        dp=(statistics.stdev(vals) if n > 1 else 0.0),
        mini=min(vals), maxi=max(vals),
    )


def _linha_stats(rotulo: str, s: dict, casas=2) -> str:
    if s["n"] == 0:
        return f"{rotulo:<10}{'n=0':>8}"
    return (f"{rotulo:<10}n={s['n']:>4}  media={br(s['media'],casas):>11}  "
            f"mediana={br(s['mediana'],casas):>11}  dp={br(s['dp'],casas):>10}  "
            f"[{br(s['mini'],casas)} ; {br(s['maxi'],casas)}]")


def _tabela_metrica(nome: str, registros: list, campo: str, casas=2):
    print(f"\n--- {nome} (campo `{campo}`), por ORDINAL do trade no pregao ---")
    por_ord = defaultdict(list)
    por_ord_stop = defaultdict(list)
    por_ord_nao = defaultdict(list)
    for r in registros:
        v = r.get(campo)
        por_ord[r["ordinal"]].append(v)
        if r["exit_reason"] == "stop":
            por_ord_stop[r["ordinal"]].append(v)
        else:
            por_ord_nao[r["ordinal"]].append(v)
    for k in sorted(por_ord):
        rot = f"{k}a" if k < TETO_ORDINAL else f"{TETO_ORDINAL}a+"
        print(f"  ordinal {rot}:")
        print("    " + _linha_stats("TODOS", _stats(por_ord[k]), casas))
        print("    " + _linha_stats("STOP", _stats(por_ord_stop[k]), casas))
        print("    " + _linha_stats("NAO-STOP", _stats(por_ord_nao[k]), casas))


def _tabela_lado(registros: list):
    print("\n--- LADO (long/short), por ORDINAL -- %long e P(stop) por lado ---")
    por_ord = defaultdict(list)
    for r in registros:
        por_ord[r["ordinal"]].append(r)
    hdr = f"{'ordinal':<9}{'n':>6}{'%long':>8}{'P(stop)long':>13}{'P(stop)short':>14}"
    print(hdr); print("-" * len(hdr))
    for k in sorted(por_ord):
        rs = por_ord[k]
        rot = f"{k}a" if k < TETO_ORDINAL else f"{TETO_ORDINAL}a+"
        longs = [r for r in rs if r["side"] == "long"]
        shorts = [r for r in rs if r["side"] == "short"]
        pstop_l = (100 * sum(1 for r in longs if r["exit_reason"] == "stop") / len(longs)
                   if longs else float("nan"))
        pstop_s = (100 * sum(1 for r in shorts if r["exit_reason"] == "stop") / len(shorts)
                   if shorts else float("nan"))
        print(f"{rot:<9}{len(rs):>6}{br(100*len(longs)/len(rs),1)+'%':>8}"
              f"{br(pstop_l,1)+'%':>13}{br(pstop_s,1)+'%':>14}")


def _tabela_ordinal_geral(registros: list):
    print("\n--- CONTAGEM e P(stop) por ORDINAL (conferencia contra o FATO ja medido) ---")
    por_ord = defaultdict(list)
    for r in registros:
        por_ord[r["ordinal"]].append(r)
    total = len(registros)
    total_stops = sum(1 for r in registros if r["exit_reason"] == "stop")
    hdr = f"{'ordinal':<9}{'n':>6}{'% do total':>11}{'stops':>7}{'% dos stops':>12}{'P(stop)':>9}"
    print(hdr); print("-" * len(hdr))
    for k in sorted(por_ord):
        rs = por_ord[k]
        rot = f"{k}a" if k < TETO_ORDINAL else f"{TETO_ORDINAL}a+"
        stops = sum(1 for r in rs if r["exit_reason"] == "stop")
        print(f"{rot:<9}{len(rs):>6}{br(100*len(rs)/total,1)+'%':>11}"
              f"{stops:>7}{br(100*stops/total_stops,1)+'%':>12}"
              f"{br(100*stops/len(rs),1)+'%':>9}")


METRICAS = [
    ("VOLATILIDADE DE REFERENCIA (pontos, amplitude media da janela)", "vol_ref", 2),
    ("DISTANCIA DO STOP (pontos)", "stop_dist_pts", 1),
    ("DISTANCIA DO ALVO (pontos)", "alvo_dist_pts", 1),
    ("TAMANHO DA POSICAO (contratos)", "quantity", 2),
    ("BARRAS DE PREGAO JA PASSADAS (barras_hoje, no sinal)", "barras_hoje", 1),
    ("LARGURA DA FAIXA DE ROMPIMENTO (pontos, teto-piso da janela)", "largura_faixa_pts", 1),
    ("VOLUME NA JANELA DE ROMPIMENTO (contratos, acumulado)", "volume_faixa", 0),
    ("RANGE ACUMULADO DO DIA ATE O SINAL (pontos)", "range_dia_pts", 1),
    ("VOLUME ACUMULADO DO DIA ATE O SINAL (contratos)", "volume_dia", 0),
    ("PENETRACAO ALEM DO NIVEL ROMPIDO NO INSTANTE DO SINAL (pontos)", "penetracao_pts", 2),
    ("CAIXA ATUAL NO MOMENTO DO SINAL (R$)", "cash_atual_brl", 2),
    ("TEMPO ENTRE SINAL E PREENCHIMENTO (minutos)", "tempo_fill_min", 2),
]


def _relatorio_janela(nome_janela: str, registros: list, sem_sinal: int, corte):
    print("\n" + "=" * 100)
    print(f"JANELA: {nome_janela}  ({len(registros)} trades casados a um sinal; "
          f"{sem_sinal} trades SEM sinal casado -- deveria ser 0)")
    print(f"corte de achatamento: {corte} UTC (folga {FOLGA_PRODUCAO}min, producao)")
    print("=" * 100)
    if not registros:
        print("  (janela vazia)")
        return
    _tabela_ordinal_geral(registros)
    _tabela_lado(registros)
    for nome, campo, casas in METRICAS:
        _tabela_metrica(nome, registros, campo, casas)

    # tambem em R$ (pontos x point_value_brl), pra stop/alvo
    pv = registros[0]["point_value_brl"]
    print(f"\n--- DISTANCIA DO STOP E DO ALVO EM REAIS POR CONTRATO "
          f"(pontos x point_value_brl={br(pv,2)}), por ORDINAL ---")
    por_ord_stop_r = defaultdict(list)
    por_ord_alvo_r = defaultdict(list)
    for r in registros:
        por_ord_stop_r[r["ordinal"]].append(
            r["stop_dist_pts"] * pv if r["stop_dist_pts"] is not None else None)
        por_ord_alvo_r[r["ordinal"]].append(
            r["alvo_dist_pts"] * pv if r["alvo_dist_pts"] is not None else None)
    for k in sorted(por_ord_stop_r):
        rot = f"{k}a" if k < TETO_ORDINAL else f"{TETO_ORDINAL}a+"
        print(f"  ordinal {rot}:")
        print("    " + _linha_stats("stop R$", _stats(por_ord_stop_r[k])))
        print("    " + _linha_stats("alvo R$", _stats(por_ord_alvo_r[k])))


def main() -> None:
    df, dias = _base._df()
    corte_oos = pd.Timestamp("2026-06-13").date()
    janelas = [
        ("IS (<2026-06-13)", [d for d in dias if d < corte_oos]),
        ("OOS (>=2026-06-13)", [d for d in dias if d >= corte_oos]),
        ("HISTORICO COMPLETO", dias),
    ]

    print("=" * 100)
    print("copa_win -- LENTE 1/5: ANATOMIA da 1a entrada (config de PRODUCAO, "
          f"folga de achatamento {FOLGA_PRODUCAO}min, capital R$ {br(CAPITAL,0)})")
    print("=" * 100)
    print(f"{len(dias)} pregoes: {dias[0]} a {dias[-1]}")
    print("Instrumentacao: embrulha `on_bar` da INSTANCIA (types.MethodType) -- "
          "copa_win.py NAO e' tocado, e o comportamento do robo e' byte a byte "
          "identico com ou sem o embrulho.")
    print("Casamento sinal->trade: sequencial (1 posicao por vez), lado + preco "
          "(tolerancia 1 tick) + janela de tempo = [sinal, sinal + entrada_ttl_"
          "barras+1 min].\n", flush=True)

    for nome, dias_janela in janelas:
        res, sinais, corte, bars_index = _rodar_instrumentado(CAPITAL, FOLGA_PRODUCAO, dias_janela)
        trades = list(res.trades)
        registros, sem_sinal = _casar(trades, sinais, bars_index)
        print(f"\n[{nome}] {len(dias_janela)} pregoes, {len(trades)} trades, "
              f"{len(sinais)} sinais emitidos (tentativas, inclui canceladas)",
              flush=True)
        _relatorio_janela(nome, registros, sem_sinal, corte)

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
