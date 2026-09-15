# -*- coding: utf-8 -*-
"""copa_win: DUAS bases de trajetoria barra-a-barra -- o INSUMO, nao a analise
(pedido do dono, 2026-09-15, ampliado no mesmo dia).

Este script NAO conclui nada sobre o robo. Produz QUATRO CSVs em `scratch/`,
2 por BASE:

  BASE A -- PRODUCAO (config intacta, `corte_persistencia_ativo=True`,
  `defesa_ativa=True`, exatamente `_KWARGS_PADRAO["copa_win"]`):
    * `copawin_trajetoria_trades_producao_2026_09_15.csv`
    * `copawin_trajetoria_barras_producao_2026_09_15.csv`
    Tem que bater **564 trades / 58 stops** -- e' a base que DESCREVE o robo
    real. Aborta se nao bater.

  BASE B -- TRAJETORIA LIVRE (MESMA config, exceto
  `corte_persistencia_ativo=False` e `defesa_ativa=False` -- todo o resto
  IDENTICO, inclusive o corte de achatamento de producao):
    * `copawin_trajetoria_trades_livre_2026_09_15.csv`
    * `copawin_trajetoria_barras_livre_2026_09_15.csv`
    NAO bate 564/58, e NAO DEVE bater -- aqui a posicao so' morre por ALVO,
    STOP ou ACHATAMENTO, entao o caminho INTEIRO aparece (nas 143 saidas de
    producao por `signal`, a regra amputa a trajetoria antes dela se
    revelar). A contagem que der e' reportada, nunca tratada como erro.

    **BASE B NAO DESCREVE O ROBO EM PRODUCAO.** Qualquer P&L tirado dela e'
    CONTRAFACTUAL ("o que teria acontecido se as duas saidas defensivas nao
    existissem"), nunca previsao -- a sequencia de entradas MUDA junto (uma
    posicao que vive mais bloqueia a proxima entrada por mais tempo), entao
    BASE B nao e' "BASE A com 2 saidas religadas por fora": e' um backtest
    proprio, com sua propria trajetoria de caixa e sua propria sequencia de
    trades.

    A tabela de trades da BASE B carrega DUAS colunas extras --
    `corte_persistencia_teria_disparado_ts` e `defesa_teria_disparado_ts` --
    o instante (NaT se nunca) em que cada mecanismo TERIA fechado a posicao,
    CALCULADO mas NUNCA executado (a posicao continua aberta de verdade na
    BASE B; o calculo roda em paralelo, sem efeito na decisao). Isto permite
    responder depois "o que as 143 saidas por sinal da producao teriam
    virado sem a regra?" sem uma 3a rodada. As mesmas duas colunas existem
    (sempre NaT) na tabela de trades da BASE A, so' por CONSISTENCIA DE
    ESQUEMA -- na BASE A o mecanismo de verdade ja' fecha a posicao, entao
    nao ha' "trajetoria livre" pra' medir depois do disparo real.

## POR QUE AS DUAS BASES

A config de producao do `copa_win` tem duas regras que LEEM a trajetoria e
AMPUTAM o caminho antes dele se revelar por inteiro:
`corte_persistencia_ativo=True` (fecha se `barras_adversas/bars_held >=
1.0`, aquecimento 10 barras) e `defesa_ativa=True` (arma em 20% da
distancia do stop, fecha quando falta so' 10% do alvo). As duas SOMADAS
produzem as 143 saidas por `signal` do FATO de 564 trades. Estudar FORMA de
trajetoria (velocidade, oscilacao, ponto de nao-retorno) so' na BASE A e'
estudar um mundo onde a regra ja' agiu -- a cauda que ela cortaria nunca
aparece. A BASE B existe pra' essa forma poder ser vista inteira, com a
ressalva de contrafactual sempre em maiusculo dita acima.

## POPULACAO -- BASE A tem que bater 564 trades / 58 stops

Backtest CONTINUO de 191 pregoes (2025-12-01 a 2026-09-10), `copa_win` com a
config de PRODUCAO importada de `strategy.daytrade.registry._KWARGS_PADRAO
["copa_win"]` (nunca redigitada aqui -- BASE B parte do MESMO dicionario e
so' sobrescreve os 2 booleanos), capital R$3.000, corte de achatamento de
producao (`config_for` ja entrega `session_end_time=profile.
flatten_cut_time` sozinho -- conferido no arranque). O motor recusa `Enter`
com posicao aberta (`copa_win` so' abre 1 posicao por vez) e a entrada e'
SEMPRE `EnterLimit` (`entrada_maker=True` em producao) -- fill exatamente no
`limit_price`, sem slippage. `fatiar_saida_alvo=True` faz o ALVO fechar em
fatias de 1 contrato (`exit_split_unit=1`), cada fatia virando seu PROPRIO
`IntradayTrade` com o MESMO `entry_ts`/`entry_price`/stop/alvo da posicao-mae,
mas `exit_ts`/`exit_price`/`pnl` proprios -- ver "CONVENCAO DE FATIA" abaixo.
STOP, achatamento (`forced_flatten`) e (so' na BASE A) as duas saidas de
sinal do robo (`corte_persistencia`, `defesa_recuo`, ambas viram
`IntradayExitReason.SIGNAL`) fecham a posicao (ou o que sobrou dela) INTEIRA
de uma vez, em UM trade so'.

Precedente reaproveitado (mesma config, mesmo motor, mesma populacao da
BASE A): `scripts/daytrade/copawin_preditor_stop_2026_09_15.py`, que produziu
`scratch/copawin_preditor_stop_trades.csv` (1 linha por trade, mesma
convencao de fatia). Este script e' a IRMA em granularidade de BARRA --
ver "COMO CASAR COM A TABELA EXISTENTE" no fim desta docstring.

## STOP E ALVO SAO OS DA ENTRADA, E NUNCA MUDAM (nas DUAS bases)

`trail_vol=None` na config de producao -- `_trailing` nunca dispara, o STOP
nunca e' ajustado (`AdjustStop`) depois da entrada, nas duas bases (BASE B
so' desliga `corte_persistencia_ativo`/`defesa_ativa`, nao mexe em
`trail_vol`). O ALVO nunca e' ajustado por este robo (nenhuma chamada a
`AdjustTarget` existe em `copa_win.py`). Logo "stop e alvo definidos na
entrada" == "stop e alvo do trade inteiro". Capturados por instrumentacao
(subclasse que so' ACRESCENTA logs dentro de `_entrada`/`on_bar`, chamando
`super()` sem alterar a decisao -- nunca roda ao vivo, vive so' aqui) do
`initial_stop`/`initial_target` da acao (`EnterLimit`) que o robo de fato
devolveu -- nunca recalculados a mao a partir de `alvo_vol`/`stop_vol`, que
teria de reproduzir o arredondamento de tick (`no_tick`) e correria risco de
divergir por 1 tick. Confirmado contra o motor (`machine._niveis_da_
entrada`): com `anchor_exits_at_fill=False` (default, nao setado por nenhum
caminho de producao deste robo) o motor usa EXATAMENTE `order.initial_stop`/
`initial_target` sem transladar -- e como a entrada e' sempre limite
preenchida no proprio nivel, a translacao seria no-op de qualquer forma.

## CONVENCAO DE FATIA (muda a contagem -- leia antes de somar linhas)

Cada `IntradayTrade` devolvido pelo motor vira UMA linha da tabela de
trades, INCLUSIVE fatias-irma do mesmo alvo. Isto reproduz os 564 trades do
FATO na BASE A (nao 564 "posicoes" -- uma posicao de N contratos fechada
inteira no alvo produz ATE' N linhas). O casamento trade<->ordem de entrada
usa um PONTEIRO monotonico (ordens e trades sao ambos crescentes no tempo,
uma unica posicao aberta por vez neste robo): para cada trade, a ordem
associada e' a ULTIMA logada com `sinal_ts <= entry_ts`. Isto identifica
corretamente fatias-irma (todas apontam pra' MESMA ordem de entrada, logo
herdam o MESMO `entry_price`/stop/alvo), sem colapsar as linhas.

## COMO "TERIA DISPARADO" E' CALCULADO NA BASE B (sombra, sem efeito)

`CopaWin._corte_persistencia_deve_fechar`/`_defesa_deve_fechar` sao METODOS
PUROS dado `(pos, bar)` -- so' dependem de `self.corte_persistencia_min_
barras`/`frac_adverso`/`defesa_gatilho_stop_pct`/`defesa_alvo_proximidade_
pct` (que continuam com os NUMEROS de producao na BASE B -- so' os
booleanos `*_ativo` mudam) e de estado interno que os PROPRIOS metodos
mantem (`self._barras_adversas`, `self._defesa_armada`), nao de
`self.corte_persistencia_ativo`/`self.defesa_ativa` (esses booleanos so' sao
lidos por `on_bar`, pra' decidir se CHAMA os metodos). Na BASE B a subclasse
instrumentada chama os DOIS metodos manualmente, TODA barra com posicao
aberta -- exatamente a mesma cadencia que a producao usaria se os
booleanos estivessem ligados --, so' que NUNCA age no resultado (nao
devolve `Exit`); grava so' o PRIMEIRO instante em que cada um retornou
`True`, por posicao (chave `(side, entry_ts)`, igual a que os proprios
metodos usam). Na BASE A isto NAO e' feito (evitaria chamar os mesmos
metodos DUAS vezes por barra -- uma pela sombra, outra pelo `on_bar` real
--, o que duplicaria a contagem interna de `_barras_adversas` e divergiria
da producao de verdade); as duas colunas saem sempre NaT ali.

## COMO OS CAMPOS DA TABELA DE BARRA SAO CALCULADOS

Tudo em CONVENCAO DE SINAL ajustada pelo lado -- "favoravel" e "adverso" sao
sempre do ponto de vista do trade (long: favoravel = preco sobe; short:
favoravel = preco desce). Testado a mao com 1 trade long e 1 short
confirmados na saida deste script (ver o bloco "CONFERENCIA DE SINAL"),
rodado uma vez pra' BASE A.

Para um trade de lado `L`, entrada `E`, stop `S`, alvo `T`, e uma barra
`(o,h,l,c,v)`:

  * `pontos_favoraveis_barra` = `h-E` (long) / `E-l` (short) -- o melhor
    preco que a barra ISOLADA alcancou a favor. NAO acumulado, NAO clampado
    em zero (pode ser negativo se a barra inteira ficou do lado adverso).
  * `pontos_adversos_barra` = `E-l` (long) / `h-E` (short) -- espelho do
    acima, o pior preco que a barra isolada alcancou contra.
  * `exc_favoravel_acum_ticks` = `max(pontos_favoraveis_barra ate' aqui)`,
    clampado em >=0, convertido pra' ticks (`/tick_size`) -- e' o MFE nao
    realizado ATE' esta barra (inclusive).
  * `exc_favoravel_acum_frac_alvo` = `exc_favoravel_acum` (em pontos, antes
    da conversao pra' tick) `/ |T-E|` -- fracao da distancia ate' o alvo ja'
    percorrida a favor. Pode passar de 1,0 (preco tocou/passou do alvo numa
    barra que NAO fechou o trade por alvo).
  * `exc_adversa_acum_ticks` / `exc_adversa_acum_frac_stop` -- os mesmos dois
    campos, espelhados pro lado do STOP.
  * `pos_fechamento_norm` -- onde o FECHAMENTO da barra fica numa reta onde
    -1=preco do stop, 0=preco de entrada, +1=preco do alvo. Formula: seja
    `p = (c-E)` (long) ou `(E-c)` (short) -- positivo do lado favoravel.
    Se `p>=0`: `pos_norm = p/|T-E|`. Se `p<0`: `pos_norm = p/|E-S|` (o sinal
    negativo de `p` sobrevive a divisao por um numero positivo). E' PIECEWISE
    LINEAR de proposito -- a escala do lado do alvo e a do lado do stop quase
    sempre tem tamanhos diferentes (`stop_vol != alvo_vol`), uma reta unica
    faria -1 e +1 nao corresponderem aos precos reais de stop/alvo.
  * `cruzou_entrada` -- 1 se o RANGE da barra (`[l,h]`) contem `E`
    (`l<=E<=h`), 0 senao. `cruzamentos_acumulados` e' a soma corrida,
    inclusive esta barra.
  * `lado_adverso_fechamento` -- 1 se `c<E` (long) ou `c>E` (short), 0 senao
    -- MESMA convencao (estrita, empate NAO conta como adverso) de
    `CopaWin._corte_persistencia_deve_fechar`. `frac_barras_adversas_
    acumulada` = soma corrida de `lado_adverso_fechamento` (inclusive esta
    barra) `/ (indice_da_barra+1)`.

    ATENCAO -- isto e' LIGEIRAMENTE diferente da contagem que o robo de
    verdade usa ao vivo (`self._barras_adversas`, que so' soma o lado das
    barras JA' VIVIDAS, excluindo a barra corrente do numerador ao decidir
    SE fecha NESTA barra -- disciplina anti-look-ahead de execucao). Aqui a
    tabela e' DESCRITIVA ("ate' aqui, inclusive"), nao uma regra de execucao
    -- quem for testar uma regra causal precisa DESLOCAR 1 barra pra' tras.

## O QUE E' POS-RESULTADO -- NUNCA USAR COMO PREDITOR

  * `frac_duracao_decorrida` (`minutos_desde_entrada / duracao_total_min` do
    TRADE) so' e' conhecida DEPOIS que o trade fecha -- mesma ressalva de
    `copawin_duracao_operacoes_2026_09_03.py`. Existe so' pra' analise
    DIAGNOSTICA retrospectiva, nunca pra' regra de saida ao vivo.
  * `is_exit_bar` (a ultima barra do trade) revela por construcao que o
    trade fechou ali -- so' serve pra' filtrar/agrupar.
  * Na BASE B, `corte_persistencia_teria_disparado_ts`/`defesa_teria_
    disparado_ts` sao conhecidas SO' depois de rodar o trade inteiro (o
    calculo olha toda barra ate' a saida) -- validas pra' perguntar "o que
    a regra teria feito", nunca pra' acionar coisa nenhuma dentro do proprio
    trade.
  * Todas as OUTRAS colunas de barra usam so' dado ATE' a barra corrente.

## COMO CASAR COM A TABELA EXISTENTE

`scratch/copawin_preditor_stop_trades.csv` (1 linha por trade da BASE A, as
mesmas 564) NAO carrega um `trade_id` explicito -- casar por (`data`,
`lado`, `tentativa_no_dia`) e' FRAGIL. O jeito ROBUSTO: casar pela CHAVE
NATURAL `entry_ts` + `exit_ts` (unica por trade -- fatias-irma compartilham
`entry_ts` mas nunca `exit_ts`). Este script grava as duas colunas em
ambas as tabelas de trades que produz.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_trajetoria_barra_a_barra_2026_09_15.py`
"""
from __future__ import annotations

