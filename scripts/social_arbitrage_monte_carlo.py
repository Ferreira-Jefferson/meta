"""Monte Carlo do dimensionamento (Kelly fracionario) -- ver a docstring de
`social_arbitrage/simulacao.py` para o que isto TESTA e o que NAO testa
(nao e' backtest da deteccao Camilo/Williams: nao existe historico real
disso neste repo).

Uso (defaults comparam Kelly cheio x meio x quarto, com edge bem estimado
E com excesso de confianca, no mesmo edge real):
    python scripts/social_arbitrage_monte_carlo.py
    python scripts/social_arbitrage_monte_carlo.py --prob-acerto-real 0.55 --payoff-real 1.5 --n-teses 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_arbitrage.simulacao import ResultadoMonteCarlo, monte_carlo  # noqa: E402


def _fmt_brl(x: float) -> str:
    return f"R${x:,.2f}"


def _imprimir(rotulo: str, r: ResultadoMonteCarlo) -> None:
    print(f"\n== {rotulo} ==")
    print(f"  fracao_kelly={r.fracao_kelly}  fracao_aposta_usada={r.fracao_aposta_usada:.2%}  n_teses={r.n_teses}  n_trajetorias={r.n_trajetorias}")
    print(f"  capital inicial : {_fmt_brl(r.capital_inicial)}")
    print(f"  mediana final   : {_fmt_brl(r.mediana_final)}")
    print(f"  p5 / p95 final  : {_fmt_brl(r.p5_final)} / {_fmt_brl(r.p95_final)}")
    print(f"  p10 / p90 final : {_fmt_brl(r.p10_final)} / {_fmt_brl(r.p90_final)}")
    print(f"  media final     : {_fmt_brl(r.media_final)}  (puxada pela cauda direita -- leia a mediana, nao a media, como o repo ja documenta em outras tabelas)")
    print(f"  prob. de ruina  : {r.prob_ruina:.1%}  (capital final < {r.limiar_ruina_pct:.0%} do inicial)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prob-acerto-real", type=float, default=0.60, help="probabilidade de acerto REAL usada para sortear cada tese (default 0.60)")
    p.add_argument("--payoff-real", type=float, default=1.2, help="payoff REAL de cada tese (default 1.2)")
    p.add_argument("--prob-acerto-assumida-otimista", type=float, default=None,
                   help="se passado, roda tambem um cenario de EXCESSO DE CONFIANCA: Kelly dimensiona com esta prob (mais otimista que a real), mas o resultado sai da real")
    p.add_argument("--payoff-assumido-otimista", type=float, default=None)
    p.add_argument("--n-teses", type=int, default=50, help="teses por trajetoria (default 50)")
    p.add_argument("--n-trajetorias", type=int, default=5_000, help="trajetorias independentes (default 5000)")
    p.add_argument("--capital-inicial", type=float, default=100_000.0)
    p.add_argument("--limiar-ruina-pct", type=float, default=0.10)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    print(f"edge REAL usado para sortear resultados: prob_acerto={args.prob_acerto_real:.0%}, payoff={args.payoff_real:.2f}")
    print("(lembrete: isto testa a matematica do dimensionamento sob um edge HIPOTETICO -- nao valida se a deteccao Camilo/Williams tem edge de verdade no Brasil.)")

    for fracao_kelly, rotulo in ((1.0, "Kelly CHEIO"), (0.5, "meio-Kelly (recomendado)"), (0.25, "quarto-Kelly")):
        r = monte_carlo(
            n_trajetorias=args.n_trajetorias, n_teses=args.n_teses,
            prob_acerto_real=args.prob_acerto_real, payoff_real=args.payoff_real,
            fracao_kelly=fracao_kelly, capital_inicial=args.capital_inicial,
            limiar_ruina_pct=args.limiar_ruina_pct, seed=args.seed,
        )
        _imprimir(f"{rotulo}, estimativa perfeita (assumida == real)", r)

    if args.prob_acerto_assumida_otimista is not None:
        payoff_otimista = args.payoff_assumido_otimista if args.payoff_assumido_otimista is not None else args.payoff_real
        for fracao_kelly, rotulo in ((1.0, "Kelly CHEIO"), (0.5, "meio-Kelly")):
            r = monte_carlo(
                n_trajetorias=args.n_trajetorias, n_teses=args.n_teses,
                prob_acerto_real=args.prob_acerto_real, payoff_real=args.payoff_real,
                prob_acerto_assumida=args.prob_acerto_assumida_otimista, payoff_assumido=payoff_otimista,
                fracao_kelly=fracao_kelly, capital_inicial=args.capital_inicial,
                limiar_ruina_pct=args.limiar_ruina_pct, seed=args.seed,
            )
            _imprimir(
                f"{rotulo}, EXCESSO DE CONFIANCA (assumida {args.prob_acerto_assumida_otimista:.0%}/{payoff_otimista:.2f} > real {args.prob_acerto_real:.0%}/{args.payoff_real:.2f})",
                r,
            )


if __name__ == "__main__":
    main()
