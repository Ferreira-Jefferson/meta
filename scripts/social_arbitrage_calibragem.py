"""Relatorio de calibragem do ledger de arbitragem social -- le as teses
FECHADAS e mostra, por lente, se o win% realizado bate com o que foi
estimado (Kelly) e onde fica o breakeven empirico. Nunca imprime veredito
quando o IC atravessa o breakeven ou quando `n` e' baixo -- ver
`social_arbitrage/calibragem.py`.

Uso:
    python scripts/social_arbitrage_calibragem.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_arbitrage.calibragem import LinhaCalibragem, calibrar  # noqa: E402
from social_arbitrage.store import SocialArbitrageStore  # noqa: E402


def _fmt_pct(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "--"


def _fmt_brl(x: float | None) -> str:
    return f"R${x:,.2f}" if x is not None else "--"


def _fmt_ic(ic: tuple[float, float] | None) -> str:
    return f"[{ic[0]:.1%} ; {ic[1]:.1%}]" if ic is not None else "--"


def _imprimir_linha(linha: LinhaCalibragem) -> None:
    print(f"\n== {linha.grupo} (n={linha.n}) ==")
    if linha.n == 0:
        print("  nenhuma tese fechada ainda.")
        return
    print(f"  win%            : {_fmt_pct(linha.win_pct)}  IC95 {_fmt_ic(linha.ic95_win_pct)}" + ("  [n BAIXO -- IC pouco confiavel]" if linha.n_baixo else ""))
    print(f"  ganho medio     : {_fmt_brl(linha.ganho_medio_brl)}")
    print(f"  perda media     : {_fmt_brl(linha.perda_media_brl)}")
    print(f"  payoff realizado: {linha.payoff_realizado:.2f}" if linha.payoff_realizado is not None else "  payoff realizado: --")
    print(f"  breakeven empir.: {_fmt_pct(linha.breakeven_empirico)}")
    print(f"  resultado total : {_fmt_brl(linha.resultado_total_brl)}")
    if linha.n_com_estimativa > 0:
        print(f"  estimado (Kelly, n={linha.n_com_estimativa}): prob_acerto media {_fmt_pct(linha.prob_acerto_estimada_media)}, payoff medio {linha.payoff_estimado_medio:.2f}")
    if linha.edge_indeterminada:
        print("  veredito: INDETERMINADO -- falta dado (sem derrota registrada ou n=0). Nao trate como edge confirmada nem refutada.")
    elif linha.n_baixo:
        print("  veredito: NAO DECIDE -- n abaixo do minimo para o IC ser confiavel. Mais teses fechadas antes de confiar neste numero.")
    elif linha.edge_confirmada:
        print("  veredito: IC95 do win% fica ACIMA do breakeven empirico -- edge confirmada nesta amostra.")
    else:
        print("  veredito: IC95 do win% NAO fica acima do breakeven -- nao ha edge confirmada nesta amostra (pode estar no zero a zero, ou pior).")


def main() -> None:
    store = SocialArbitrageStore()
    teses = store.listar()
    linhas = calibrar(teses)
    if not linhas:
        print("nenhuma tese fechada ainda -- nada para calibrar.")
        return
    for linha in linhas:
        _imprimir_linha(linha)


if __name__ == "__main__":
    main()