import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 3_000.0
FATO_TRADES = 564
FATO_STOPS = 58
CORTE_OOS = pd.Timestamp("2026-06-13").date()

SCRATCH = ROOT / "scratch"


def br(x, casas=2):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# carga de dados (compartilhada pelas 2 bases -- mesmo df, mesmos 191 dias)
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def _carregar_bars():
    if "df" in _CACHE:
        return _CACHE["df"], _CACHE["dias"]
    from market_data_intraday.storage import load_m1

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    df = df[[d in set(completos) for d in df.index.date]].copy()
    real = df["real_volume"].fillna(0.0) if "real_volume" in df.columns else pd.Series(0.0, index=df.index)
    tick_v = df["tick_volume"].fillna(0.0) if "tick_volume" in df.columns else pd.Series(0.0, index=df.index)
    df["volume"] = np.where(real > 0, real, tick_v).astype(float)
    _CACHE["df"], _CACHE["dias"] = df, completos
    return df, completos


def _construir_estrategia(modo: str):
    """`modo="producao"`: `_KWARGS_PADRAO["copa_win"]` byte a byte, so' com
    log de entrada. `modo="livre"`: MESMOS kwargs, exceto
    `corte_persistencia_ativo=False`/`defesa_ativa=False` -- e' ALI que a
    subclasse tambem liga o rastreio de sombra (ver a secao "COMO 'TERIA
    DISPARADO' " da docstring do modulo)."""
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    if modo not in ("producao", "livre"):
        raise ValueError(f"modo invalido: {modo!r}")
    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    shadow = (modo == "livre")
    if shadow:
        kwargs["corte_persistencia_ativo"] = False
        kwargs["defesa_ativa"] = False

    class CopaWinInstrumentado(CopaWin):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._log_ordens: list[dict] = []
            self._ts_atual = None
            # (side, entry_ts) -> ts do PRIMEIRO bar em que o mecanismo teria
            # disparado -- so' preenchido quando `shadow=True` (modo="livre").
            self._shadow_corte_disparo: dict = {}
            self._shadow_defesa_disparo: dict = {}

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._ts_atual = ts
            if shadow and positions:
                for pos in positions:
                    chave = (pos.side, pos.entry_ts)
                    # Chama os DOIS metodos SEMPRE (mesma cadencia que a
                    # producao usaria com os booleanos ligados) -- o estado
                    # interno que eles mantem (`_barras_adversas`,
                    # `_defesa_armada`) precisa avancar a CADA barra pra' o
                    # instante de disparo sair certo. NUNCA age no retorno.
                    disparou_corte = self._corte_persistencia_deve_fechar(pos, bar)
                    if disparou_corte and chave not in self._shadow_corte_disparo:
                        self._shadow_corte_disparo[chave] = ts
                    disparou_defesa = self._defesa_deve_fechar(pos, bar)
                    if disparou_defesa and chave not in self._shadow_defesa_disparo:
                        self._shadow_defesa_disparo[chave] = ts
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        def _entrada(self, lado, preco, nivel_rompido, vol):
            acao = super()._entrada(lado, preco, nivel_rompido, vol)
            self._log_ordens.append(dict(
                sinal_ts=self._ts_atual,
                lado=lado,
                stop=acao.initial_stop,
                alvo=acao.initial_target,
                quantidade=acao.quantity,
            ))
            return acao

    return CopaWinInstrumentado(**kwargs)


