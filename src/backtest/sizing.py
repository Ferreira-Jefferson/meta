"""Mecanica de execucao compartilhada entre o backtest e a operacao ao vivo.

Por que este modulo existe
--------------------------
A decisao de COMPRAR e da estrategia (`strategy/`). O tamanho da compra nao e:
quantas cotas cabem no caixa, qual o lote, quanto reservar para taxas, onde fica
o stop quando o robo nao pede um, e quantas posicoes simultaneas sao permitidas
— tudo isso e do ENGINE, parametrizado por `BacktestConfig`, e a estrategia nunca
ve.

Isso era invisivel enquanto so existia backtest. Passa a ser o maior risco de
divergencia quando existe operacao real: se o runtime ao vivo recalcular o
tamanho "do seu jeito", o robo que opera deixa de ser o robo que foi testado —
e a diferenca aparece em cada entrada, silenciosamente, como um erro de
arredondamento que compoe por 16 anos.

Entao a regra e: existe UMA implementacao, aqui, pura, e os dois lados chamam.
Se este arquivo mudar, os dois mudam juntos — que e exatamente o que se quer.

Verificacao: extraido verbatim do bloco de entrada de `engine_portfolio.py`. O
capital final FULL do `portfolio_dip2_hw40` (R$ 169.635,72 com R$ 1.000 iniciais)
tem de continuar identico ao centavo depois da refatoracao — e o teste que prova
que a extracao nao mudou comportamento.
"""
from __future__ import annotations

from dataclasses import dataclass

from backtest.costs import apply_slippage, fees_for_leg
from core.config import BacktestConfig

# Folga extra sobre a reserva de taxas. Sem ela, o arredondamento do calculo de
# cotas pode produzir uma ordem cujo custo total estoura o caixa por centavos, e
# a entrada e simplesmente descartada. Valor herdado do engine — mexer aqui muda
# o historico de backtest inteiro.
_BUDGET_MARGIN = 1e-4


@dataclass(frozen=True)
class EntryPlan:
    """Quanto comprar e quanto custa. `quantity == 0` significa entrada inviavel."""

    quantity: int
    exec_price: float
    gross: float
    fees: float
    cost: float

    @property
    def is_feasible(self) -> bool:
        return self.quantity > 0


def plan_entry(
    cash: float,
    ref_price: float,
    size_hint: float | None,
    config: BacktestConfig,
) -> EntryPlan:
    """Dimensiona uma entrada a partir do preco de referencia (o open do dia).

    `size_hint` e a fracao do caixa que a estrategia pediu (`Enter.size_hint`);
    None ou <= 0 significa "use o caixa todo". O preco de execucao ja sai com
    slippage de compra aplicado — e sobre ele que as cotas sao contadas, senao o
    slippage viraria um estouro de caixa na hora do fill.

    Inviabilidade tem duas causas e as duas devolvem `quantity == 0`: nao cabe um
    lote, ou o custo total com taxas passou do caixa.
    """
    exec_price = apply_slippage(ref_price, "buy", config.costs)
    slot_budget = cash * float(size_hint) if (size_hint and size_hint > 0) else cash
    budget = slot_budget * (1.0 - config.costs.per_side_pct - _BUDGET_MARGIN)
    quantity = int(budget // (exec_price * config.lot_size)) * config.lot_size
    if quantity <= 0:
        return EntryPlan(0, exec_price, 0.0, 0.0, 0.0)
    gross = exec_price * quantity
    fees = fees_for_leg(gross, config.costs, quantity)
    cost = gross + fees
    if cost > cash:
        return EntryPlan(0, exec_price, 0.0, 0.0, 0.0)
    return EntryPlan(quantity, exec_price, gross, fees, cost)


def initial_stop(
    exec_price: float,
    requested: float | None,
    config: BacktestConfig,
) -> float | None:
    """Stop de entrada: o que a estrategia pediu, ou o default do config.

    A estrategia manda quando tem opiniao (`Enter.initial_stop`). Quando nao
    tem, o engine aplica `config.stop_loss_pct` sobre o preco de execucao — nao
    sobre o preco de referencia, porque o risco real do trade e medido do preco
    que se pagou. `None` sem default = posicao sem stop, fechada so por `Exit`.
    """
    if requested is not None:
        return float(requested)
    if config.stop_loss_pct > 0:
        return exec_price * (1.0 - config.stop_loss_pct)
    return None


def has_free_slot(open_positions: int, config: BacktestConfig) -> bool:
    """Ha vaga para mais uma posicao simultanea?

    Teto do engine, nao da estrategia: um robo pode pedir 8 entradas e receber 5.
    Ao vivo o teto tem de ser o mesmo, senao a carteira real fica mais
    concentrada (ou mais diluida) que a testada.
    """
    return open_positions < config.max_concurrent_positions


def liquidation_quantity(
    needed_cash: float,
    exec_price: float,
    available_qty: int,
    config: BacktestConfig,
) -> int:
    """Quantas cotas vender para levantar `needed_cash` liquido de taxas.

    Usado pelo saque quando o caixa nao cobre o valor pedido. Arredonda para
    cima (`ceil`) de proposito: vender de menos deixa o saque incompleto e a
    diferenca volta para a fila da politica, o que atrasa o pagamento sem
    reduzir o custo. Limitado pela posicao disponivel.
    """
    import math

    net_per_share = exec_price * (1.0 - config.costs.per_side_pct)
    if net_per_share <= 0:
        return 0
    return max(0, min(available_qty, math.ceil(needed_cash / net_per_share)))
