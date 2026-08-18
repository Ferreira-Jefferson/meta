"""Politica de saque — overlay de gestao de capital sobre `portfolio_dip2_hw40`.

Motivacao: reduzir o MaxDD do robo por dentro da estrategia se mostrou
praticamente impossivel sem destruir o capital final (duas rodadas de
experimentos, 61 hipoteses, 0 aprovadas). A alternativa e nao manter 100% do
patrimonio exposto: retirar lucro periodicamente para um caixa externo. O
drawdown da CARTEIRA continua o mesmo — o que cai e o drawdown do PATRIMONIO
(carteira + caixa retirado), porque parte do dinheiro deixou de estar em risco.

Contrato com o engine (anti-look-ahead preservado):
  - `on_close(date, equity, invested)` e chamado no fecho de cada barra e devolve
    o valor a sacar. Esse saque e executado na ABERTURA do dia seguinte,
    exatamente como qualquer ordem de trade (regra 4 do AGENTS.md).
  - `on_liquidity_event(date, equity, reason)` e chamado quando uma venda do robo
    acabou de creditar caixa no open[D] — ali o saque nao paga liquidacao extra.
  - `on_executed(date, executed)` informa quanto SAIU de fato (pode ser menor que
    o pedido: gap de preco, cotas insuficientes).

Politicas sao puras: nenhum I/O, nenhuma leitura de banco, nenhum acesso ao
futuro. Sao portaveis para MQL5 junto com as estrategias.

================================================================================
DECISAO (2026-08-17) — `FloorSkim(pct=0.010, floor=55_000, min_amount=1_000)`
================================================================================
Escolhida pelo usuario. Ver `official_policy()`. Janela FULL 2010-01-01 ->
2026-08-14, capital inicial R$1.000, lote fracionario, caixa sacado rendendo
Selic diaria real. REF (sem saque) = patrimonio R$169.636, MaxDD 5A -32,99%.

    carteira final       R$  99.123
    caixa sacado+Selic   R$  54.175
    PATRIMONIO           R$ 153.298   (-9,6% vs REF)
    sacado total         R$  37.142   em 30 parcelas de R$1.019 a R$1.721
    MaxDD patrimonio 5A      -24,18%   (REF -32,99%)
    MaxDD estrategia (TWR)   -35,12%   (identico ao REF — o robo nao e tocado)
    intervalo entre saques    78 dias em media (5A), maior seca 335 dias

ALTERNATIVAS MEDIDAS E DESCARTADAS (numeros preservados aqui de proposito: sem
eles a escolha viraria dogma, e alguem re-implementaria as refutadas). Todas na
mesma janela, mesma metrica de patrimonio:

  familia "% do lucro" — sacam desde 2011, quando a carteira valia R$1.000, e
  cada real dali foi multiplicado por ~170 depois. Teto estrutural de eficiencia:
    10% do lucro por ROTACAO ....... R$131.745 (-22,3%), sacado R$ 7.800, 2 saques/61 meses
    10% do lucro do ANO ............ R$130.899 (-22,8%), sacado R$10.244
    25% do lucro do ANO ............ R$ 88.922 (-47,6%)
    10% do ganho ACUMULADO/ano ..... R$ 88.832 (-47,6%)
    resgata principal em 2x ........ R$ 88.103 (-48,1%)
    10% a cada topo +25% ........... R$ 62.590 (-63,1%)
    montante composto (o nao-sacado virava base do saque seguinte) era a regra
    dessa familia; com piso absoluto ela deixa de fazer sentido — o piso E o
    montante, imutavel.

  salario fixo em reais (`FixedFloorSalary`, R$400/mes acima de 40k):
    R$150.504 (-11,3%) — pro-ciclico ao contrario: numa queda o valor fixo pesa
    proporcionalmente mais e drena no pior momento.

  excecao de piso quando o robo esta fora do mercado (`flat_floor`):
    liberar o saque com o robo 100% em caixa (a base nao esta compondo) REABRE o
    buraco do saque precoce: R$128.710 (-24,1%), sacando MENOS (R$28.295) e em
    MENOS meses (37 vs 40/61), com saque minimo caindo a R$8. Com piso secundario
    de 20k funciona (R$147.441, 45/61) mas perde para simplesmente baixar o piso
    unico para 45k (R$146.732, 55/61) — mais saque, mais meses, um parametro a
    menos. Para comprar regularidade: baixe o piso, nao adicione excecao.

  aportar menos desde o inicio (sem saque, 70% robo / 30% Selic):
    R$120.258 (-29,1%) por apenas 1,75 p.p. de DD — pior que qualquer saque. A
    perna estatica de Selic vira 1,2% do patrimonio; o colchao precisa CRESCER
    com a carteira, e e isso que o saque faz.

  fronteira do piso a 1,0%/mes + minimo R$1.000 (a escolha final e o 55k):
    45k -> R$145.979, sacado R$41.859, 25 saques/5A
    50k -> R$149.793, sacado R$40.761, 24 saques/5A
    55k -> R$153.298, sacado R$37.142, 24 saques/5A   <-- ESCOLHIDA
    60k -> R$156.845, sacado R$34.402, 21 saques/5A, maior seca 485 dias
    Cambio marginal de descer o piso: ~R$1,29 de patrimonio por real antecipado.

LIMITE CONHECIDO: nenhuma politica de piso melhora o MaxDD FULL de -35,12%. Esse
evento e de 2017, com a carteira em R$18.585 — abaixo de qualquer piso util, e
portanto anterior ao mecanismo existir. O ganho e no risco PROSPECTIVO (5A).

LEITURA DO PISO: R$55.000 e 55x o capital inicial de R$1.000 do criterio oficial
de ranking. Com esse capital os saques so comecam em set/2020 (a carteira leva 10
anos para cruzar o piso). Operando com capital real diferente, o piso tem de ser
re-lido como multiplo do aporte — nao copiar R$55.000 em absoluto, senao o saque
comeca no primeiro mes e o mecanismo que faz a politica funcionar (nao sacar
cedo) deixa de existir.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


# ---------- registro de eventos -------------------------------------------

@dataclass
class WithdrawalEvent:
    """Um saque efetivamente executado (auditoria)."""

    date: pd.Timestamp
    requested: float          # valor pedido pela politica no close[D-1]
    executed: float           # valor que saiu de fato do caixa no open[D]
    equity_before: float      # equity da carteira no close da decisao
    fees_paid: float = 0.0    # custos de liquidar posicao para levantar o caixa
    liquidated: list[tuple[str, int, float]] = field(default_factory=list)
    # ^ (ticker, quantidade vendida, preco de execucao)

    @property
    def shortfall(self) -> float:
        return max(0.0, self.requested - self.executed)


# ---------- politica -------------------------------------------------------

class WithdrawalPolicy(ABC):
    """Decide quanto sacar. Estado interno proprio, sem I/O."""

    label: str = "policy"

    @abstractmethod
    def on_close(self, date: pd.Timestamp, equity: float, invested: float = 0.0) -> float:
        """Valor a sacar, decidido no close[D] e executado no open[D+1]. 0 = nada.

        `invested` = valor a mercado das posicoes no fecho (0 = robo 100% em
        caixa, tipicamente sob gate de Selic/IBOV defensivo).
        """

    def on_liquidity_event(self, date: pd.Timestamp, equity: float, reason: str) -> float:
        """Valor a sacar QUANDO O ROBO ACABOU DE VENDER, executado na mesma barra.

        Disparado por qualquer saida que credita caixa no open[D] — rotacao de
        ativo (`'rotation_out'`), stop (`'stop'`) ou saida defensiva de Selic/IBOV
        (`'ibov_defensive'`). Nesses dias o dinheiro esta liquido em maos: o saque
        nao custa liquidacao extra (nem corretagem, nem slippage) e a compra
        seguinte e dimensionada pelo que sobrou. `equity` vem marcado no open[D],
        nunca no close (que ainda nao aconteceu). Default: ignora.
        """
        return 0.0

    def on_executed(self, date: pd.Timestamp, executed: float) -> None:  # noqa: B027
        """Confirmacao do valor que saiu de fato. Default: nada a ajustar."""
        return None

    def state(self) -> dict:
        """Estado interno para sobreviver a um restart do processo ao vivo.

        No backtest a politica vive do comeco ao fim num processo so; ao vivo
        o processo reinicia (deploy, reboot, queda de energia) e perde toda
        memoria local. O que precisa sobreviver e exatamente o que cada
        politica guarda como atributo de instancia PRIVADO (prefixo `_`):
        contador de pregoes do mes, mes ja pago, fila do minimo, topo
        historico etc (ver `FloorSkim.__init__`). Um restart no dia 10 do mes
        sem reidratar esse estado zera o contador — a politica passa a pagar
        fora do dia combinado, ou paga duas vezes no mesmo mes, ou perde a
        fila do minimo acumulado.

        Implementacao GENERICA nesta classe-base, de proposito: qualquer
        subclasse que siga a convencao de prefixar estado privado com `_`
        ganha `state()`/`restore()` de graca, sem reescrever nada especifico
        de `FloorSkim`. Ver `restore` para o cuidado com tupla vs lista.
        """
        return {k: v for k, v in vars(self).items() if k.startswith("_")}

    def restore(self, state: dict) -> None:
        """Reidrata o estado devolvido por `state()`, tipicamente apos um restart.

        Detalhe que morde: em `FloorSkim`, `_month`, `_paid_month` e
        `_accrued_month` sao TUPLAS `(ano, mes)`. Mas o caminho real deste
        estado — sair de um processo, ser persistido, voltar num processo
        novo — normalmente passa por JSON (`json.loads(json.dumps(...))`), e
        JSON nao tem tipo tupla: uma tupla vira lista na volta. Sem normalizar
        de volta aqui, `month != self._month` fica SEMPRE True (lista nunca
        `==` tupla em Python, mesmo com os mesmos elementos) — a politica
        passa a se comportar como se todo pregao fosse o primeiro do mes, e
        nunca (ou sempre) paga.

        A heuristica generica "lista recebida na restauracao => era tupla no
        original" e segura porque nenhuma politica hoje guarda lista de
        verdade em estado privado (so tupla ou escalar). Uma politica futura
        que precise de uma lista como estado de fato teria de sobrescrever
        este metodo.
        """
        for k, v in state.items():
            setattr(self, k, tuple(v) if isinstance(v, list) else v)


class FloorSkim(WithdrawalPolicy):
    """Saca `pct` do EQUITY uma vez por mes, mas so acima de um PISO ABSOLUTO.

    O que separa esta politica das descartadas (ver docstring do modulo): o custo
    de um saque nao e proporcional, e TEMPORAL. Um real retirado em 2011, quando a
    carteira valia R$1.000, foi multiplicado por ~170 depois; o mesmo real em 2025
    custa quase nada de composicao. O piso simplesmente nao deixa o saque comecar
    antes de a carteira atingir um patamar de riqueza declarado. Medido: mesma
    politica de 0,5%/mes SEM piso custa R$4,37 de patrimonio por real sacado;
    com piso de 40k, R$0,57.

    Mecanica:
      - saca no `day`-esimo pregao de cada mes (calendario, previsivel), OU
        antecipa para um evento de liquidez do mes (rotacao/stop/saida defensiva),
        onde o caixa ja esta em maos e o saque nao paga liquidacao — o que vier
        primeiro, uma vez por mes;
      - valor = `min(equity * pct, equity - floor, cap)` — nunca derruba a
        carteira abaixo do piso, nunca passa do `cap`;
      - `min_amount`: parcela abaixo do minimo nao sai, mas NAO se perde — fica
        numa fila e sai somada quando o acumulado bate o minimo. Mede-se quase
        neutro em patrimonio (-0,06%) e troca muitos saques pequenos por menos
        saques maiores;
      - `dd_guard` (opcional): nao saca enquanto o equity estiver mais que
        `dd_guard` abaixo do proprio topo historico (nao vende capital ferido).
        Preserva mais capital (-4,8% com 0,5%/40k) ao custo de irregularidade.

    Fixando o piso, o patrimonio final e um PLATO no `pct` (com piso 60k, variar
    0,5% -> 1,5% move o patrimonio em 0,6% enquanto o valor sacado varia 60%): o
    piso limita a extracao TOTAL, o `pct` so decide a velocidade.

    `cap` default R$20.000 = teto mensal de vendas isentas de IR para pessoa
    fisica em acoes no mercado a vista (Lei 11.033/2004, art. 3, I). Mantem cada
    saque dentro da isencao — o maior saque medido criou venda de R$1.718, folga
    de 12x. Quem estoura o limite e a ROTACAO do robo (vende a posicao inteira),
    nao o saque.
    """

    def __init__(
        self,
        pct: float = 0.010,
        floor: float = 55_000.0,
        day: int = 3,
        cap: float = 20_000.0,
        min_amount: float = 1_000.0,
        dd_guard: float | None = None,
    ) -> None:
        self.pct = float(pct)
        self.floor = float(floor)
        self.day = int(day)
        self.cap = float(cap)
        self.min_amount = float(min_amount)
        self.dd_guard = dd_guard
        guard = f"_dd{int(round(dd_guard * 100))}" if dd_guard else ""
        minimo = f"_min{self.min_amount:.0f}" if min_amount else ""
        self.label = f"piso_{self.floor:.0f}_{pct * 100:.2f}pct_mes{minimo}{guard}"
        self._month: tuple | None = None
        self._sessions = 0
        self._paid_month: tuple | None = None
        self._accrued_month: tuple | None = None
        self._pool = 0.0            # parcelas ainda nao sacadas (fila do minimo)
        self._requested = 0.0       # ultimo valor pedido, p/ reconciliar shortfall
        self._peak = 0.0

    def _amount(self, equity: float) -> float:
        """Parcela do mes: percentual do equity, limitada pelo piso e pelo cap."""
        if equity <= self.floor:
            return 0.0
        if self.dd_guard is not None and self._peak > 0:
            if equity / self._peak - 1.0 < -self.dd_guard:
                return 0.0
        return max(0.0, min(equity * self.pct, equity - self.floor, self.cap))

    def _accrue_and_pay(self, month: tuple, equity: float) -> float:
        """Acumula a parcela do mes na fila e paga se o acumulado bater o minimo."""
        if self._paid_month == month:
            return 0.0
        if self._accrued_month != month:
            entitlement = self._amount(equity)
            if entitlement <= 0.0:
                # abaixo do piso ou guarda de DD ativa: nao acumula nem paga
                return 0.0
            self._pool += entitlement
            self._accrued_month = month
        allowed = min(self._pool, max(0.0, equity - self.floor), self.cap)
        if allowed <= 0.0 or allowed < self.min_amount:
            return 0.0            # fica na fila para o mes seguinte
        self._paid_month = month
        self._pool -= allowed
        self._requested = allowed
        return allowed

    def on_close(self, date: pd.Timestamp, equity: float, invested: float = 0.0) -> float:
        self._peak = max(self._peak, equity)
        month = (date.year, date.month)
        if month != self._month:
            self._month = month
            self._sessions = 0
        self._sessions += 1
        if self._sessions != self.day:
            return 0.0
        return self._accrue_and_pay(month, equity)

    def on_liquidity_event(self, date: pd.Timestamp, equity: float, reason: str) -> float:
        return self._accrue_and_pay((date.year, date.month), equity)

    def on_executed(self, date: pd.Timestamp, executed: float) -> None:
        # se saiu menos que o pedido (gap de preco, cotas insuficientes), a
        # diferenca volta para a fila em vez de desaparecer
        falta = self._requested - executed
        if falta > 0.0:
            self._pool += falta
        self._requested = 0.0


# Configuracao escolhida (2026-08-17) — ver o registro de decisao no topo.
# Multiplo do capital inicial do criterio oficial de ranking (R$1.000).
OFFICIAL_FLOOR_MULTIPLE: float = 55.0
OFFICIAL_PCT: float = 0.010
OFFICIAL_MIN_AMOUNT: float = 1_000.0


def official_policy(initial_capital: float = 1_000.0) -> FloorSkim:
    """A politica de saque escolhida, ja parametrizada.

    Fabrica (nao constante) de proposito: `FloorSkim` guarda estado entre barras,
    entao cada backtest precisa de uma instancia nova — reutilizar uma instancia
    entre runs contamina o resultado com a fila e o topo do run anterior.

    O piso acompanha o capital inicial (55x), nao um valor absoluto: ver a nota
    "LEITURA DO PISO" no topo do modulo.
    """
    return FloorSkim(
        pct=OFFICIAL_PCT,
        floor=OFFICIAL_FLOOR_MULTIPLE * initial_capital,
        min_amount=OFFICIAL_MIN_AMOUNT,
    )


# ---------- analitica do overlay (pura) -----------------------------------

def external_cash_curve(
    events: list[WithdrawalEvent],
    index: pd.DatetimeIndex,
    daily_rate_pct: pd.Series | None = None,
) -> pd.Series:
    """Saldo do caixa externo (dinheiro sacado) ao longo do tempo.

    `daily_rate_pct`: taxa livre de risco em **% por dia** (formato da serie
    Selic do BCB, ex. 0.0517 = 0,0517%/dia). None → caixa parado, sem juros.
    """
    balance = 0.0
    by_date = {pd.Timestamp(e.date): e.executed for e in events}
    out: list[float] = []
    for d in index:
        if daily_rate_pct is not None:
            r = daily_rate_pct.get(d)
            if r is not None and pd.notna(r):
                balance *= 1.0 + float(r) / 100.0
        balance += by_date.get(d, 0.0)
        out.append(balance)
    return pd.Series(out, index=index, dtype=float)


def reinvested_equity_curve(equity: pd.Series, events: list[WithdrawalEvent]) -> pd.Series:
    """Curva time-weighted: como a carteira teria andado sem os saques.

    O equity com saque tem quedas que nao sao perda de mercado — usar MaxDD
    direto nele superestima o risco. Aqui os fluxos de saida sao neutralizados
    (retorno diario = (E_t + saque_t) / E_{t-1} - 1) para isolar o desempenho
    da ESTRATEGIA. E nessa curva que o MaxDD e comparavel ao run de referencia.
    """
    if equity.empty:
        return equity
    by_date = {pd.Timestamp(e.date): e.executed for e in events}
    vals = [float(equity.iloc[0])]
    prev = float(equity.iloc[0])
    for d, e in list(equity.items())[1:]:
        e = float(e)
        if prev <= 0:
            vals.append(vals[-1])
            prev = e
            continue
        r = (e + by_date.get(pd.Timestamp(d), 0.0)) / prev - 1.0
        vals.append(vals[-1] * (1.0 + r))
        prev = e
    return pd.Series(vals, index=equity.index, dtype=float)
