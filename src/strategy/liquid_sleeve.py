"""LiquidSleeve — universo escolhido por LIQUIDEZ na data, fatiado em sleeves.

Por que esta peca existe
------------------------
Duas coisas quebraram o campeao quando ele foi medido fora da amostra:

  1. A WATCHLIST oficial (7 tickers em `core/config.py`) foi escolhida em 2026
     maximizando o capital de 2010-2026. `scripts/run_walk_forward.py` mostrou
     que refazer a mesma selecao usando so dado passado derruba o CAGR de ~36%
     para 17,1% / -4,2% / 18,3% nos tres cortes. O excedente era vies.
  2. A busca premiou papel ilikido. EMAE4 gira R$ 141 mil/dia; com 100% do
     capital em uma posicao, o robo satura o proprio papel a partir de
     R$ 70 mil. O backtest nunca soube disso porque nao modela impacto.

`scripts/run_safety_rolling.py` mediu onze alternativas em cinco janelas
FECHADAS de cinco anos e so duas sobreviveram — as duas que esta classe faz:

  - **universo point-in-time por liquidez**: a cada `refresh_months`, ranqueia
    o pool bruto pelo giro financeiro mediano dos `liquidity_window` pregoes
    ANTERIORES e fica com os `universe_n` primeiros. Nenhuma informacao de
    retorno entra na escolha — o mesmo universo era montavel naquele dia, com
    o dado daquele dia. Capacidade sobe de R$ 70 mil para ~R$ 14 milhoes.
  - **sleeve**: o robo nao opera o universo inteiro, so a fatia
    `[sleeve_index::sleeve_count]` dele. Cinco sleeves disjuntos rodando com
    capital/5 levaram as janelas negativas de 1 em 5 para 0 em 5 e o pior
    retorno de 12 meses de -41,9% para -16,1%.

Todo filtro defensivo ADITIVO testado junto (trava de tendencia IBOV>SMA200,
quarentena apos stop, stop largo, sem stop, dip 5%, universo top-40) reprovou:
cortaram o retorno sem comprar seguranca. Por isso nao estao aqui.

O que esta classe NAO e
-----------------------
Nao e um robo — e a peca. `candidate = False` a mantem fora do ranking porque
um sleeve sozinho e um quinto de uma decisao, e ranquea-lo por capital final
compararia um quinto de carteira com carteiras inteiras. O robo operavel e
`strategy/liquid_sleeves5.py`, que compoe cinco destas.

Fatiamento por rodizio (`[i::k]`), nao por blocos: em blocos o sleeve 0 ficaria
so com as blue chips e o sleeve 4 so com as menos liquidas — cada conta teria um
perfil de risco diferente e somar as curvas misturaria coisas incomparaveis.

Vies que continua de pe: `POOL` sai de `data/raw/`, que so tem empresas vivas
em 2026. Quem saiu da bolsa entre 2010 e hoje nao esta ali, e isso empurra todo
numero deste arquivo para cima.
"""
from __future__ import annotations

import pandas as pd

from core.models import ExitReason
from strategy.base import Exit
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio


# Pool BRUTO — tudo que existe em `data/raw/` com historico utilizavel. Nao e a
# watchlist do robo: e o conjunto de onde o filtro de liquidez escolhe, na data,
# sem olhar retorno. Inclui BOVA11/GOLD11/IMAB11 (ETFs) de proposito, porque foi
# com eles no pool que `run_safety_rolling.py` produziu os numeros aprovados —
# tirar agora mudaria o robo em relacao ao que foi validado.
POOL: tuple[str, ...] = (
    "AALR3.SA", "ABCB4.SA", "ALUP11.SA", "BAZA3.SA", "BBAS3.SA", "BBDC4.SA",
    "BBSE3.SA", "BEES3.SA", "BGIP4.SA", "BLAU3.SA", "BMEB4.SA", "BMGB4.SA",
    "BOVA11.SA", "BPAC11.SA", "BRAP4.SA", "BRSR6.SA", "CGAS3.SA", "CMIG4.SA",
    "CMIN3.SA", "CPFE3.SA", "CSMG3.SA", "CSNA3.SA", "CXSE3.SA", "DASA3.SA",
    "EGIE3.SA", "EMAE4.SA", "ENEV3.SA", "ENGI11.SA", "EQTL3.SA", "EUCA4.SA",
    "FESA4.SA", "FLRY3.SA", "FRAS3.SA", "GGBR4.SA", "GOAU4.SA", "GOLD11.SA",
    "HAPV3.SA", "IMAB11.SA", "IRBR3.SA", "ITUB4.SA", "KEPL3.SA", "LEVE3.SA",
    "MATD3.SA", "MYPK3.SA", "PINE4.SA", "PNVL3.SA", "POMO4.SA", "PSSA3.SA",
    "RADL3.SA", "RAPT4.SA", "RDOR3.SA", "ROMI3.SA", "SANB11.SA", "SAPR11.SA",
    "SBSP3.SA", "TAEE11.SA", "TIMS3.SA", "TUPY3.SA", "UGPA3.SA", "USIM5.SA",
    "VALE3.SA", "VIVT3.SA", "WEGE3.SA",
)


