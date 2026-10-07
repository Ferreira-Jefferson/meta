"""CLI da arbitragem social -- registra e move a tese pelas fases do metodo
Camilo (ver `social_arbitrage/__init__.py`). Nao manda ordem nenhuma: `abrir`
e `fechar` so' REGISTRAM o que o dono ja fez pelo canal que ele usa (MT5/home
broker).

Exemplos:
    python scripts/social_arbitrage_cli.py detectar --marca Havaianas \\
        --fonte "video viral TikTok" \\
        --descricao "esgotado em 3 lojas do bairro X" \\
        --saida "quando a imprensa financeira citar o produto" \\
        --tamanho-pct 0.10
    python scripts/social_arbitrage_cli.py marcas --marca Havaianas
    python scripts/social_arbitrage_cli.py evidencia --id 1 --texto "..." --fonte "ligacao loja Y"
    python scripts/social_arbitrage_cli.py verificar --id 1
    python scripts/social_arbitrage_cli.py aprovar --id 1
    python scripts/social_arbitrage_cli.py rejeitar --id 1 --motivo "..."
    python scripts/social_arbitrage_cli.py abrir --id 1 --preco 4.20 --qtd 1000
    python scripts/social_arbitrage_cli.py fechar --id 1 --preco 6.30
    python scripts/social_arbitrage_cli.py listar
    python scripts/social_arbitrage_cli.py ficha --id 1
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_arbitrage.brand_map import buscar_por_marca  # noqa: E402
from social_arbitrage.thesis import Evidencia, Fase, Lente, Thesis  # noqa: E402
from social_arbitrage.sizing import kelly_fraction, tamanho_meio_kelly  # noqa: E402
from social_arbitrage.store import SocialArbitrageStore  # noqa: E402


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _imprimir_ficha(tese: Thesis) -> None:
    print(f"#{tese.id} [{tese.fase.value}] {tese.marca} ({tese.ticker})")
    print(f"  detectado em : {tese.criado_em.isoformat()} via {tese.fonte_deteccao!r}")
    print(f"  descricao    : {tese.descricao}")
    print(f"  criterio saida: {tese.criterio_saida}")
    print(f"  tamanho alvo : {tese.tamanho_alvo_pct:.1%} do capital")
    if tese.evidencias:
        print(f"  evidencias ({len(tese.evidencias)}):")
        for ev in tese.evidencias:
            print(f"    - [{ev.registrado_em.isoformat()}] ({ev.fonte}) {ev.texto}")
    if tese.motivo_rejeicao:
        print(f"  motivo rejeicao: {tese.motivo_rejeicao}")
    if tese.preco_entrada is not None:
        print(f"  entrada: {tese.quantidade:g} a R${tese.preco_entrada:.2f}")
    if tese.preco_saida is not None:
        print(f"  saida  : R${tese.preco_saida:.2f} -> resultado R${tese.resultado_brl:,.2f}")


def _resolver_tamanho_pct(args: argparse.Namespace) -> float:
    """`--tamanho-pct` direto, OU `--prob-acerto`+`--payoff` via meio-Kelly.
    Nunca os dois ausentes, nunca os dois presentes -- `main()` ja garante
    isso no grupo mutuamente exclusivo do argparse, mas o calculo do Kelly
    mora aqui para o comando `kelly` (so' calcular, sem cadastrar) reusar."""
    if args.tamanho_pct is not None:
        return args.tamanho_pct
    if args.payoff is None:
        print("--prob-acerto exige --payoff junto (razao ganho/perda esperada).", file=sys.stderr)
        raise SystemExit(1)
    tamanho = tamanho_meio_kelly(
        args.prob_acerto, args.payoff,
        fracao_kelly=args.fracao_kelly, teto_pct=args.teto_pct,
    )
    if tamanho <= 0.0:
        print(
            f"Kelly com prob_acerto={args.prob_acerto:.2%} e payoff={args.payoff:.2f} "
            f"nao indica edge positiva (fracao <= 0) -- nao cadastre esta tese.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"tamanho por meio-Kelly: {tamanho:.2%} do capital (fracao_kelly={args.fracao_kelly}, teto={args.teto_pct:.0%}).")
    return tamanho


def cmd_detectar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    vinculos = buscar_por_marca(args.marca)
    if args.ticker is None:
        if not vinculos:
            print(
                f"AVISO: {args.marca!r} nao esta no catalogo "
                f"(social_arbitrage/brand_map.py) e nenhum --ticker foi passado. "
                f"Cadastre a marca no catalogo ou informe --ticker explicitamente.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if len(vinculos) > 1:
            tickers = ", ".join(f"{v.ticker} ({v.empresa})" for v in vinculos)
            print(f"AVISO: {args.marca!r} mapeia para mais de um ticker: {tickers}. Use --ticker para desambiguar.", file=sys.stderr)
            raise SystemExit(1)
        ticker = vinculos[0].ticker
    else:
        ticker = args.ticker
    tamanho_pct = _resolver_tamanho_pct(args)
    usou_kelly = args.tamanho_pct is None
    tese = store.criar_tese(
        marca=args.marca,
        ticker=ticker,
        lente=Lente(args.lente),
        fonte_deteccao=args.fonte,
        descricao=args.descricao,
        criterio_saida=args.saida,
        prob_acerto_estimada=args.prob_acerto if usou_kelly else None,
        payoff_estimado=args.payoff if usou_kelly else None,
        tamanho_alvo_pct=tamanho_pct,
        quando=_agora(),
    )
    print(f"tese #{tese.id} criada em DETECTADA ({tese.marca} -> {tese.ticker}, lente={tese.lente.value}).")


def cmd_kelly(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    cru = kelly_fraction(args.prob_acerto, args.payoff)
    tamanho = tamanho_meio_kelly(
        args.prob_acerto, args.payoff,
        fracao_kelly=args.fracao_kelly, teto_pct=args.teto_pct,
    )
    print(f"kelly cru: {cru:.2%}")
    print(f"meio-kelly (fracao={args.fracao_kelly}, teto={args.teto_pct:.0%}): {tamanho:.2%} do capital")


def cmd_marcas(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    vinculos = buscar_por_marca(args.marca)
    if not vinculos:
        print(f"{args.marca!r} nao esta no catalogo.")
        return
    for v in vinculos:
        print(f"{v.marca} -> {v.ticker} ({v.empresa}) [{v.fonte_confianca.value}] {v.categoria}" + (f" -- {v.observacao}" if v.observacao else ""))


def cmd_evidencia(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    store.adicionar_evidencia(args.id, Evidencia(texto=args.texto, fonte=args.fonte, registrado_em=_agora()))
    print(f"evidencia adicionada a tese #{args.id}.")


def cmd_verificar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    store.transicionar(args.id, Fase.EM_VERIFICACAO, quando=_agora())
    print(f"tese #{args.id} -> EM_VERIFICACAO.")


def cmd_aprovar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    store.transicionar(args.id, Fase.APROVADA, quando=_agora())
    print(f"tese #{args.id} -> APROVADA. Execute a ordem pelo canal de sempre e registre com `abrir`.")


def cmd_rejeitar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    store.transicionar(args.id, Fase.REJEITADA, quando=_agora(), motivo_rejeicao=args.motivo)
    print(f"tese #{args.id} -> REJEITADA ({args.motivo}).")


def cmd_abrir(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    store.registrar_abertura(args.id, preco_entrada=args.preco, quantidade=args.qtd, quando=_agora())
    print(f"tese #{args.id} -> ABERTA ({args.qtd:g} a R${args.preco:.2f}).")


def cmd_fechar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    tese = store.registrar_fechamento(args.id, preco_saida=args.preco, quando=_agora())
    print(f"tese #{args.id} -> FECHADA. resultado R${tese.resultado_brl:,.2f}.")


def cmd_listar(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    fase = Fase(args.fase) if args.fase else None
    teses = store.listar(fase)
    if not teses:
        print("nenhuma tese encontrada.")
        return
    for t in teses:
        print(f"#{t.id} [{t.fase.value}] {t.marca} ({t.ticker}) -- {t.descricao[:60]}")


def cmd_ficha(store: SocialArbitrageStore, args: argparse.Namespace) -> None:
    _imprimir_ficha(store.obter(args.id))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    sp = sub.add_parser("detectar", help="registra uma tese nova em DETECTADA")
    sp.add_argument("--marca", required=True)
    sp.add_argument("--ticker", default=None, help="ignora o catalogo e usa este ticker direto")
    sp.add_argument("--lente", required=True, choices=[l.value for l in Lente],
                     help="consumo (Camilo) ou posicionamento (Williams)")
    sp.add_argument("--fonte", required=True, help='ex.: "video viral TikTok", "COT: comercial no percentil 8%% em 3 anos"')
    sp.add_argument("--descricao", required=True, help="o que foi observado")
    sp.add_argument("--saida", required=True, help="o que vai indicar paridade de informacao")
    grupo_tamanho = sp.add_mutually_exclusive_group(required=True)
    grupo_tamanho.add_argument("--tamanho-pct", type=float, default=None, help="fracao do capital, ex.: 0.10 para 10%% -- direto, sem Kelly")
    grupo_tamanho.add_argument("--prob-acerto", type=float, default=None, help="probabilidade estimada de acerto (0-1) -- calcula tamanho via meio-Kelly, use com --payoff")
    sp.add_argument("--payoff", type=float, default=None, help="razao ganho/perda esperada -- obrigatorio junto de --prob-acerto")
    sp.add_argument("--fracao-kelly", type=float, default=0.5, help="fracao do Kelly cru a usar (default 0.5 = meio-Kelly)")
    sp.add_argument("--teto-pct", type=float, default=0.40, help="teto de capital por tese (default 0.40, o mesmo teto que Camilo pratica)")
    sp.set_defaults(func=cmd_detectar)

    sp = sub.add_parser("kelly", help="so' calcula o tamanho por meio-Kelly, sem cadastrar tese")
    sp.add_argument("--prob-acerto", type=float, required=True)
    sp.add_argument("--payoff", type=float, required=True)
    sp.add_argument("--fracao-kelly", type=float, default=0.5)
    sp.add_argument("--teto-pct", type=float, default=0.40)
    sp.set_defaults(func=cmd_kelly)

    sp = sub.add_parser("marcas", help="consulta o catalogo marca->ticker")
    sp.add_argument("--marca", required=True)
    sp.set_defaults(func=cmd_marcas)

    sp = sub.add_parser("evidencia", help="acumula evidencia numa tese em DETECTADA/EM_VERIFICACAO")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--texto", required=True)
    sp.add_argument("--fonte", required=True)
    sp.set_defaults(func=cmd_evidencia)

    sp = sub.add_parser("verificar", help="DETECTADA -> EM_VERIFICACAO")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmd_verificar)

    sp = sub.add_parser("aprovar", help="EM_VERIFICACAO -> APROVADA")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmd_aprovar)

    sp = sub.add_parser("rejeitar", help="-> REJEITADA")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--motivo", required=True)
    sp.set_defaults(func=cmd_rejeitar)

    sp = sub.add_parser("abrir", help="registra abertura de posicao ja executada -> ABERTA")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--preco", type=float, required=True)
    sp.add_argument("--qtd", type=float, required=True)
    sp.set_defaults(func=cmd_abrir)

    sp = sub.add_parser("fechar", help="registra fechamento de posicao ja executado -> FECHADA")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--preco", type=float, required=True)
    sp.set_defaults(func=cmd_fechar)

    sp = sub.add_parser("listar", help="lista teses, opcionalmente por fase")
    sp.add_argument("--fase", default=None, choices=[f.value for f in Fase])
    sp.set_defaults(func=cmd_listar)

    sp = sub.add_parser("ficha", help="mostra a ficha completa de uma tese")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmd_ficha)

    args = p.parse_args()
    store = SocialArbitrageStore()
    args.func(store, args)


if __name__ == "__main__":
    main()
