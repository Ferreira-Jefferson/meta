"""Frente F8-win-lacuna-execucao -- aritmetica de breakeven ANTES de rodar
qualquer backtest (pedido explicito da missao).

Pergunta 1: existe T (alvo, em ticks) maior que 2 ou espacamento muito maior
que o testado (0/60 celulas) capaz de escapar do veredito negativo?

Aqui a conta e' feita de duas formas, para nao depender so' de uma:

(a) Taxa de acerto EXIGIDA (breakeven) por combinacao de T (alvo) e S
    (stop), sob o mesmo modelo de custo do resto do projeto
    (`backtest.intraday.costs.IntradayCostModel`, ver
    `backtest.intraday.profiles.FUTURES_PROFILES["WIN@"]`): tick = R$1,00,
    tarifa de ida-e-volta R$0,50 (0,5 tick), e a saida por STOP paga
    `slippage_ticks=1.0` (e' ordem a mercado -- a saida por ALVO e' maker,
    `target_fills_as_maker=True`, e portanto NAO paga slippage, ver
    `machine.py` linha ~1548).

        p_breakeven = [ (S + slip) + fee_ticks + pedagio_total ] / (T + S + slip)

(b) Valor esperado por trade sob a hipotese de "jogo justo" localmente --
    ou seja, ASSUMINDO que a probabilidade real de tocar o alvo antes do
    stop segue a formula classica de ruina do apostador para um passeio
    aleatorio simetrico, p_toque = S / (S + T). Essa hipotese e' exatamente
    o que o achado MFE=MAE (razao 0,97-1,01 em todo horizonte, ja
    estabelecido no projeto) da' suporte empirico: sem deriva mensuravel,
    a excursao favoravel e desfavoravel sao estatisticamente iguais.

        EV/trade (ticks) = p_toque*T - (1-p_toque)*(S+slip) - fee_ticks - pedagio_total
                          = - T*slip/(S+T) - fee_ticks - pedagio_total     [ALGEBRA, ver docstring principal]

    Este EV e' <= -fee_ticks-pedagio_total SEMPRE (o termo T*slip/(S+T) e'
    estritamente positivo pra T>0, e CRESCE com T a S fixo) -- ou seja,
    sob a hipotese de jogo justo, AUMENTAR o alvo T NUNCA melhora o EV
    esperado por trade; so' piora (mais stops, cada um pagando slip). O
    minimo de perda (o "teto" mais favoravel possivel) e' T->0 (T=1, o
    caso ja testado), com EV -> -fee_ticks-pedagio_total conforme S cresce.

    Isso ja responde a pergunta por ALGEBRA, sem rodar nada: se T=1 (o
    caso mais favoravel da familia) ja perde sob custo minimo, nenhum T>1
    escapa -- o gradiente aponta na direcao ERRADA.
"""
from __future__ import annotations

FEE_ROUND_TRIP_BRL = 0.50   # FUTURES_FEE_ROUND_TRIP_BRL, profiles.py
TICK_VALUE_BRL = 1.00       # WIN@: price_tick_size=5.0 pts, point_value=R$0,20/pt -> R$1,00/tick
SLIPPAGE_TICKS = 1.0        # default IntradayCostModel.slippage_ticks, paga na saida por STOP (mercado)
FEE_TICKS = FEE_ROUND_TRIP_BRL / TICK_VALUE_BRL  # 0.5 tick


def p_breakeven(T: int, S: int, pedagio_ticks_total: float = 0.0) -> float:
    return (S + SLIPPAGE_TICKS + FEE_TICKS + pedagio_ticks_total) / (T + S + SLIPPAGE_TICKS)


def ev_ticks_jogo_justo(T: int, S: int, pedagio_ticks_total: float = 0.0) -> float:
    """EV/trade em TICKS sob p_toque = S/(S+T) (ruina do apostador,
    passeio aleatorio simetrico -- a hipotese que MFE=MAE sustenta)."""
    p = S / (S + T)
    return p * T - (1 - p) * (S + SLIPPAGE_TICKS) - FEE_TICKS - pedagio_ticks_total


def main() -> None:
    print("=== (a) taxa de acerto EXIGIDA (breakeven), pedagio=0 (piso, sem taxa de fila) ===")
    print(f"{'T':>4} {'S':>4} {'p_breakeven':>12}")
    for T in [1, 2, 3, 5, 8, 13, 20, 40, 80]:
        for S in [8, 16, 32, 64]:
            p = p_breakeven(T, S, 0.0)
            flag = " (IMPOSSIVEL >100%)" if p > 1.0 else ""
            print(f"{T:>4} {S:>4} {p*100:>11.2f}%{flag}")
        print()

    print("=== (a2) mesma conta, pedagio=1 tick x 2 pernas maker = 2.0 ticks extras ===")
    for T in [1, 2, 3, 5, 8]:
        S = 16
        p = p_breakeven(T, S, pedagio_ticks_total=2.0)
        flag = " (IMPOSSIVEL >100%)" if p > 1.0 else ""
        print(f"T={T:>3} S={S}: p_breakeven={p*100:.2f}%{flag}")

    print("\n=== (b) EV/trade em R$ sob jogo justo (p_toque=S/(S+T)), pedagio=0 ===")
    print("(se isto ja for negativo p/ T=1 -- o caso mais favoravel -- nenhum T maior escapa)")
    print(f"{'T':>4} {'S':>4} {'EV_ticks':>10} {'EV_R$':>10}")
    for T in [1, 2, 3, 5, 8, 13, 20, 40, 80]:
        for S in [8, 16, 32, 64]:
            ev = ev_ticks_jogo_justo(T, S, 0.0)
            print(f"{T:>4} {S:>4} {ev:>10.4f} {ev*TICK_VALUE_BRL:>10.4f}")
        print()

    print("=== (b2) confere: EV piora monotonicamente com T, a S fixo (S=32) ===")
    S = 32
    prev = None
    for T in [1, 2, 3, 5, 8, 13, 20, 40, 80, 160]:
        ev = ev_ticks_jogo_justo(T, S, 0.0)
        direcao = "" if prev is None else ("PIOROU" if ev < prev else "melhorou")
        print(f"T={T:>4} EV={ev:>9.4f} ticks  {direcao}")
        prev = ev

    print("\n=== range diario disponivel vs T extremo (WIN@, medicao do perfil) ===")
    RANGE_MEDIANO_PTS = 2968.0
    TICK_PTS = 5.0
    range_mediano_ticks = RANGE_MEDIANO_PTS / TICK_PTS
    print(f"range diario mediano: {RANGE_MEDIANO_PTS:.0f} pts = {range_mediano_ticks:.1f} ticks")
    for T in [20, 40, 80, 160]:
        pct = 100 * T / range_mediano_ticks
        print(f"  T={T:>4} ticks = {T*TICK_PTS:>6.0f} pts = {pct:5.1f}% do range mediano do dia")


if __name__ == "__main__":
    main()
