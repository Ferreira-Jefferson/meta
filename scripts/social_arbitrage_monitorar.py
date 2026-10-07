"""Varredura de deteccao automatica (Reddit + Google Trends) contra o
catalogo de marcas de `social_arbitrage/brand_map.py`.

So' INFORMA -- nunca cria tese sozinho. `tamanho_alvo_pct` e `criterio_saida`
sao decisao humana obrigatoria em `Thesis` (sem default, de proposito, ver
`thesis.py`), e um script de varredura automatica preenchendo isso sozinho
reintroduziria exatamente o "parametro de risco com default silencioso" que
`AGENTS.md` proibe. Quando acha algo, imprime o comando `detectar` PRONTO
para o dono rodar (ou ajustar) se decidir que vale a pena.

Nenhuma das duas fontes precisa de credencial (Reddit via RSS publico,
Trends via `pytrends`) -- mas as duas sao caminhos NAO-OFICIAIS/nao
autenticados, mais lentos e mais sujeitos a bloqueio de taxa que uma API
oficial. Por isso ha pausa entre CADA chamada, nao so' entre marcas (ver
`social_arbitrage/deteccao_reddit.py`: 2 chamadas seguidas sem pausa ja
levaram a 429 num teste ao vivo em 2026-09-27).

Uso:
    python scripts/social_arbitrage_monitorar.py
    python scripts/social_arbitrage_monitorar.py --marcas Havaianas Natura
    python scripts/social_arbitrage_monitorar.py --subreddits investimentos farialimabets --sem-trends
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests  # noqa: E402

from social_arbitrage.brand_map import CATALOGO_BRASIL  # noqa: E402
from social_arbitrage.deteccao_reddit import buscar_mencoes  # noqa: E402
from social_arbitrage.deteccao_trends import consultar_interesse  # noqa: E402

_SUBREDDITS_DEFAULT = ("investimentos", "farialimabets")


def _comando_detectar_sugerido(marca: str, ticker: str, fonte: str, descricao: str) -> str:
    return (
        f'python scripts/social_arbitrage_cli.py detectar --marca "{marca}" --ticker {ticker} '
        f'--lente consumo --fonte "{fonte}" --descricao "{descricao}" '
        f'--saida "quando a imprensa financeira citar" --tamanho-pct 0.10'
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--marcas", nargs="*", default=None, help="marcas a checar (default: todo o catalogo)")
    p.add_argument("--subreddits", nargs="*", default=list(_SUBREDDITS_DEFAULT))
    p.add_argument("--sem-reddit", action="store_true")
    p.add_argument("--sem-trends", action="store_true")
    p.add_argument("--pausa-segundos", type=float, default=3.0, help="pausa entre CADA chamada de rede (Reddit e Trends -- os dois sao caminhos nao-oficiais sensiveis a rate limit)")
    args = p.parse_args()

    entradas = (
        [(m.marca, m.ticker) for m in CATALOGO_BRASIL if m.marca in args.marcas]
        if args.marcas else
        [(m.marca, m.ticker) for m in CATALOGO_BRASIL]
    )
    if not entradas:
        print("nenhuma marca do catalogo bate com --marcas informado.", file=sys.stderr)
        raise SystemExit(1)

    achados = 0

    if not args.sem_reddit:
        for i, (marca, ticker) in enumerate(entradas):
            if i > 0:
                time.sleep(args.pausa_segundos)
            try:
                mencoes = buscar_mencoes(marca, tuple(args.subreddits), pausa_segundos=args.pausa_segundos)
            except requests.exceptions.RequestException as exc:
                # RSS publico e' sensivel a rate limit (429 medido ao vivo) --
                # uma marca falhando nao pode derrubar a varredura inteira das
                # outras 39+, mesmo espirito de "resultado sai assim que fica
                # pronto" (AGENTS.md).
                print(f"[REDDIT] {marca}: {exc}", file=sys.stderr)
                continue
            for m in mencoes:
                achados += 1
                print(f"\n[REDDIT] r/{m.subreddit} ({m.criado_em.date()}): {m.titulo}\n  {m.url}")
                print("  ->", _comando_detectar_sugerido(marca, ticker, f"reddit r/{m.subreddit}", m.titulo[:80]))

    if not args.sem_trends:
        for marca, ticker in entradas:
            try:
                sinal = consultar_interesse(marca)
            except RuntimeError as exc:
                print(f"[TRENDS] {marca}: {exc}", file=sys.stderr)
                time.sleep(args.pausa_segundos)
                continue
            if sinal.em_pico:
                achados += 1
                print(f"\n[TRENDS] {marca}: interesse atual {sinal.interesse_atual} vs media {sinal.media_movel_recente:.1f} (razao {sinal.razao_pico:.1f}x)")
                print("  ->", _comando_detectar_sugerido(marca, ticker, "Google Trends", f"pico de interesse {sinal.razao_pico:.1f}x a media"))
            time.sleep(args.pausa_segundos)

    print(f"\n{achados} achado(s) no total. Nenhuma tese foi criada -- os comandos acima sao SUGESTOES.")


if __name__ == "__main__":
    main()
