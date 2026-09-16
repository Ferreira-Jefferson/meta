# -*- coding: utf-8 -*-
"""Contabilidade das oportunidades PERDIDAS pelo `win_retangulo` -- frente B
do pedido do dono: "quantos retangulos sao DETECTADOS mas nao viram operacao,
e por que?"

Instrumenta uma subclasse que reproduz `on_bar`/`_tenta_detectar` do robo de
PRODUCAO (mesma logica, copiada linha a linha, so' com contadores inseridos
nos pontos de decisao -- nao reescreve o DETECTOR, que continua sendo
`detecta_retangulo` importado do modulo original, regra 2 do pedido do dono)
e classifica, por RETANGULO VALIDADO (passou forma + largura + risco), o
destino:

  * ARMOU pelo menos uma vez (virou `EnterLimit`) -- destino normal.
  * NUNCA ARMOU porque toda vez que chegou ao ponto de decisao havia posicao
    aberta (`positions` nao-vazio) -- o motor NAO PIRAMIDA (ver memoria do
    projeto), entao enquanto uma posicao esta aberta o robo nao arma nada,
    nem para um retangulo diferente.
  * NUNCA ARMOU por outro motivo (fechou exatamente no meio em toda barra da
    vida dele, ou morreu antes de qualquer barra chegar la' -- raro).

Dos retangulos que ARMARAM, o motor conta tambem (via os hooks que a
PRODUCAO ja' usa, `on_order_rejected`/`on_order_expired`):

  * PREENCHIDOS -- viram `IntradayTrade` (contagem = `len(res.trades)`,
    a mesma fonte da tabela oficial).
  * EXPIRADOS POR TTL -- a limite estourou o prazo sem tocar o nivel.
  * REJEITADOS PELO PORTAO DE CAPITAL/RISCO na submissao -- `on_order_
    rejected` (raro aqui: `enforce_capital_minimo` e' regra de ACAO, este
    robo e' futuro; o unico portao ativo e' `max_open_contracts`/margem, que
    com quantidade fixa=1 e capital acima do piso quase nunca dispara).

Antes do RETANGULO ser validado, dois cortes acontecem na deteccao (mesma
ordem do codigo de producao):

  * REJEITADO POR LARGURA MINIMA (< 328 pontos).
  * REJEITADO POR TETO DE RISCO (`risco_maximo_brl=80`).

## O que esta contagem RESPONDE e o que ela NAO responde

Responde: qual fatia da vida do retangulo se perde em cada portao, com
numero. NAO responde se "armar em retangulos concorrentes" e' facil de
destravar -- isso exigiria MUDAR o desenho (mais de uma posicao ao mesmo
tempo), o que o motor proibe estruturalmente (nao piramida, item da memoria
do projeto) e o desenho de execucao fechado nao contempla. Se a perda por
posicao aberta for grande, a secao final desta rodada fecha a frente dizendo
isso explicitamente, em vez de sugerir uma mudanca que o motor nao permite.

Roda nas duas janelas (IS/OOS), configuracao de PRODUCAO (W=20, largura>=328,
alvo 0,80xL, stop 0,50xL, ttl=10, tolerancia=0,20, risco<=R$80, capital
R$1.100, 1 contrato).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_oportunidades_perdidas_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import EnterLimit, no_tick  # noqa: E402
from strategy.daytrade.lab.win_retangulo import (  # noqa: E402
    LARGURA_MINIMA_TICKS, WinRetangulo, detecta_retangulo,
)

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 1_100.0


class WinRetanguloInstrumentado(WinRetangulo):
    """Reimplementa `_tenta_detectar`/`on_bar` do robo de PRODUCAO com
    contadores nos pontos de decisao. O DETECTOR (`detecta_retangulo`) e' o
    mesmo importado, nunca reescrito."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.n_candidatos = 0
        self.n_rejeitados_largura = 0
        self.n_rejeitados_risco = 0
        self.n_validados = 0
        self.n_armou_ao_menos_uma_vez = 0
        self.n_bloqueado_por_posicao = 0
        self.n_bloqueado_outro_motivo = 0
        self.n_expirados_ttl = 0
        self.n_rejeitados_capital = 0
        self._retangulo_armou = False
        self._retangulo_teve_bloqueio_posicao = False

    def on_session_start(self, session_date) -> None:
        # Classifica o retangulo que ficou ativo no PREGAO ANTERIOR (se
        # houver) antes de `_reset_sessao` (chamado pela super) apaga-lo em
        # silencio -- sem isto, todo retangulo vivo na virada de pregao
        # some sem nunca ser contado em nenhum destino.
        self._fecha_retangulo_atual()
        super().on_session_start(session_date)
        self._retangulo_armou = False
        self._retangulo_teve_bloqueio_posicao = False

    def on_order_rejected(self, ts) -> None:
        super().on_order_rejected(ts)
        self.n_rejeitados_capital += 1

    def on_order_expired(self, ts) -> None:
        super().on_order_expired(ts)
        self.n_expirados_ttl += 1

    def _fecha_retangulo_atual(self) -> None:
        """Chamado sempre que um retangulo VALIDADO deixa de ser o ativo
        (morreu ou foi substituido) -- classifica o destino dele."""
        if self._retangulo is None:
            return
        if self._retangulo_armou:
            self.n_armou_ao_menos_uma_vez += 1
        elif self._retangulo_teve_bloqueio_posicao:
            self.n_bloqueado_por_posicao += 1
        else:
            self.n_bloqueado_outro_motivo += 1

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * self.janela_barras:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior,
                                 tolerancia=self.tolerancia_borda)
        if ret is None:
            return
        self.n_candidatos += 1
        if ret["largura"] < LARGURA_MINIMA_TICKS * self.tick_size:
            self.n_rejeitados_largura += 1
            return
        if ret["largura"] < self.largura_minima_pontos:
            self.n_rejeitados_largura += 1
            return
        risco = (self.stop_fracao_largura * ret["largura"]
                 * self.valor_do_ponto_brl * self.quantidade)
        if risco > self.risco_maximo_brl:
            self.n_rejeitados_risco += 1
            return
        self.n_validados += 1
        self._retangulo = ret
        self._fora_seguidas = 0
        self._retangulo_armou = False
        self._retangulo_teve_bloqueio_posicao = False

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._hist.append(bar)

        if self._retangulo is not None and self._morreu(bar):
            self._fecha_retangulo_atual()
            self._retangulo = None
            self._barras_esperando = None
        if self._retangulo is None:
            self._tenta_detectar()
            if self._retangulo is None:
                return []

        if positions:
            if self._barras_esperando is None:
                # Chegaria aqui para tentar armar, se pudesse: posicao aberta
                # bloqueia (motor nao piramida).
                self._retangulo_teve_bloqueio_posicao = True
            self._barras_esperando = None
            return []

        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        r = self._retangulo
        meio, largura = r["meio"], r["largura"]
        if bar.close < meio:
            lado = "short"
            alvo = meio - self.alvo_fracao_largura * largura
            stop = meio + self.stop_fracao_largura * largura
        elif bar.close > meio:
            lado = "long"
            alvo = meio + self.alvo_fracao_largura * largura
            stop = meio - self.stop_fracao_largura * largura
        else:
            return []

        limite = no_tick(meio, self.tick_size)
        if lado == "short" and limite <= bar.close:
            return []
        if lado == "long" and limite >= bar.close:
            return []

        self._barras_esperando = 0
        self._retangulo_armou = True
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantidade,
            ttl_bars=self.ttl_barras,
            reason=f"retangulo_W{self.janela_barras}_L{largura:.0f}",
        )]


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _unidade(args):
    rotulo, dias = args
    strat = WinRetanguloInstrumentado(
        janela_barras=20, largura_minima_pontos=328.0,
        alvo_fracao_largura=0.80, stop_fracao_largura=0.50,
        ttl_barras=10, quantidade=1, tolerancia_borda=0.20,
        risco_maximo_brl=80.0,
    )
    df = load_m1("WIN@").sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile, trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01, initial_capital=CAPITAL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    # Fecha o retangulo que ficou ativo no ultimo pregao (se houver), senao
    # ele nunca e' classificado.
    strat._fecha_retangulo_atual()
    linha = linha_de_resultado(rotulo, res, CAPITAL, extras={})
    return dict(
        rotulo=rotulo,
        preenchidos=len(res.trades),
        candidatos=strat.n_candidatos,
        rej_largura=strat.n_rejeitados_largura,
        rej_risco=strat.n_rejeitados_risco,
        validados=strat.n_validados,
        armou=strat.n_armou_ao_menos_uma_vez,
        bloq_posicao=strat.n_bloqueado_por_posicao,
        bloq_outro=strat.n_bloqueado_outro_motivo,
        expirados_ttl=strat.n_expirados_ttl,
        rej_capital=strat.n_rejeitados_capital,
        linha=linha,
    )