def _config(strat):
    from backtest.intraday.profiles import config_for, profile_for

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    assert cfg.session_end_time == profile.flatten_cut_time, (
        "config_for nao entregou o corte de achatamento de PRODUCAO -- pare e "
        "investigue antes de rodar qualquer coisa."
    )
    return cfg


def _rodar(modo: str):
    from backtest.intraday.engine import run_intraday_backtest

    df, dias = _carregar_bars()
    strat = _construir_estrategia(modo)
    cfg = _config(strat)
    res = run_intraday_backtest(df, strat, cfg)
    return res, strat, df, dias


# ---------------------------------------------------------------------------
# tabela de TRADES (1 linha por `IntradayTrade`, fatias-irma inclusive)
# ---------------------------------------------------------------------------

def montar_tabela_trades(res, strat) -> pd.DataFrame:
    tick = float(strat.tick_size)
    point_value = float(strat.point_value_brl)
    trades = sorted(res.trades, key=lambda t: (t.entry_ts, t.exit_ts))
    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])

    por_dia: dict = {}
    for t in trades:
        por_dia.setdefault(t.entry_ts.date(), []).append(t)
    ordinal: dict = {}
    for dia, ts_dia in por_dia.items():
        for i, t in enumerate(sorted(ts_dia, key=lambda x: x.entry_ts), start=1):
            ordinal[id(t)] = i

    i = 0
    ordem_do_trade: dict = {}
    for t in trades:
        while i + 1 < len(ordens) and ordens[i + 1]["sinal_ts"] <= t.entry_ts:
            i += 1
        ordem_do_trade[id(t)] = ordens[i] if ordens and ordens[i]["sinal_ts"] <= t.entry_ts else None

    linhas = []
    sem_ordem = 0
    trade_id = 0
    for t in trades:
        ordem = ordem_do_trade[id(t)]
        if ordem is None:
            sem_ordem += 1
            continue
        trade_id += 1
        stop_price = ordem["stop"]
        target_price = ordem["alvo"]
        dur_min = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
        exit_reason = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
        chave_pos = (t.side, t.entry_ts)
        linhas.append(dict(
            trade_id=trade_id,
            data=t.entry_ts.date(),
            janela=("IS" if t.entry_ts.date() < CORTE_OOS else "OOS"),
            ordinal_no_dia=ordinal[id(t)],
            lado=t.side,
            entry_ts=t.entry_ts,
            entry_price=t.entry_price,
            stop_price=stop_price,
            target_price=target_price,
            dist_stop_ticks=(abs(t.entry_price - stop_price) / tick if stop_price is not None else float("nan")),
            dist_alvo_ticks=(abs(target_price - t.entry_price) / tick if target_price is not None else float("nan")),
            exit_ts=t.exit_ts,
            exit_price=t.exit_price,
            exit_reason=exit_reason,
            exit_detail=t.exit_detail,
            quantity=t.quantity,
            pnl_brl=t.pnl_brl,
            duracao_barras=None,  # preenchido depois de montar a tabela de barras
            duracao_min=dur_min,
            tick_size=tick,
            point_value_brl=point_value,
            symbol=strat.symbol,
            capital=CAPITAL,
            corte_persistencia_teria_disparado_ts=strat._shadow_corte_disparo.get(chave_pos, pd.NaT),
            defesa_teria_disparado_ts=strat._shadow_defesa_disparo.get(chave_pos, pd.NaT),
        ))
    if sem_ordem:
        print(f"  [aviso] {sem_ordem} trade(s) sem ordem casada (descartado(s)) -- "
              f"investigar se > 0, nao deveria acontecer neste robo (1 posicao por vez).")
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# tabela de BARRAS (1 linha por trade x barra, entry_ts..exit_ts inclusive)
# ---------------------------------------------------------------------------