class LiquidSleeve(DipTop1Portfolio):
    """Campeao rodando so na fatia `sleeve_index` do top-N liquido do dia."""

    name = "liquid_sleeve"
    version = "1.0"
    candidate = False  # peca de composicao — o robo e `liquid_sleeves5`
    universe_tickers = POOL

    def __init__(
        self,
        sleeve_index: int = 0,
        sleeve_count: int = 5,
        universe_n: int = 20,
        liquidity_window: int = 252,
        refresh_months: int = 12,
        min_history_days: int = 504,
        evict_on_refresh: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sleeve_index = sleeve_index
        self.sleeve_count = sleeve_count
        self.universe_n = universe_n
        self.liquidity_window = liquidity_window
        self.refresh_months = refresh_months
        self.min_history_days = min_history_days
        self.evict_on_refresh = evict_on_refresh
        self._eligible: pd.DataFrame = pd.DataFrame()
        self._raw_scores: dict[str, pd.Series] = {}

    # ------------------------------------------------------------------ setup

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._eligible = self._build_eligibility(panels, ibov.index)
        # Mascarar o SCORE (e nao filtrar na hora de ranquear) mantem toda a
        # logica de histerese/dip da familia intacta: um ticker fora do sleeve
        # simplesmente nao tem score naquele dia, entao nunca vira rank-1.
        self._raw_scores = dict(self._scores)
        for t, s in list(self._scores.items()):
            if t not in self._eligible.columns:
                self._scores[t] = pd.Series(float("nan"), index=s.index)
                continue
            mask = self._eligible[t].reindex(s.index).fillna(False)
            self._scores[t] = s.where(mask)

    def _build_eligibility(self, panels, index: pd.DatetimeIndex) -> pd.DataFrame:
        """Matriz data x ticker: este ticker pertence ao meu sleeve neste dia?

        Sem look-ahead por construcao: `rolling(...).median()` em `d` so ve ate
        `d`, e a fatia escolhida em `d` vale de `d` em diante — nunca para tras.
        """
        turnover, history = {}, {}
        for t, df in panels.items():
            if t.startswith("^") or "volume" not in df.columns:
                continue  # benchmark e paineis sem volume nao concorrem
            # Calculado no indice NATIVO do papel e so depois reindexado. Fazer
            # o contrario (reindexar antes) transforma todo pregao que o papel
            # nao teve em NaN dentro da janela e a mediana movel some — um papel
            # com dois buracos em 252 dias sumiria do ranking de liquidez por
            # motivo de calendario, nao de liquidez.
            tv = (df["close"] * df["volume"]).dropna()
            adtv_t = tv.rolling(self.liquidity_window, min_periods=self.liquidity_window // 2).median()
            turnover[t] = adtv_t.reindex(index).ffill()
            seen = pd.Series(range(1, len(df.index) + 1), index=df.index, dtype=float)
            history[t] = seen.reindex(index).ffill().fillna(0.0)
        if not turnover:
            return pd.DataFrame(index=index)

        adtv = pd.DataFrame(turnover, index=index)
        hist = pd.DataFrame(history, index=index)
        eligible = pd.DataFrame(False, index=index, columns=adtv.columns)

        # Primeiro pregao de cada epoca de `refresh_months` meses.
        epoch = (index.year * 12 + index.month - 1) // self.refresh_months
        starts = [0] + [i for i in range(1, len(index)) if epoch[i] != epoch[i - 1]]
        bounds = starts + [len(index)]

        for i, pos in enumerate(starts):
            limit = bounds[i + 1]
            # No inicio do historico ninguem tem 252 pregoes ainda e o ranking de
            # liquidez nao existe. Em vez de pular a epoca inteira (o robo
            # ficaria um ano parado depois de qualquer inicio de serie), anda
            # para a frente ate o primeiro dia em que da para ranquear.
            while pos < limit:
                d = index[pos]
                row = adtv.loc[d]
                # Historico minimo: sem ele o momentum 12-1 nao tem o que
                # calcular no primeiro mes e o sleeve comecaria cego.
                ok = row[(row > 0) & row.notna() & (hist.loc[d] >= self.min_history_days)]
                if not ok.empty:
                    break
                pos += 1
            if pos >= limit:
                continue
            top = list(ok.sort_values(ascending=False).head(self.universe_n).index)
            mine = top[self.sleeve_index :: self.sleeve_count]
            if not mine:
                continue
            eligible.iloc[pos : bounds[i + 1], eligible.columns.get_indexer(mine)] = True
        return eligible

    # ------------------------------------------------------------------ decisao

    def is_eligible(self, ticker: str, date) -> bool:
        """Este ticker esta no meu sleeve nesta data?"""
        if self._eligible.empty or ticker not in self._eligible.columns:
            return False
        if date not in self._eligible.index:
            return False
        return bool(self._eligible.at[date, ticker])

    def on_bar(self, date, open_positions, cash_available):
        stale = [t for t in open_positions if not self.is_eligible(t, date)]
        if not stale:
            return super().on_bar(date, open_positions, cash_available)

        if self.evict_on_refresh:
            # Despejo: a posicao herdada de uma epoca anterior sai assim que o
            # papel deixa o top-N liquido. Sem isso ela ficaria PRESA — com o
            # score mascarado o papel nunca mais vira rank-1, mas a histerese
            # tambem nunca manda sair (compara contra um score que virou NaN).
            self._pending_rebalance = True
            return [Exit(ticker=t, reason=ExitReason.ROTATION_OUT) for t in stale]

        # Grandfathering: o papel que ja esta na carteira continua sendo julgado
        # pelo momentum REAL dele (nao pelo score mascarado), entao a histerese
        # decide a saida como decidiria qualquer outra — o que o refresh proibe e
        # COMPRAR fora do universo, nao segurar o que ja se tem. Existe porque o
        # despejo transforma a virada de ano num evento de venda forcada, e a
        # venda forcada custa corretagem, spread e IR num dia escolhido pelo
        # calendario em vez de pelo sinal.
        saved = {t: self._scores[t] for t in stale if t in self._scores}
        for t in saved:
            self._scores[t] = self._raw_scores[t]
        try:
            return super().on_bar(date, open_positions, cash_available)
        finally:
            self._scores.update(saved)
