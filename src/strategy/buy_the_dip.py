"""Buy-the-dip: entradas condicionadas a estar abaixo do 20d high.

Hipótese: comprar no fim do mês pega qualquer preço. Filtrar entradas para
tickers que estão pelo menos 3% abaixo do máximo dos últimos 20 pregões
melhora timing de entrada, reduz DD.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from core.indicators import rolling_high
from core.models import ExitReason
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy


class BuyTheDip(Strategy):
    name = "buy_the_dip"
    version = "1.0"
    candidate = False  # classe-base da familia dip (usada por composicao), fora do ranking
    # Lista branca de `Strategy.state()`/`restore()` (ver `strategy/base.py`):
    # so `_pending_rebalance` precisa sobreviver a um restart. Declarada na
    # RAIZ da familia (nao na folha, `portfolio_dip2_hw40.py`) para ser
    # herdada automaticamente por `DipTop1Hysteresis` -> `PortfolioHysteresis`
    # -> `DipTop1Portfolio` (a campea), sem redeclarar em cada subclasse.
    _stateful_keys = ("_pending_rebalance",)

    # Ficha técnica da RAIZ da família (ver `Strategy` em `strategy/base.py`):
    # toda a linhagem dip herda daqui e só declara o que ela muda.
    watched_signals = (
        "Momentum 12-1: retorno de `lookback` pregões atrás até `skip_recent` atrás. "
        "O mês mais recente fica FORA do cálculo de propósito — não comprar o que "
        "acabou de disparar.",
        "Distância da máxima: fechamento dividido pela máxima dos últimos "
        "`high_window` pregões. Negativo = abaixo do topo.",
        "Selic: variação da taxa nos últimos `selic_window` pregões, lida de "
        "`selic_path`. Acima de `selic_threshold` conta como aperto monetário.",
        "Calendário: último pregão de cada mês (é a única data em que ele decide) "
        "e blackout de divulgação de resultados.",
    )
    entry_rules = (
        "Decide UMA vez por mês, no último pregão. Em qualquer outro dia devolve "
        "lista vazia — não entra, não rotaciona, não olha preço.",
        "Ranqueia o universo pelo momentum 12-1 e mira nos `top_n` primeiros.",
        "Só compra se o papel estiver pelo menos `dip_pct` abaixo da máxima de "
        "`high_window` pregões. Sem o dip, o mês passa em branco — a espera é a regra, "
        "não uma falha.",
        "Blackout de resultados não força a decisão: adia. A rotação fica DEVIDA "
        "(`_pending_rebalance`) e é recalculada do zero no próximo pregão livre.",
        "Sinal visto no fechamento de D é executado na abertura de D+1 — o engine "
        "não deixa a estratégia tocar o preço do próprio dia da decisão.",
    )
    exit_rules = (
        "Rotação: papel que caiu fora dos `top_n` na virada do mês é vendido "
        "(`ROTATION_OUT`).",
        "Aperto de Selic: variação acima de `selic_threshold` zera a carteira inteira "
        "(`IBOV_DEFENSIVE`). É o único gate macro do robô.",
        "Stop de -15% sobre o preço de ENTRADA (`BacktestConfig.stop_loss_pct`): é do "
        "ENGINE, não desta classe. Dispara em qualquer dia, intra-barra, sem esperar "
        "o fim do mês — e nunca sobe junto com o preço.",
        "Pregão perdido ao vivo não vira ordem atrasada: se era fim de mês, a rotação "
        "fica devida e é redecidida com o dado do pregão de retorno.",
    )
    sizing_rules = (
        "Capital dividido em `top_n` fatias iguais — cada entrada leva `1/top_n` do "
        "caixa livre no momento da compra.",
        "Custo sempre aplicado: corretagem + taxas por perna e slippage de "
        "`CostModel.slippage_pct` (padrão 0,15%) na execução.",
        "Ordem fracionária (abaixo de `fractional_lot_shares` ações) paga ainda a "
        "corretagem FIXA de `fractional_fixed_fee` por perna — o que decide se um "
        "capital pequeno sobrevive ao giro.",
    )
    param_docs = {
        "lookback": "Pregões do início da janela de momentum (252 ≈ 1 ano).",
        "skip_recent": "Pregões recentes ignorados no momentum (21 ≈ 1 mês).",
        "top_n": "Quantas posições simultâneas o robô persegue.",
        "selic_window": "Janela, em pregões, da variação da Selic.",
        "selic_threshold": "Alta de Selic que dispara a saída defensiva.",
        "selic_path": "Parquet da Selic diária. Ausente = gate desligado.",
        "dip_pct": "Queda mínima abaixo da máxima recente para poder comprar.",
        "high_window": "Pregões da máxima usada como referência do dip.",
    }

    def __init__(
        self,
        lookback: int = 252,
        skip_recent: int = 21,
        top_n: int = 3,
        selic_window: int = 63,
        selic_threshold: float = 0.005,
        selic_path: str = "data/raw/selic.parquet",
        dip_pct: float = 0.03,
        high_window: int = 20,
    ):
        self.lookback = lookback
        self.skip_recent = skip_recent
        self.top_n = top_n
        self.selic_window = selic_window
        self.selic_threshold = selic_threshold
        self.selic_path = selic_path
        self.dip_pct = dip_pct
        self.high_window = high_window
        self._scores = {}
        self._dist_from_high = {}
        self._selic_tightening = pd.Series(dtype=bool)
        self._month_end = pd.Series(dtype=bool)
        self._blackout = pd.Series(dtype=bool)
        self._pending_rebalance = False

    def initialize(self, panels, ibov):
        from core.calendar import is_month_end
        from core.earnings_calendar import blackout_series
        p = Path(self.selic_path)
        if p.exists():
            selic = pd.read_parquet(p)["valor"].reindex(ibov.index).ffill()
            dch = selic - selic.shift(self.selic_window)
            self._selic_tightening = (dch > self.selic_threshold).fillna(False)
        else:
            self._selic_tightening = pd.Series(False, index=ibov.index)
        self._month_end = is_month_end(ibov.index)
        self._blackout = blackout_series(ibov.index)
        for t, df in panels.items():
            c = df["close"]
            self._scores[t] = (c.shift(self.skip_recent) / c.shift(self.lookback)) - 1.0
            hi = rolling_high(c, self.high_window)
            self._dist_from_high[t] = (c / hi) - 1.0  # negativo = abaixo do high

    def on_missed_bars(self, missed):
        """Pregão perdido que era fim de mês deixa a rotação DEVIDA.

        Este robô só rebalanceia quando `is_month_end` é verdade naquele dia
        (ver `on_bar`). Se o processo estava fora do ar exatamente naquele
        fecho, o mês inteiro passa sem rotação — a carteira fica com o que
        sobrou do mês anterior até a virada seguinte.

        Marca `_pending_rebalance`, que é o MESMO mecanismo já usado para o
        blackout de resultados: no próximo pregão o robô recalcula momentum,
        distância da máxima e gate de Selic COM O DADO DESSE PREGÃO e decide
        do zero. Não é a decisão velha sendo executada tarde (regra 7) — é
        uma decisão nova, que pode perfeitamente ser "não entra".

        Pregão perdido que não era fim de mês não deve nada: naquele dia o
        robô teria devolvido lista vazia de qualquer forma.
        """
        for d in missed:
            ts = pd.Timestamp(d)
            if ts in self._month_end.index and bool(self._month_end.loc[ts]):
                self._pending_rebalance = True
                return

    def on_bar(self, date, open_positions, cash_available):
        is_me = date in self._month_end.index and bool(self._month_end.loc[date])
        should_rebalance = is_me or self._pending_rebalance
        if not should_rebalance:
            return []
        actions = []
        if date in self._selic_tightening.index and bool(self._selic_tightening.loc[date]):
            self._pending_rebalance = False
            for t in open_positions:
                actions.append(Exit(ticker=t, reason=ExitReason.IBOV_DEFENSIVE))
            return actions
        if date in self._blackout.index and bool(self._blackout.loc[date]):
            self._pending_rebalance = True
            return []
        self._pending_rebalance = False
        cands = []
        for t, s in self._scores.items():
            if date not in s.index: continue
            v = s.loc[date]
            if pd.isna(v): continue
            cands.append((t, float(v)))
        if not cands: return actions
        cands.sort(key=lambda x: x[1], reverse=True)
        # Rank (1 = melhor momentum) e score por ticker, só para o `metadata`
        # da entrada — `tgt` abaixo continua sendo a decisão.
        rank_de = {t: i + 1 for i, (t, _) in enumerate(cands)}
        score_de = {t: v for (t, v) in cands}
        tgt = {t for (t,_) in cands[:self.top_n]}
        # Exit por rotação
        for t in open_positions:
            if t not in tgt:
                actions.append(Exit(ticker=t, reason=ExitReason.ROTATION_OUT))
        # Entradas condicionais: só se dist_from_high <= -dip_pct
        sh = 1.0 / float(self.top_n)
        for t in tgt:
            if t in open_positions: continue
            dseries = self._dist_from_high.get(t)
            if dseries is None or date not in dseries.index: continue
            dist = dseries.loc[date]
            if pd.isna(dist) or float(dist) > -self.dip_pct:
                continue  # não entra sem o dip
            # `reason`/`metadata` são REGISTRO, não decisão: nada abaixo muda
            # o que já foi decidido nas linhas acima. Guardam a resposta para
            # "por que este papel neste dia?" — a regra que disparou mais os
            # números que a satisfizeram. Ver `Enter` em `strategy/base.py`.
            actions.append(Enter(
                ticker=t, size_hint=sh, reason="dip_rank",
                metadata={
                    "rank": rank_de.get(t),
                    "top_n": int(self.top_n),
                    "momentum_score": score_de.get(t),
                    "dist_from_high": float(dist),
                    "dip_threshold": -float(self.dip_pct),
                    "high_window": int(self.high_window),
                    "lookback": int(self.lookback),
                    "skip_recent": int(self.skip_recent),
                    "trigger": "month_end" if is_me else "pending_rebalance",
                },
            ))
        return actions
