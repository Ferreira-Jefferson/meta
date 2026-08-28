"""Frente F4-wdo-geometria-sessao, RODADA 2, bloco (A) -- sensibilidade a
pedagio de fila (1 tick por perna maker, 2 pernas) testada na GRADE INTEIRA
(144 celulas: reload 72 + rolling 72), NAO so' no top-15-por-pnl-bruto da
rodada 1 (aquele top ficou dominado por espacamento=1 tick, o que enviesa a
pergunta "geometria LARGA sobrevive a pedagio?" para "nao" antes mesmo de
medir -- ver o pedido explicito do critico da rodada 1, bloco A).

O que muda de `wdo_geo_sweep.py` (rodada 1): aquele testava pedagio SO' nas
15 celulas de maior liquido bruto. Este roda pedagio (0 e 1 tick) em TODA
celula da grade, e reporta a sobrevivencia por FAIXA DE ESPACAMENTO -- a
pergunta concreta e' se um nivel LONGE do preco (espacamento>=4, ate' 32
ticks) tem economia por trade robusta o bastante para um pedagio fixo de
~R$10/round-trip (1 tick * R$5/tick * 2 pernas), diferente do espacamento=1
que a rodada 1 ja mostrou morrer por completo (0/15, todas revertendo para
-R$37k a -R$195k).

Reusa `_bars_is`/`_config_com_pedagio`/`_monta_robo`/`_variante`/`_rodar_celula`/
`_fase_metade`/`_fase_nulo` de `wdo_geo_sweep.py` (mesmo diretorio, so' LE,
nao edita) -- evita reimplementar a mesma infra testada na rodada 1.

Disciplina: IS travado (`_bars_is` ja usa `LockedBars.in_sample()`, nunca
`.unlock()`), custo+slippage sempre no numero principal, pedagio testado
lado a lado (nunca escondido), teste de metade + nulo sign-flip correto no
melhor sobrevivente (se algum sobreviver).

Uso:
    python scripts/daytrade/wdo_geo_pedagio_largo.py --jobs 8
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.report import num_br, tabela  # noqa: E402
import wdo_geo_sweep as base  # noqa: E402  (reusa infra da propria frente F4, so' LE)

EXTRAS = base.EXTRAS


def _grade_completa() -> list[tuple]:
    return base._grade_reload() + base._grade_rolling()


def _roda_com_e_sem_pedagio(unidades: list[tuple], jobs: int) -> dict:
    """Roda cada unidade (mechanic, T, S, spacing, n_levels, reanchor_bars)
    DUAS vezes -- pedagio 0.0 e 1.0 tick -- e devolve
    {chave: (Celula_sem, Celula_com)}."""
    max_workers = jobs or min(len(unidades) * 2, os.cpu_count() or 4)
    print(f"\n[pedagio-largo] {len(unidades)} celula(s) x 2 (sem/com pedagio) = "
          f"{len(unidades)*2} runs em ate {max_workers} processo(s)...", flush=True)
    resultados: dict = {}
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for u in unidades:
            mech, T, S, sp, nl, rb = u
            futures[pool.submit(base._rodar_celula, mech, T, S, sp, nl, rb, 0.0)] = (u, "sem")
            futures[pool.submit(base._rodar_celula, mech, T, S, sp, nl, rb, 1.0)] = (u, "com")
        feitas = 0
        for future in as_completed(futures):
            u, tag = futures[future]
            c = future.result()
            resultados.setdefault(u, {})[tag] = c
            feitas += 1
            if feitas % 40 == 0 or feitas == len(futures):
                print(f"[pedagio-largo] {feitas}/{len(futures)} prontas...", flush=True)
    return resultados


def _bucket_espacamento(sp: int) -> str:
    if sp <= 2:
        return "estreito (1-2 ticks)"
    if sp <= 4:
        return "medio (4 ticks)"
    return "largo (8-32 ticks)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()

    bars = base._bars_is()
    dias = sorted(set(bars.index.date))
    print(f"[wdo_geo_pedagio_largo] WDO@ IS: {len(bars)} barras, {len(dias)} pregoes "
          f"({dias[0]}..{dias[-1]})")

    unidades = _grade_completa()
    resultados = _roda_com_e_sem_pedagio(unidades, args.jobs)

    # --------------------------------------------------- surperficie por espacamento ----
    print(f"\n=== Sobrevivencia a pedagio (1 tick/perna, 2 pernas) por FAIXA DE ESPACAMENTO "
          f"-- TODA a grade, nao so' o top-por-pnl-bruto ===")
    for mechanic in ("rolling", "reload"):
        print(f"\n  -- mecanica={mechanic} --")
        espacamentos = sorted({u[3] for u in unidades if u[0] == mechanic})
        for sp in espacamentos:
            celulas_sp = [(u, r) for u, r in resultados.items() if u[0] == mechanic and u[3] == sp]
            sem = [r["sem"].linha.liquido_brl for u, r in celulas_sp]
            com = [r["com"].linha.liquido_brl for u, r in celulas_sp]
            positivos_sem = sum(1 for v in sem if v > 0)
            positivos_com = sum(1 for v in com if v > 0)
            print(f"    espacamento={sp:>3} ticks  n={len(sem):3d}  "
                  f"mediana_sem={num_br(statistics.median(sem),2):>12}  "
                  f"mediana_com={num_br(statistics.median(com),2):>12}  "
                  f"positivas_sem={positivos_sem}/{len(sem)}  positivas_com={positivos_com}/{len(com)}")

    # --------------------------------------------------- destaque nos candidatos citados ----
    print(f"\n=== Destaque -- candidatas citadas pelo critico da rodada 1 "
          f"(T4, espacamento largo, ~R$15-22k zero-atrito no spot-check) ===")
    citados = [("rolling", 4, 16, 4, 1, 1), ("rolling", 4, 8, 4, 1, 1), ("rolling", 4, 32, 4, 1, 1)]
    for u in citados:
        if u in resultados:
            r = resultados[u]
            sobrevive = "SOBREVIVE" if r["com"].linha.liquido_brl > 0 else "morre"
            print(f"  {r['sem'].linha.variante:<26} sem_pedagio={num_br(r['sem'].linha.liquido_brl,2):>12}  "
                  f"com_pedagio={num_br(r['com'].linha.liquido_brl,2):>12}   [{sobrevive}]")
        else:
            print(f"  {u}: nao esta na grade padrao (fora do range testado)")

    # --------------------------------------------------- todos os sobreviventes ----
    sobreviventes = sorted(
        [r["com"] for r in resultados.values() if r["com"].linha.liquido_brl > 0],
        key=lambda c: c.linha.liquido_brl, reverse=True,
    )
    print(f"\n=== TODOS os sobreviventes com pedagio (liquido com_pedagio > 0), "
          f"de {len(resultados)} celulas testadas ===")
    if sobreviventes:
        print(tabela([c.linha for c in sobreviventes[:30]], extras=EXTRAS, largura_extra=9))
    else:
        print("  NENHUMA celula da grade completa sobrevive a 1 tick de pedagio de fila -- "
              "nem no top-15-por-pnl-bruto (rodada 1) nem em espacamento largo (esta rodada).")

    # --------------------------------------------------- top 15 sem pedagio, p/ contexto ----
    top_sem = sorted([r["sem"] for r in resultados.values()], key=lambda c: c.linha.liquido_brl,
                      reverse=True)[:15]
    print(f"\n=== Top 15 SEM pedagio (contexto -- mesmo baseline da rodada 1) ===")
    print(tabela([c.linha for c in top_sem], extras=EXTRAS, largura_extra=9))

    if sobreviventes:
        campea = sobreviventes[0]
        key = (campea.mechanic, campea.T, campea.S, campea.spacing, campea.n_levels, campea.reanchor_bars)
        campea_sem_pedagio = resultados[key]["sem"]
        print(f"\n[wdo_geo_pedagio_largo] candidata FINAL do bloco A: "
              f"{campea.linha.variante} (com_pedagio={num_br(campea.linha.liquido_brl,2)}, "
              f"sem_pedagio={num_br(campea_sem_pedagio.linha.liquido_brl,2)})")
        # Teste de metade roda a ZERO pedagio (mesma convencao da rodada 1:
        # `_fase_metade` mede a robustez da GEOMETRIA, pedagio e' um corte
        # ortogonal separado) -- top-15 por liquido sem_pedagio, garantindo
        # que a candidata final do bloco A esteja sempre incluida.
        top_por_pnl_bruto = sorted((r["sem"] for r in resultados.values()),
                                    key=lambda c: c.linha.liquido_brl, reverse=True)[:14]
        top_para_metade = [campea_sem_pedagio] + [
            c for c in top_por_pnl_bruto
            if (c.mechanic, c.T, c.S, c.spacing, c.n_levels, c.reanchor_bars) != key
        ]
        base._fase_metade(top_para_metade, args.jobs)
        base._fase_nulo(campea.mechanic, campea.T, campea.S, campea.spacing,
                         campea.n_levels, campea.reanchor_bars)
    else:
        print(f"\n[wdo_geo_pedagio_largo] NENHUM sobrevivente -- sem teste de metade/nulo "
              f"(nao ha' candidata para testar). Ver o angulo alternativo (entrada a mercado) "
              f"no proximo script desta rodada.")


if __name__ == "__main__":
    main()
