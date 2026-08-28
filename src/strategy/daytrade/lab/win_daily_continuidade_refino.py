"""REFINO do candidato `ContinuidadeDiaria(direction="reversal")` em WIN@
(`strategy.daytrade.lab.continuidade_daily`, +R$8.832,30 IS, 127 trades,
55,9% acerto -- rodada `continuidade_*` de 2026-08-27) -- pedido do dono:
"ele teve algum ganho, o que se pode fazer e' refinar ele, ver o que faz
com que numa segunda rodada ele pare de ganhar."

## Diagnostico que motiva estas 3 classes (`scripts/daytrade/
win_daily_continuidade_refino_diagnostico.py`, rodar de novo para
reproduzir os numeros citados aqui)

1. A autocorrelacao lag-1 BRUTA (sem custo) e' ESTAVEL no sinal ao longo do
   tempo -- fica NEGATIVA (favorece reversal) em 82%-94% do periodo
   inteiro nas 3 janelas rolantes testadas (40/60/80 pregoes), com so' 2-12
   trocas de sinal (a maioria perto de zero, ruido). Corr lag-1 medida so'
   na metade 1 = -0,1373; so' na metade 2 = -0,0929 -- mesmo sinal, ordem
   de grandeza parecida. Ou seja: a hipotese "o regime de autocorrelacao
   inverteu entre metade1/metade2" esta' REFUTADA -- nao e' a causa.
2. O P&L diario acumulado NAO tem um break abrupto numa data especifica:
   o pico da curva (R$9.931,40) acontece em 2026-03-23, ja' DENTRO da
   metade 2 (trade #72/127, a metade corta no #64), e a partir dali a
   curva devolve so' R$1.099,10 ate' o fim -- um giveback moderado, nao um
   colapso. A degradacao e' mais sobre DRAWDOWN crescente (MaxDD metade2
   R$4.304,70 > MaxDD metade1 R$3.445,80) do que sobre lucro desaparecendo.
3. O ACHADO CENTRAL: cortando os trades em tercis por |retorno do dia
   anterior| (o que decide o sinal, `previous_daily_bars[-1].close -
   previous_daily_bars[-2].close`, calculado SO' dentro de cada metade), o
   tercio "forte" e' EXATAMENTE onde a degradacao mora --
     M1 forte: R$4.393,10 (R$209,20/trade, o MELHOR grupo da metade 1)
     M2 forte: R$-1.111,80 (R$-50,54/trade, o UNICO grupo negativo da
     metade 2)
   -- enquanto o tercio "fraco" fica quase estavel (M1 R$107,80/trade ->
   M2 R$92,71/trade). O MESMO padrao aparece cortando por REGIME DE
   VOLATILIDADE trailing (range diario mediano das ultimas 20 sessoes
   concluidas): o tercio de vol ALTA vai de R$3.144,40 (M1) para R$224,90
   (M2, quase zero), o de vol BAIXA fica estavel (R$1.277,70 -> R$833,50).
   Os dois angulos (magnitude do movimento anterior, regime de vol
   trailing) apontam para a MESMA conclusao porque sao correlacionados por
   construcao (dias de vol alta tendem a produzir retornos maiores).

## As 3 classes desta rodada de refino

`ContinuidadeDiariaMagnitudeCap` e `ContinuidadeDiariaVolCap`: mesma logica
de `ContinuidadeDiaria` (SUBCLASSE, reusa `seed_daily_volatility`/
`on_session_start`/`on_bar` da classe pai via `super()` -- nao copia/cola),
so' que ADICIONAM um portao que zera `_pending_side` quando a magnitude/vol
do dia passa de um CORTE FIXO decidido SO' na metade 1 cronologica do IS
(mesma disciplina de `scripts/daytrade/spread_relativo_f7_regime_horizonte.
py`: corte calculado numa metade, aplicado tal e qual na outra, NUNCA
reajustado) -- a APOSTA que a parte "forte"/vol-alta do sinal e' a parte
RUIDOSA, e cortar ela preserva o resto.

`ContinuidadeDiariaDirecaoRolante`: NAO subclasseia `ContinuidadeDiaria`
(a logica de direcao muda por completo) -- reestima `direction`
("continuation" vs "reversal") a CADA pregao usando SO' a correlacao lag-1
dos ultimos `janela_dias` retornos diarios JA CONCLUIDOS (mesmo hook
`seed_daily_volatility`, nunca `bars`/dado futuro). Testada por
COMPLETUDE/honestidade e porque o briefing pediu explicitamente essa
direcao -- o diagnostico (item 1 acima) ja sugere que ela NAO deveria
ajudar muito, porque o sinal da correlacao bruta nao inverteu de fato.

`previous_daily_bars` chega CAPADO em 60 sessoes (`backtest.intraday.
engine._CAUDA_DIAS_MAXIMA`) -- `janela_dias` de `ContinuidadeDiariaDirecao
Rolante` NUNCA deve passar de 60 (usa 60 = o teto inteiro disponivel,
mesma janela que o diagnostico mediu como a mais estavel das 3
testadas)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    JanelaVolatilidadeDiaria,
)
from strategy.daytrade.lab.continuidade_daily import ContinuidadeDiaria, Direction, _flip

#: Corte de |retorno do dia anterior| em PONTOS -- percentil 67 (fronteira
#: do tercil "forte") medido SO' na metade 1 cronologica do IS de WIN@
#: (129 pregoes completos, corte em 2026-03-10 -- MESMO corte de `_metade`
#: em `continuidade_daily_rule.py`). Reproduzivel: ver a secao 3 de
#: `win_daily_continuidade_refino_diagnostico.py`, tercil "M1" -- o proprio
#: numero (nao so' o rotulo "forte") foi obtido rodando `pandas.Series.
#: quantile(0.6667)` sobre `|retorno_sinal_pts|` restrito aos primeiros 64
#: pregoes com trade. NUNCA recalculado usando dado da metade 2.
CUTOFF_MAGNITUDE_PTS_WIN = 2247.8

#: Corte do range diario mediano TRAILING (20 pregoes, so' concluidos) em
#: PONTOS -- percentil 67 medido SO' na metade 1 cronologica (mesmo split
#: acima). Reproduzivel do mesmo jeito, secao 4 do diagnostico, tercil
#: "M1"/"alta".
CUTOFF_VOL_PTS_WIN = 3590.0

#: Janela do range trailing -- mesma da secao 4 do diagnostico.
VOL_JANELA_DIAS_WIN = 20

#: Janela da correlacao rolante. O diagnostico mediu 40/60/80 pregoes;
#: 60 seria a mais estavel das 3 (menos trocas de sinal), mas sob o teste
#: de METADE cada metade backtesta do ZERO (`_metade`/`continuidade_daily_
#: rule.py` roda metade1 e metade2 como series INDEPENDENTES, sem carregar
#: o historico da outra -- mesmo desenho do resto desta investigacao, para
#: nenhuma metade "ver" a outra) -- janela=60 dentro de uma metade de so'
#: 64-65 pregoes deixaria so' 4-5 pregoes de warmup completo por metade,
#: teste de metade praticamente vazio (medido: 0 trades em qualquer
#: subconjunto na 1a tentativa desta rodada, `janela_dias=60`). 20 preserva
#: ~44-45 pregoes de trade por metade (warmup de 20 sobre 64-65) e ainda
#: cobre a maior parte do periodo onde a corr rolante-40 do diagnostico fica
#: estavelmente negativa.
JANELA_DIRECAO_ROLANTE_DIAS = 20


class ContinuidadeDiariaMagnitudeCap(ContinuidadeDiaria):
    """`ContinuidadeDiaria` + portao: fica DE FORA quando
    `|close[D] - close[D-1]| > cutoff_pts` -- exclui o tercio "forte" do
    diagnostico, onde a degradacao metade1->metade2 mora inteira."""

    name = "continuidade_diaria_magnitude_cap"
    version = "0.1"

    def __init__(
        self,
        symbol: str,
        direction: Direction = "reversal",
        cutoff_pts: float = CUTOFF_MAGNITUDE_PTS_WIN,
        quantity: int | None = None,
    ):
        super().__init__(symbol=symbol, direction=direction, quantity=quantity)
        self.cutoff_pts = float(cutoff_pts)

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        super().seed_daily_volatility(previous_daily_bars)
        if self._pending_side is None or len(previous_daily_bars) < 2:
            return
        retorno = previous_daily_bars[-1].close - previous_daily_bars[-2].close
        if abs(retorno) > self.cutoff_pts:
            self._pending_side = None  # dia "forte" -- fora, e' onde a degradacao mora


class ContinuidadeDiariaVolCap(ContinuidadeDiaria):
    """`ContinuidadeDiaria` + portao: fica DE FORA quando o range diario
    mediano TRAILING (`vol_janela_dias` sessoes ja concluidas, MESMO padrao
    anti-look-ahead de `JanelaVolatilidadeDiaria`) passa de `cutoff_pts` --
    exclui o regime de vol "alta" do diagnostico."""

    name = "continuidade_diaria_vol_cap"
    version = "0.1"

    def __init__(
        self,
        symbol: str,
        direction: Direction = "reversal",
        vol_janela_dias: int = VOL_JANELA_DIAS_WIN,
        cutoff_pts: float = CUTOFF_VOL_PTS_WIN,
        quantity: int | None = None,
    ):
        super().__init__(symbol=symbol, direction=direction, quantity=quantity)
        self.vol_janela_dias = int(vol_janela_dias)
        self.cutoff_pts = float(cutoff_pts)

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        super().seed_daily_volatility(previous_daily_bars)
        if self._pending_side is None:
            return
        janela = JanelaVolatilidadeDiaria(janela_dias=self.vol_janela_dias)
        for bar_diaria in previous_daily_bars[-self.vol_janela_dias:]:
            janela.registrar_dia(bar_diaria)
        trailing = janela.range_mediano()
        if trailing is None:
            self._pending_side = None  # historico insuficiente -- fora, nao assume regime
            return
        if trailing > self.cutoff_pts:
            self._pending_side = None  # regime de vol "alta" -- fora


class ContinuidadeDiariaDirecaoRolante(IntradayStrategy):
    """Mesma mecanica de entrada de `ContinuidadeDiaria` (1 decisao por
    pregao, na 1a barra, sem timing), mas `direction` e' RECALCULADA a cada
    pregao a partir da correlacao lag-1 dos ultimos `janela_dias` retornos
    diarios JA CONCLUIDOS (`seed_daily_volatility`, nunca dado futuro) --
    NAO herda de `ContinuidadeDiaria` porque a logica de decidir o lado
    muda por completo (a classe pai recebe `direction` fixo de fora)."""

    name = "continuidade_diaria_direcao_rolante"
    version = "0.1"

    def __init__(
        self,
        symbol: str,
        janela_dias: int = JANELA_DIRECAO_ROLANTE_DIAS,
        quantity: int | None = None,
    ):
        if janela_dias > 60:
            raise ValueError(
                "janela_dias > 60 nunca teria dado suficiente -- "
                "`previous_daily_bars` vem capado em 60 sessoes por "
                "`backtest.intraday.engine._CAUDA_DIAS_MAXIMA`"
            )
        self.symbol = symbol
        self.janela_dias = int(janela_dias)
        self.quantity = quantity
        self._pending_side: str | None = None
        self._today_side: str | None = None
        self._entered_today = False

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        # exige pelo menos `janela_dias` fechamentos (janela_dias-1
        # retornos) para a correlacao rolante nao rodar com amostra
        # minuscula/ruidosa logo no inicio do historico. NAO pede
        # `janela_dias + 1`: `previous_daily_bars` vem capado em 60 sessoes
        # (`backtest.intraday.engine._CAUDA_DIAS_MAXIMA`) -- exigir um a
        # mais que `janela_dias` tornaria `janela_dias=60` estruturalmente
        # impossivel de satisfazer (bug medido na 1a tentativa desta
        # rodada: 0 trades em QUALQUER subconjunto, full IS incluido).
        if len(previous_daily_bars) < self.janela_dias:
            self._pending_side = None
            return
        window = previous_daily_bars[-self.janela_dias:]
        closes = np.array([b.close for b in window], dtype=float)
        rets = np.diff(closes)  # janela_dias - 1 retornos, mais antigo primeiro
        if len(rets) < 3:
            self._pending_side = None
            return
        corr = float(np.corrcoef(rets[:-1], rets[1:])[0, 1])
        retorno_ultimo = rets[-1]
        if np.isnan(corr) or corr == 0.0 or retorno_ultimo == 0.0:
            self._pending_side = None
            return
        lado_bruto = "long" if retorno_ultimo > 0 else "short"
        # corr < 0 -> regime de REVERSAO (aposta oposta); corr > 0 ->
        # regime de CONTINUACAO (mesmo lado) -- mesma convencao de sinal de
        # `ContinuidadeDiaria`/`continuidade_stats.py`.
        self._pending_side = lado_bruto if corr > 0 else _flip(lado_bruto)

    def on_session_start(self, session_date) -> None:
        self._today_side = self._pending_side
        self._entered_today = False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._entered_today or self._today_side is None or positions:
            return []
        self._entered_today = True
        return [Enter(
            side=self._today_side,  # type: ignore[arg-type]
            quantity=self.quantity,
            reason="continuidade_diaria_direcao_rolante",
        )]
