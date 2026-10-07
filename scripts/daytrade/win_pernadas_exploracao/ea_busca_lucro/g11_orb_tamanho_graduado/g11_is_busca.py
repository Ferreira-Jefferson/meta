# -*- coding: utf-8 -*-
"""Geracao 11 (`WinBuscaLucroG11OrbTamanhoGraduado`) -- BUSCA no IS (jan-jun/2026).

Mandato do COORDENADOR: traduzir "sinal fraco muda o TAMANHO da mao" para um
instrumento que so' cabe 1 contrato a R$250 -- aqui, "tamanho" vira SELECAO:
so' operar o balde de sinal FORTE (ou nao operar, no fraco). A geometria
(stop/alvo) e' herdada LITERALMENTE do vencedor composto da G8
(`stop_max_pontos=140, alvo_multiplo=3x`) -- esta geracao isola o efeito de
UM eixo novo: a forca relativa do rompimento (magnitude alem da faixa /
tamanho da faixa), sem remexer em nada que a G8 ja' tinha fixado.

Protocolo em 3 passos:
  1. DIAGNOSTICO -- roda sem filtro de forca (forca_min=0, forca_max=inf,
     EXATAMENTE a REF/vencedor da G8) sobre o IS inteiro, coleta
     `strat.stats_forcas` (forca de TODA borda bruta, nao so' das emitidas)
     e calcula os cortes de tercil (p33/p67) -- causal, SO' no IS.
  2. BALDES -- roda 3 celulas (fraco/medio/forte) com os cortes do passo 1,
     mais a REF (= passo 1, reaproveitada).
  3. CRITERIO COMPOSTO (mesmo da G8, herdado por precedencia de mesma
     familia/capital/instrumento): liquido>0 E nao censurado E veredito
     win% != NEGATIVO E p_ruina(MC, 44 operacoes projetadas, R$250->R$100)
     <= 25% -- e, ALEM disso (item 2 do mandato desta geracao), o balde
     promovido precisa ter win%/payoff DISTINGUIVEL de ruido frente ao balde
     fraco (teste de duas proporcoes), senao "forte" seria so' um recorte
     arbitrario do mesmo sinal, nao uma graduacao real.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g11_orb_tamanho_graduado/g11_is_busca.py`
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g11_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.25  # herdado da G8 (revisado de 20% -> 25% la', mesma familia/capital)
HORIZONTE_PREGOES = 44  # tamanho do OOS-1 -- mesma pergunta da G8


def _worker(rotulo: str, kwargs_estrategia: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(dias, **kwargs_estrategia)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias),
                                  horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    payoff = (c["ganho_medio"] / c["perda_media"]) if c["perda_media"] > 0 else float("nan")
    be_nom = 1.0 / (1.0 + kwargs_estrategia["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "payoff": b.br(payoff, 2) if payoff == payoff else "--",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "bruto/forca/emit": f"{strat.stats_bruto}/{strat.stats_fora_forca}/{strat.stats_ordens_emitidas}",
        "p_ruina(MC)": (b.br(100 * ruina["p_ruina"], 1) + "%") if ruina["p_ruina"] == ruina["p_ruina"] else "--",
        "pior_seq_perdas": str(const.get("pior_seq_ops", 0)),
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, kwargs=kwargs_estrategia, c=c, top5=top5, linha=linha_res,
        equity_min=equity_min, bruto=strat.stats_bruto, fora_forca=strat.stats_fora_forca,
        ja_operou=strat.stats_ja_operou_hoje, emitidas=strat.stats_ordens_emitidas,
        ruina=ruina, const=const, sizing=sizing, payoff=payoff,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
        forcas=list(strat.stats_forcas),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _bate_composto(r: dict) -> bool:
    c = r["c"]
    liquido_ok = c["liquido"] > 0
    censura_ok = not _censurado(r)
    win_ok = c["veredito"] != "NEGATIVO"
    ruina_ok = r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= LIMIAR_RUINA
    return liquido_ok and censura_ok and win_ok and ruina_ok


def _z_duas_proporcoes(r1: dict, r2: dict) -> float:
    """Teste de duas proporcoes (win% de `r1` contra `r2`) -- `nan` se
    alguma amostra for vazia. Usado so' para a leitura "forte difere de
    fraco de forma distinguivel de ruido?", nao como substituto do IC95 de
    cada balde isoladamente."""
    c1, c2 = r1["c"], r2["c"]
    n1, n2 = c1["n"], c2["n"]
    if n1 == 0 or n2 == 0:
        return float("nan")
    k1 = c1["win"] * n1
    k2 = c2["win"] * n2
    p_pool = (k1 + k2) / (n1 + n2)
    denom = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if denom == 0:
        return float("nan")
    return (c1["win"] - c2["win"]) / denom


def _imprime_linha(rot: str, r: dict) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {rot:<14} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"payoff={b.br(r['payoff'],2) if r['payoff']==r['payoff'] else '--':>5}  "
          f"veredito={c['veredito']:<10}  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"composto={_bate_composto(r)}", flush=True)


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 160)
    print("WinBuscaLucroG11OrbTamanhoGraduado -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 160)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Geometria herdada LITERALMENTE da G8 (stop_max=140, alvo=3x) -- so' o filtro de forca varia.")
    print(f"CRITERIO COMPOSTO (herdado da G8): liquido>0 E nao censurado E win% != NEGATIVO E "
          f"p_ruina(MC, R$250->R$100, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n",
          flush=True)

    # -- PASSO 1: diagnostico (= REF, sem filtro de forca) --------------------
    print("--- PASSO 1: diagnostico (sem filtro de forca = REF = vencedor G8) ---", flush=True)
    ref = _worker("REF (G8)", dict(b.GEOMETRIA_G8, forca_min=0.0, forca_max=float("inf")), dias)
    _imprime_linha("REF (G8)", ref)
    forcas = ref["forcas"]
    print(f"  populacao de forca bruta: n={len(forcas)}  "
          f"min={b.br(min(forcas),3)}  max={b.br(max(forcas),3)}  "
          f"mediana={b.br(sorted(forcas)[len(forcas)//2],3)}")

    q_baixo, q_alto = b.quantis_forca(forcas)
    print(f"  cortes de tercil (causais, so' IS): p33={b.br(q_baixo,3)}  p67={b.br(q_alto,3)}\n", flush=True)

    # -- PASSO 2: baldes -------------------------------------------------------
    variantes = [
        ("fraco", dict(b.GEOMETRIA_G8, forca_min=0.0, forca_max=q_baixo)),
        ("medio", dict(b.GEOMETRIA_G8, forca_min=q_baixo, forca_max=q_alto)),
        ("forte", dict(b.GEOMETRIA_G8, forca_min=q_alto, forca_max=float("inf"))),
    ]
    print("--- PASSO 2: baldes de forca (tercis causais do IS) ---", flush=True)
    resultados: dict[str, dict] = {"REF (G8)": ref}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r)

    # -- tabela consolidada ----------------------------------------------------
    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "payoff", "top3/liq", "top5/liq",
              "bruto/forca/emit", "p_ruina(MC)", "pior_seq_perdas")
    print("\n" + "=" * 160)
    print("TABELA CONSOLIDADA -- REF + 3 baldes de forca")
    print("=" * 160)
    print(tabela([resultados[k]["linha"] for k in ("REF (G8)", "fraco", "medio", "forte")],
                 extras=EXTRAS, largura_extra=11))

    print("\nSTOP MEDIANO (pts) / sizing por balde:")
    for rot in ("REF (G8)", "fraco", "medio", "forte"):
        r = resultados[rot]
        s = r["sizing"]
        print(f"  {rot:<14} stop_mediano={b.br(r['stop_dist_mediana'],0)}  "
              f"equity_min={b.br(r['equity_min'])}  "
              f"contratos_kelly={s.get('contratos_kelly','--')}  "
              f"p_encolhido={b.br(100*s.get('p_encolhido',float('nan')),1)}%")

    # -- comparacao estatistica forte x fraco ----------------------------------
    print("\n--- COMPARACAO forte x fraco (teste de duas proporcoes, win%) ---")
    z = _z_duas_proporcoes(resultados["forte"], resultados["fraco"])
    print(f"z = {b.br(z,2) if z==z else '--'}  "
          f"(|z|>=1,96 => diferenca distinguivel de ruido a 95%)")
    diff_real = (z == z and abs(z) >= 1.96)
    print(f"diferenca forte-vs-fraco distinguivel de ruido? {diff_real}")

    # -- vencedor: so' promove se bater o composto E (se aplicavel) diferir de fraco
    print("\n" + "=" * 160)
    candidatos_compostos = [rot for rot in ("fraco", "medio", "forte")
                            if _bate_composto(resultados[rot])]
    print("Baldes que batem o criterio composto:", candidatos_compostos or "NENHUM")
    print(f"REF (G8, sem filtro) bate o composto? {_bate_composto(ref)}")
    print("=" * 160)

    print("\nFIM PASSO 1+2. Ver g11_is_busca_stdout.log para o relatorio completo.")


if __name__ == "__main__":
    main()