def main():
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 130)
    print("win_retangulo -- ONDE SE PERDEM AS OPORTUNIDADES (config de producao, capital R$1.100)")
    print("=" * 130)
    print(f"  IS {len(IS)} pregoes | OOS {len(OOS)} pregoes\n", flush=True)

    tarefas = [("IS  (< 2026-06-13)", IS), ("OOS (>= 2026-06-13)", OOS)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t[0] for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            print(f"  ok {r['rotulo']}", flush=True)

    print("\n" + tabela([out[r]["linha"] for r, _d in tarefas]))

    print("\n" + "=" * 130)
    print("FUNIL DE OPORTUNIDADES")
    print("=" * 130)
    cols = ["candidatos", "rej_largura", "rej_risco", "validados", "armou",
            "bloq_posicao", "bloq_outro", "expirados_ttl", "rej_capital", "preenchidos"]
    header = "  " + "".join(f"{c:>15}" for c in ["janela"] + cols)
    print(header)
    for rot, _d in tarefas:
        r = out[rot]
        print("  " + f"{rot:>15}" + "".join(f"{r[c]:>15}" for c in cols))

    print()
    for rot, _d in tarefas:
        r = out[rot]
        pct_bloq = 100 * r["bloq_posicao"] / r["validados"] if r["validados"] else float("nan")
        pct_arm = 100 * r["armou"] / r["validados"] if r["validados"] else float("nan")
        pct_fill = 100 * r["preenchidos"] / r["armou"] if r["armou"] else float("nan")
        print(f"  {rot}: de {r['validados']} retangulos validados, {r['armou']} "
              f"armaram ({br(pct_arm,1)}%), {r['bloq_posicao']} nunca armaram por "
              f"POSICAO ABERTA ({br(pct_bloq,1)}%), {r['bloq_outro']} por outro motivo. "
              f"Dos que armaram, {r['preenchidos']} preencheram ({br(pct_fill,1)}%), "
              f"{r['expirados_ttl']} expiraram por TTL, {r['rej_capital']} foram "
              f"rejeitados no portao de capital/margem.")

    print("\n" + "=" * 130)
    print("LEITURA -- e' candidato a frente C fechar ou nao")
    print("=" * 130)
    print("  * `bloq_outro` inclui retangulos que morreram (3 barras fora da margem de morte)")
    print("    antes de qualquer barra chegar ao ponto de decisao de armar, ou cujo fechamento")
    print("    ficou exatamente no meio em toda a vida (limite nao tem lado -- caso raro).")
    print("  * O motor nao piramida por desenho (Enter com posicao aberta some, sem grid dos 2")
    print("    lados -- ver memoria do projeto). 'Armar em retangulos concorrentes' exigiria")
    print("    reescrever o motor para aceitar 2+ posicoes simultaneas do MESMO robo, o que o")
    print("    desenho de execucao fechado deste projeto nao contempla -- se a fatia bloqueada")
    print("    por posicao aberta for grande, ela e' custo ESTRUTURAL do desenho, nao um bug a")
    print("    corrigir aqui.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
