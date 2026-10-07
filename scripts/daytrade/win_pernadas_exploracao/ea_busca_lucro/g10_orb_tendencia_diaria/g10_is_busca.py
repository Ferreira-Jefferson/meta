# -*- coding: utf-8 -*-
"""Geracao 10 (`WinBuscaLucroG10OrbTendenciaDiaria`) -- BUSCA no IS (jan-jun/2026).

Pergunta: a geometria vencedora da G8 (stop_max=140, alvo=3x, range=5min --
liquido+R$1.365,50 IS, mas p_ruina(MC)=24,8% e MORREU no OOS-1 com 5
derrotas seguidas) fica melhor -- win% maior e/ou p_ruina menor -- quando so'
opera NA DIREcao da tendencia DIARIA do WIN@? Geometria FIXA (herdada da G8,
`g10_base.GEOMETRIA_G8_VENCEDORA`) -- o eixo desta geracao e' SO' a definicao
do filtro de tendencia:

  REF        -- G8 sem filtro (recalculada aqui, mesma janela)
  MA10 nivel -- fechamento[D-1] acima/abaixo da media de 10 dias
  MA20 nivel -- fechamento[D-1] acima/abaixo da media de 20 dias
  MA50 nivel -- fechamento[D-1] acima/abaixo da media de 50 dias
  MA20 incl. -- media de 20 dias subindo/descendo nos ultimos 5 dias

Mesmo criterio COMPOSTO da G8 (liquido>0 E nao censurado E win%!=NEGATIVO E
p_ruina(MC, horizonte=44 pregoes, R$250->R$100)<=LIMIAR_RUINA) -- LIMIAR
comeca em 20% (mesmo ponto de partida declarado da G8); se nenhuma variante
bater e a vizinhanca não for degenerada, o mesmo precedente da G8 (revisar
para 25% ANTES de ver o OOS, com a razao escrita) pode ser aplicado aqui,
nunca depois de ja' ter visto qualquer numero do OOS-1.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g10_orb_tendencia_diaria/g10_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g10_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.20
HORIZONTE_PREGOES = 44  # tamanho do OOS-1 -- mesma convencao da G8


def _worker_referencia(rotulo: str, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda_referencia_sem_filtro(dias)
    return _empacota(rotulo, res, strat, dias, bruto=strat.stats_bruto,
                      bruto_favoravel=strat.stats_bruto, bloqueado=0)


def _worker_filtro(rotulo: str, direcao_kwargs: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

    res, strat = b.roda(dias, direcao_kwargs, **b.GEOMETRIA_G8_VENCEDORA)
    return _empacota(rotulo, res, strat, dias, bruto=strat.stats_bruto,
                      bruto_favoravel=strat.stats_bruto_favoravel,
                      bloqueado=strat.stats_bloqueado_tendencia)


def _empacota(rotulo: str, res, strat, dias: list, bruto: int,
              bruto_favoravel: int, bloqueado: int) -> dict:
    from backtest.intraday.report import linha_de_resultado

    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias),
                                  horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    be_nom = 1.0 / (1.0 + b.GEOMETRIA_G8_VENCEDORA["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto/favor/emit": f"{bruto}/{bruto_favoravel}/{strat.stats_ordens_emitidas}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
        "p_ruina(MC)": (b.br(100 * ruina["p_ruina"], 1) + "%") if ruina["p_ruina"] == ruina["p_ruina"] else "--",
        "pior_seq_perdas": str(const.get("pior_seq_ops", 0)),
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, c=c, top5=top5, linha=linha_res, equity_min=equity_min,
        bruto=bruto, bruto_favoravel=bruto_favoravel, bloqueado=bloqueado,
        emitidas=strat.stats_ordens_emitidas, ja_operou=strat.stats_ja_operou_hoje,
        ruina=ruina, const=const, sizing=sizing,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _bate_composto(r: dict, limiar: float) -> bool:
    c = r["c"]
    liquido_ok = c["liquido"] > 0
    censura_ok = not _censurado(r)
    win_ok = c["veredito"] != "NEGATIVO"
    ruina_ok = r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= limiar
    return liquido_ok and censura_ok and win_ok and ruina_ok


def _imprime_linha(rot: str, r: dict, limiar: float) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {rot:<20} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"bruto/favor/emit={r['bruto']}/{r['bruto_favoravel']}/{r['emitidas']}  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
          f"composto={_bate_composto(r, limiar)}", flush=True)


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 170)
    print("WinBuscaLucroG10OrbTendenciaDiaria -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 170)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Geometria FIXA herdada do vencedor composto da G8:", b.GEOMETRIA_G8_VENCEDORA)
    print(f"CRITERIO COMPOSTO: liquido>0 E nao censurado E win% != NEGATIVO E "
          f"p_ruina(MC, R$250->R$100, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n",
          flush=True)

    variantes_filtro = [
        ("MA10 nivel", dict(modo="nivel", n=10)),
        ("MA20 nivel", dict(modo="nivel", n=20)),
        ("MA50 nivel", dict(modo="nivel", n=50)),
        ("MA20 inclin.5d", dict(modo="inclinacao", n=20, janela_inclinacao=5)),
    ]

    resultados: dict[str, dict] = {}
    print("--- rodando REF (sem filtro) + 4 definicoes de tendencia, 4 workers ---", flush=True)
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker_referencia, "REF sem filtro", dias): "REF sem filtro"}
        for rot, kw in variantes_filtro:
            futs[ex.submit(_worker_filtro, rot, kw, dias)] = rot
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r, LIMIAR_RUINA)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "bruto/favor/emit",
              "top3/liq", "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas")
    ordem = ["REF sem filtro"] + [r for r, _ in variantes_filtro]
    print("\n" + "=" * 170)
    print("TABELA CONSOLIDADA -- REF + 4 definicoes de tendencia diaria")
    print("=" * 170)
    print(tabela([resultados[r]["linha"] for r in ordem], extras=EXTRAS, largura_extra=13))

    print("\nREDUCAO DE AMOSTRA PELO FILTRO (bruto -> favoravel -> emitidas) + concentracao:")
    for rot in ordem:
        r = resultados[rot]
        frac = (r["bruto_favoravel"] / r["bruto"]) if r["bruto"] else float("nan")
        print(f"  {rot:<20} bruto={r['bruto']:>4}  favoravel_tendencia={r['bruto_favoravel']:>4} "
              f"({b.br(100*frac,1) if frac==frac else '--'}%)  bloqueado_tendencia={r['bloqueado']:>4}  "
              f"emitidas={r['emitidas']:>4}  pregoes_distintos_c_trade={r['c']['com_trade']}  "
              f"top3/liq={b.br(100*r['c']['concentracao_top3'],0) if r['c']['concentracao_top3']==r['c']['concentracao_top3'] else '--'}%  "
              f"top5/liq={b.br(100*r['top5'],0) if r['top5']==r['top5'] else '--'}%")

    print("\nSTOP MEDIANO (pts) por variante (item 6.47 -- flag se < 100):")
    for rot in ordem:
        r = resultados[rot]
        flag = " <<< FLAG 6.47 (precisa checagem com ticks)" if r["stop_dist_mediana"] == r["stop_dist_mediana"] and r["stop_dist_mediana"] < 100 else ""
        print(f"  {rot:<20} stop_mediano={b.br(r['stop_dist_mediana'],0)}  equity_min={b.br(r['equity_min'])}  "
              f"ruina_formula(Lundberg)={b.br(100*r['ruina']['ruina_formula'],1) if r['ruina']['ruina_formula']==r['ruina']['ruina_formula'] else '--'}%  "
              f"n_ops_simulados={r['ruina']['n_ops']}{flag}")

    print("\nSIZING (motor.tamanho/p_encolhido) -- Kelly fracionario a R$250:")
    for rot in ordem:
        s = resultados[rot]["sizing"]
        print(f"  {rot:<20} p_encolhido={b.br(100*s.get('p_encolhido',float('nan')),1)}%  "
              f"contratos_kelly={s.get('contratos_kelly','--')}")

    candidatos_filtro = {r: resultados[r] for r in ordem if r != "REF sem filtro"}
    bate_algum = {r: v for r, v in candidatos_filtro.items() if _bate_composto(v, LIMIAR_RUINA)}
    print("\n" + "=" * 170)
    if bate_algum:
        venc = min(bate_algum.values(), key=lambda r: (r["ruina"]["p_ruina"], -r["c"]["liquido"]))
        print(f"VENCEDOR (bate composto @ {LIMIAR_RUINA*100:.0f}%):", venc["rotulo"])
    else:
        nao_censurados = {r: v for r, v in candidatos_filtro.items() if not _censurado(v)}
        if nao_censurados:
            venc = min(nao_censurados.values(), key=lambda r: (r["ruina"]["p_ruina"], -r["c"]["liquido"]))
            print(f"NENHUM filtro bate o composto @ {LIMIAR_RUINA*100:.0f}% -- melhor NAO-CENSURADO:", venc["rotulo"])
        else:
            venc = max(candidatos_filtro.values(), key=lambda r: r["c"]["liquido"])
            print("TODAS as variantes de filtro censuraram -- resultado degenerado, melhor liquido mesmo assim:", venc["rotulo"])
    print("=" * 170)
    print("\nFIM.")


if __name__ == "__main__":
    main()