def montar_tabela_barras(tab_trades: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    times_ns = df.index.as_unit("ns").asi8
    o_arr = df["open"].to_numpy(dtype=np.float64)
    h_arr = df["high"].to_numpy(dtype=np.float64)
    l_arr = df["low"].to_numpy(dtype=np.float64)
    c_arr = df["close"].to_numpy(dtype=np.float64)
    v_arr = df["volume"].to_numpy(dtype=np.float64)

    blocos = []
    sem_barra = 0
    for row in tab_trades.itertuples(index=False):
        entry_ns = pd.Timestamp(row.entry_ts).value
        exit_ns = pd.Timestamp(row.exit_ts).value
        start = int(np.searchsorted(times_ns, entry_ns, side="left"))
        end = int(np.searchsorted(times_ns, exit_ns, side="right"))
        if end <= start:
            sem_barra += 1
            continue

        o, h, l, c, v = o_arr[start:end], h_arr[start:end], l_arr[start:end], c_arr[start:end], v_arr[start:end]
        ts = times_ns[start:end]
        n = end - start
        E = float(row.entry_price)
        S = row.stop_price
        T = row.target_price
        tick = float(row.tick_size)
        is_long = (row.lado == "long")

        if is_long:
            pontos_fav_barra = h - E
            pontos_adv_barra = E - l
            pontos_fav_close = c - E
        else:
            pontos_fav_barra = E - l
            pontos_adv_barra = h - E
            pontos_fav_close = E - c

        cum_fav = np.clip(np.maximum.accumulate(pontos_fav_barra), 0.0, None)
        cum_adv = np.clip(np.maximum.accumulate(pontos_adv_barra), 0.0, None)

        dist_alvo = abs(T - E) if T is not None and T == T else float("nan")
        dist_stop = abs(E - S) if S is not None and S == S else float("nan")

        frac_fav = cum_fav / dist_alvo if dist_alvo and dist_alvo > 0 else np.full(n, np.nan)
        frac_adv = cum_adv / dist_stop if dist_stop and dist_stop > 0 else np.full(n, np.nan)

        pos_norm = np.where(
            pontos_fav_close >= 0,
            pontos_fav_close / dist_alvo if dist_alvo and dist_alvo > 0 else np.nan,
            pontos_fav_close / dist_stop if dist_stop and dist_stop > 0 else np.nan,
        )

        cruzou_entrada = ((l <= E) & (h >= E)).astype(np.int64)
        cruzamentos_acum = np.cumsum(cruzou_entrada)

        if is_long:
            lado_adverso = (c < E).astype(np.int64)
        else:
            lado_adverso = (c > E).astype(np.int64)
        frac_adverso_acum = np.cumsum(lado_adverso) / np.arange(1, n + 1)

        minutos_desde_entrada = (ts.astype(np.float64) - entry_ns) / 1e9 / 60.0
        dur_total_min = (exit_ns - entry_ns) / 1e9 / 60.0
        if dur_total_min > 0:
            frac_duracao = minutos_desde_entrada / dur_total_min
        else:
            frac_duracao = np.ones(n)

        bar_idx = np.arange(n)
        bloco = pd.DataFrame({
            "trade_id": row.trade_id,
            "bar_idx": bar_idx,
            "ts": pd.to_datetime(ts, utc=True),
            "minutos_desde_entrada": minutos_desde_entrada,
            "frac_duracao_decorrida": frac_duracao,
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "exc_favoravel_barra_ticks": pontos_fav_barra / tick,
            "exc_adversa_barra_ticks": pontos_adv_barra / tick,
            "exc_favoravel_acum_ticks": cum_fav / tick,
            "exc_favoravel_acum_frac_alvo": frac_fav,
            "exc_adversa_acum_ticks": cum_adv / tick,
            "exc_adversa_acum_frac_stop": frac_adv,
            "pos_fechamento_norm": pos_norm,
            "cruzou_entrada": cruzou_entrada,
            "cruzamentos_acumulados": cruzamentos_acum,
            "lado_adverso_fechamento": lado_adverso,
            "frac_barras_adversas_acumulada": frac_adverso_acum,
            "is_entry_bar": bar_idx == 0,
            "is_exit_bar": bar_idx == (n - 1),
            "lado": row.lado, "entry_price": E, "stop_price": S, "target_price": T,
            "entry_ts": row.entry_ts, "exit_ts": row.exit_ts,
        })
        blocos.append(bloco)

    if sem_barra:
        print(f"  [aviso] {sem_barra} trade(s) sem NENHUMA barra localizavel em "
              f"[entry_ts, exit_ts] (inesperado -- investigar se > 0).")
    if not blocos:
        return pd.DataFrame()
    return pd.concat(blocos, ignore_index=True)


# ---------------------------------------------------------------------------
# conferencia manual de SINAL -- 1 long + 1 short, impresso pra' inspecao.
# ---------------------------------------------------------------------------

def _conferir_sinal(tab_trades: pd.DataFrame, tab_barras: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("CONFERENCIA MANUAL DE SINAL -- 1 trade LONG e 1 SHORT resolvidos por STOP ou TARGET")
    print("=" * 100)
    for lado in ("long", "short"):
        cand = tab_trades[(tab_trades.lado == lado) & (tab_trades.exit_reason.isin(["stop", "target"]))]
        if cand.empty:
            print(f"\n[{lado}] nenhum trade STOP/TARGET encontrado -- pulando conferencia.")
            continue
        row = cand.iloc[0]
        tid = row.trade_id
        barras = tab_barras[tab_barras.trade_id == tid].sort_values("bar_idx")
        print(f"\n--- [{lado.upper()}] trade_id={tid}  data={row.data}  exit_reason={row.exit_reason} ---")
        print(f"  entry_price={br(row.entry_price)}  stop_price={br(row.stop_price)}  "
              f"target_price={br(row.target_price)}  quantity={row.quantity}  pnl={br(row.pnl_brl)}")
        print(f"  {len(barras)} barra(s) de entry_ts={row.entry_ts} a exit_ts={row.exit_ts}")
        cols = ["bar_idx", "open", "high", "low", "close",
                "exc_favoravel_barra_ticks", "exc_adversa_barra_ticks",
                "exc_favoravel_acum_ticks", "exc_adversa_acum_ticks",
                "pos_fechamento_norm", "cruzou_entrada", "lado_adverso_fechamento"]
        primeiras = barras.head(3)[cols]
        ultimas = barras.tail(3)[cols]
        print("  primeiras barras:")
        print(primeiras.to_string(index=False))
        print("  ultimas barras:")
        print(ultimas.to_string(index=False))
        ultima = barras.iloc[-1]
        esperado_pos_norm_negativo = (row.exit_reason == "stop")
        print(f"  [checagem] pos_fechamento_norm da ultima barra = {br(ultima.pos_fechamento_norm, 4)} "
              f"(esperado {'<0 (perto de -1, saiu por STOP)' if esperado_pos_norm_negativo else '>0 (perto de +1, saiu por TARGET)'})")
        ok = (ultima.pos_fechamento_norm < 0) == esperado_pos_norm_negativo
        print(f"  [checagem] {'OK' if ok else 'DIVERGENTE -- INVESTIGAR'}")


# ---------------------------------------------------------------------------

def _processar_base(modo: str, sufixo: str, checar_fato: bool) -> None:
    print("\n" + "#" * 100)
    print(f"# BASE {sufixo.upper()} (modo={modo})")
    print("#" * 100)

    print("[1/5] rodando o backtest CONTINUO (191 pregoes, um so' processo, caixa nao reseta)...", flush=True)
    res, strat, df, dias = _rodar(modo)
    trades = list(res.trades)
    contagem_motivos = pd.Series([
        (t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason))
        for t in trades
    ]).value_counts()
    stops = int(contagem_motivos.get("stop", 0))
    print(f"  {len(dias)} pregoes ({dias[0]} a {dias[-1]})  |  trades={len(trades)}  stops={stops}  "
          f"ordens_logadas={len(strat._log_ordens)}", flush=True)
    print("  distribuicao de exit_reason:")
    print("    " + contagem_motivos.to_string().replace("\n", "\n    "))

    if checar_fato:
        if len(trades) != FATO_TRADES or stops != FATO_STOPS:
            print(f"  [ATENCAO] NAO bateu com o FATO ja medido (esperado trades={FATO_TRADES}, "
                  f"stops={FATO_STOPS}). ABORTANDO -- a base descreveria outro robo.")
            sys.exit(1)
        print("  CONFERENCIA OK -- bate byte a byte com o FATO ja medido (564 trades / 58 stops).")
    else:
        print("  (BASE LIVRE -- NAO se compara ao FATO de producao; divergencia e' o RESULTADO esperado.)")

    print("\n[2/5] montando a tabela de TRADES...", flush=True)
    tab_trades = montar_tabela_trades(res, strat)
    print(f"  {len(tab_trades)} trades casados com ordem de entrada.")
    if modo == "livre":
        n_corte = tab_trades.corte_persistencia_teria_disparado_ts.notna().sum()
        n_defesa = tab_trades.defesa_teria_disparado_ts.notna().sum()
        print(f"  corte_persistencia TERIA disparado em {n_corte} posicao(oes); "
              f"defesa TERIA disparado em {n_defesa} posicao(oes) (calculado, nao executado).")

    print("\n[3/5] montando a tabela de BARRAS (entry_ts..exit_ts por trade)...", flush=True)
    tab_barras = montar_tabela_barras(tab_trades, df)
    print(f"  {len(tab_barras)} linhas trade x barra.")

    contagem_barras = tab_barras.groupby("trade_id").size()
    tab_trades["duracao_barras"] = tab_trades["trade_id"].map(contagem_barras).fillna(0).astype(int)

    if checar_fato:
        print("\n[4/5] conferencia manual de sinal (1 long + 1 short)...", flush=True)
        _conferir_sinal(tab_trades, tab_barras)
    else:
        print("\n[4/5] conferencia de sinal pulada nesta base (ja feita na BASE producao, mesmo motor/formulas).")

    print("\n[5/5] gravando CSVs em scratch/...", flush=True)
    csv_trades = SCRATCH / f"copawin_trajetoria_trades_{sufixo}_2026_09_15.csv"
    csv_barras = SCRATCH / f"copawin_trajetoria_barras_{sufixo}_2026_09_15.csv"
    tab_trades.to_csv(csv_trades, index=False, encoding="utf-8")
    tab_barras.to_csv(csv_barras, index=False, encoding="utf-8")
    print(f"  {csv_trades}  ({len(tab_trades)} linhas)")
    print(f"  {csv_barras}  ({len(tab_barras)} linhas)")

    print(f"\n[resumo {sufixo}] duracao_barras -- media={tab_trades.duracao_barras.mean():.1f}  "
          f"mediana={tab_trades.duracao_barras.median():.1f}  "
          f"min={tab_trades.duracao_barras.min()}  max={tab_trades.duracao_barras.max()}")
    print("distribuicao de lado:")
    print("  " + tab_trades.lado.value_counts().to_string().replace("\n", "\n  "))
    print("quantidade por trade (fatias-irma inclusive):")
    print("  " + tab_trades.quantity.value_counts().sort_index().to_string().replace("\n", "\n  "))


def main() -> None:
    t0 = _time.perf_counter()
    print("=" * 100)
    print("copa_win -- BASES DE TRAJETORIA barra-a-barra (WIN@, R$3.000, 191 pregoes)")
    print("=" * 100)

    _processar_base("producao", "producao", checar_fato=True)
    _processar_base("livre", "livre", checar_fato=False)

    dt = _time.perf_counter() - t0
    print(f"\n\nFIM. total={dt:.1f}s")


if __name__ == "__main__":
    main()
