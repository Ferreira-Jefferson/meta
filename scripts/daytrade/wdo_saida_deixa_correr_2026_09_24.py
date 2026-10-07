"""WDO@ M1: correcao do dono sobre o desenho de saida dinamica dos dois
scripts anteriores (`wdo_cor_minuto_saida_dinamica_2026_09_24.py`,
`wdo_oscilacao_lado_saida_dinamica_2026_09_24.py`). O desenho k/fixo/
trailing media la fechava no PRIMEIRO lucro (`fixo`) ou punha o stop a
~breakeven-custo assim que ativava (`trailing`, ativa em k=2, ancora 2 ticks
atras) -- as duas formas cortavam qualquer recuo normal antes de deixar o
preco correr, e por isso o win% daquelas rodadas saia 0-20%: nao e' que o
sinal fosse ruim, e' que a saida nunca dava chance de vencer por mais do que
o minimo.

## Regra de saida nova ("deixa correr", ver `_saida_dinamica_tick_sim.
resolver_saida_deixa_correr`)

1. Stop INICIAL de sempre: `max(2 ticks, round(1,5 x mediana21))`, a
   mercado, 1 tick de deslize.
2. ATIVA quando a excursao favoravel bate 2 ticks: o stop pula para um PISO
   fixo (entrada +/- 1 tick -- a mercado com deslize da' ~breakeven liquido,
   so' perde a corretagem) e NUNCA MAIS RECUA.
3. Dali em diante o stop e' `max(piso, extremo -/+ trail)`, `trail` em
   {1,0x, 2,0x} da mediana21 CONGELADA na entrada (arredondado, minimo 2
   ticks) -- ratchet monotonico, so' aperta. Sai a mercado no primeiro
   toque, 1 tick de deslize. Achata no fim do pregao (18:25 BRT) a mercado.

## Sinais -- MESMA janela IS de 18 pregoes dos dois scripts anteriores (ver
`_saida_dinamica_tick_sim.py` para a reconstrucao da janela e as suposicoes
de dado)

  * `seguir3`: >=3 M1 verdes seguidas -> compra, >=3 vermelhas -> vende
    (identico a `wdo_cor_minuto_saida_dinamica_2026_09_24.py`).
  * `lado_vencedor` + filtro ligado: olha as ultimas 21 barras, conta
    vitorias HIPOTETICAS por lado (`_saida_dinamica_tick_sim.
    resolver_hipoteticos_dia_deixa_correr` -- MESMA regra de saida "deixa
    correr" do trail_mult da celula, "vitoria" = P&L LIQUIDO positivo, nao
    so' ticks brutos capturados), so' entra com media10 de range >= 4 ticks
    (identico a `wdo_oscilacao_lado_saida_dinamica_2026_09_24.py`, filtro
    ligado fixo -- coordenador nao pediu grade de filtro aqui).
  * `cego`: CONTROLE as cegas (lado alternado). Suposicao explicita (regra 1
    de disciplina-de-codigo): como so ha' UM `cego` na grade mas DOIS sinais
    para comparar contra ele, a linha da grade espelha os instantes de
    `lado_vencedor` (o sinal novo desta rodada); a diferenca `seguir3-cego`
    usa um SEGUNDO cego, interno (mesma logica, espelhando os instantes de
    `seguir3`), calculado so' para aquela comparacao -- para as duas
    diferencas serem pareadas nos MESMOS instantes do sinal que estao
    testando, em vez de comparar contagens de trade diferentes.

## Grade -- 6 celulas (`sinal x trail_mult`), CADA UMA com as DUAS entradas
pedidas (teto a mercado + entrada-limite, fila calibrada de `fidelidade.py`,
TTL 5min) = 12 rodadas.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _saida_dinamica_tick_sim as sim  # noqa: E402

FILTRO_MIN_TICKS = sim.DEIXA_CORRER_ATIVACAO_TICKS + 2.0  # 4 ticks -- mesma formula do script de oscilacao
VOL_FILTRO_LOOKBACK = 10
TRAIL_MULTS = (1.0, 2.0)

EXTRAS = ("R$/op", "IC95 R$/op", "win%", "breakeven%", "ativou%", "ganho tk med", "ganho tk p50",
          "ganho tk p90", "MFE tk med", "capt tk med", "hold min", "%inicial", "%piso", "%trail",
          "%flat", "fill%", "atraso min", "preg s/trade")


def _prep_m1(m1_dia: pd.DataFrame) -> pd.DataFrame:
    m1_dia = m1_dia.copy()
    m1_dia["media10_ticks"] = m1_dia["range_ticks"].rolling(VOL_FILTRO_LOOKBACK).mean()
    return m1_dia


def _elegivel_filtro(m1_dia: pd.DataFrame) -> pd.Series:
    return m1_dia["median21_ticks"].notna() & (m1_dia["media10_ticks"] >= FILTRO_MIN_TICKS)


def _sinal_seguir3(m1_dia: pd.DataFrame) -> pd.Series:
    lado = pd.Series(None, index=m1_dia.index, dtype=object)
    cond_long = (m1_dia["streak_cor"] == "verde") & (m1_dia["streak_len"] >= 3)
    cond_short = (m1_dia["streak_cor"] == "vermelho") & (m1_dia["streak_len"] >= 3)
    lado[cond_long] = "long"
    lado[cond_short] = "short"
    return lado


def _sinal_cego_espelha(sinal_base_por_dia: dict) -> dict:
    """Mesmos instantes de `sinal_base_por_dia` (concatenados em ordem
    cronologica entre pregoes), lado alternado -- as cegas."""
    marcados = []
    for dia, serie in sinal_base_por_dia.items():
        for ts in serie.dropna().index:
            marcados.append((dia, ts))
    marcados.sort(key=lambda par: par[1])
    cego_por_dia = {dia: pd.Series(None, index=serie.index, dtype=object)
                     for dia, serie in sinal_base_por_dia.items()}
    for k, (dia, ts) in enumerate(marcados):
        cego_por_dia[dia][ts] = "long" if k % 2 == 0 else "short"
    return cego_por_dia


# --------------------------------------------------------------------------
# Cache por processo
# --------------------------------------------------------------------------
_CACHE: dict = {}


def _carrega_cache():
    if "dias" not in _CACHE:
        dias = sim.IS_DIAS
        m1_por_dia = {d: _prep_m1(df) for d, df in sim.carregar_m1(dias).items()}
        ticks_por_dia = sim.carregar_ticks(dias)

        seguir3 = {d: _sinal_seguir3(m1_por_dia[d]) for d in dias}
        cego_de_seguir3 = _sinal_cego_espelha(seguir3)  # so' para a diferenca seguir3-cego

        elig_filtro = {d: _elegivel_filtro(m1_por_dia[d]) for d in dias if d in m1_por_dia}

        lado_vencedor = {}
        for trail_mult in TRAIL_MULTS:
            lado_vencedor[trail_mult] = {}
            for d in dias:
                if d not in ticks_por_dia:
                    continue
                hip = sim.resolver_hipoteticos_dia_deixa_correr(m1_por_dia[d], ticks_por_dia[d], trail_mult)
                bruto = sim.sinal_lado_vencedor(m1_por_dia[d], *hip)
                lado_vencedor[trail_mult][d] = bruto.where(elig_filtro[d])

        # cego da GRADE espelha lado_vencedor (o sinal novo) -- 1 mirror por
        # trail_mult, ja que os instantes elegiveis de lado_vencedor mudam
        # com o trail (o painel hipotetico muda).
        cego_grade = {trail_mult: _sinal_cego_espelha(lado_vencedor[trail_mult]) for trail_mult in TRAIL_MULTS}

        _CACHE["dias"] = dias
        _CACHE["m1_por_dia"] = m1_por_dia
        _CACHE["ticks_por_dia"] = ticks_por_dia
        _CACHE["sinais"] = {
            "seguir3": {tm: seguir3 for tm in TRAIL_MULTS},
            "lado_vencedor": lado_vencedor,
            "cego": cego_grade,
            "cego_de_seguir3": {tm: cego_de_seguir3 for tm in TRAIL_MULTS},
        }
    return _CACHE["dias"], _CACHE["m1_por_dia"], _CACHE["ticks_por_dia"], _CACHE["sinais"]


def _roda_uma(spec: dict) -> tuple[str, object, dict, str]:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _saida_dinamica_tick_sim as sim
    from backtest.intraday.report import linha, linha_de_resultado, num_br

    dias, m1_por_dia, ticks_por_dia, sinais_todos = _carrega_cache()
    sinais = sinais_todos[spec["nome_sinal"]][spec["trail_mult"]]
    modo = spec["modo_entrada"]
    queue_ahead = spec["queue_ahead_qty"]
    trail_mult = spec["trail_mult"]

    censurado = sim.simular_deixa_correr(dias, m1_por_dia, ticks_por_dia, sinais, trail_mult,
                                          modo_entrada=modo, queue_ahead_qty=queue_ahead,
                                          capital_inicial=sim.CAPITAL_REAL_BRL)
    livre = sim.simular_deixa_correr(dias, m1_por_dia, ticks_por_dia, sinais, trail_mult,
                                      modo_entrada=modo, queue_ahead_qty=queue_ahead, capital_inicial=None)

    resultado = sim.monta_resultado(censurado.trades, sim.CAPITAL_REAL_BRL)
    stats = sim.estatisticas(livre.trades)

    trades = livre.trades
    diags = livre.diagnosticos
    n = len(trades)
    ativou_pct = 100.0 * sum(d.ativou for d in diags) / n if n else float("nan")
    # ticks de preco capturados LIQUIDOS de deslize (nao de corretagem, que
    # e' um valor fixo em R$, nao converte limpo pra ticks) -- so' dos
    # trades VENCEDORES (pnl_brl>0, ja com deslize+corretagem descontados).
    ganhos_ticks = [dgn.capturado_ticks - sim.SLIPPAGE_TICKS
                    for t, dgn in zip(trades, diags) if t.pnl_brl > 0]
    ganho_tk_med = float(np.mean(ganhos_ticks)) if ganhos_ticks else float("nan")
    ganho_tk_p50 = float(np.median(ganhos_ticks)) if ganhos_ticks else float("nan")
    ganho_tk_p90 = float(np.percentile(ganhos_ticks, 90)) if ganhos_ticks else float("nan")
    mfe_med = float(np.mean([d.mfe_ticks for d in diags])) if n else float("nan")
    capt_med = float(np.mean([d.capturado_ticks for d in diags])) if n else float("nan")
    hold_med = float(np.mean([d.holding_min for d in diags])) if n else float("nan")
    from collections import Counter
    contagem = Counter(t.exit_detail for t in trades)
    pct = lambda chave: 100.0 * contagem.get(chave, 0) / n if n else float("nan")  # noqa: E731

    if modo == "limite":
        tent = livre.tentativas_limite
        fill_pct = 100.0 * sum(1 for t in tent if t.preenchida) / len(tent) if tent else float("nan")
        atrasos = [t.atraso_min for t in tent if t.preenchida]
        atraso_med = float(pd.Series(atrasos).median()) if atrasos else float("nan")
        fill_txt, atraso_txt = f"{num_br(fill_pct, 1)}%", num_br(atraso_med, 2)
    else:
        fill_txt, atraso_txt = "—", "—"

    extras = {
        "R$/op": num_br(stats["media"], 2),
        "IC95 R$/op": f"[{num_br(stats['ic95'][0], 2)};{num_br(stats['ic95'][1], 2)}]",
        "win%": f"{num_br(stats['win_pct'], 1)}%",
        "breakeven%": f"{num_br(stats['breakeven_empirico'], 1)}%",
        "ativou%": f"{num_br(ativou_pct, 1)}%",
        "ganho tk med": num_br(ganho_tk_med, 2),
        "ganho tk p50": num_br(ganho_tk_p50, 2),
        "ganho tk p90": num_br(ganho_tk_p90, 2),
        "MFE tk med": num_br(mfe_med, 2),
        "capt tk med": num_br(capt_med, 2),
        "hold min": num_br(hold_med, 2),
        "%inicial": f"{num_br(pct('inicial'), 1)}%",
        "%piso": f"{num_br(pct('piso'), 1)}%",
        "%trail": f"{num_br(pct('trailing'), 1)}%",
        "%flat": f"{num_br(pct('forced_flatten'), 1)}%",
        "fill%": fill_txt,
        "atraso min": atraso_txt,
        "preg s/trade": str(len(dias) - len(censurado.dias_com_trade)),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, sim.CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)
    texto = f"[{spec['idx']}/{spec['total']}] {linha(item, EXTRAS, 11)}"
    return spec["rotulo"], item, stats, texto


def main() -> None:
    from backtest.intraday.fidelidade import fidelidade_for
    from backtest.intraday.report import cabecalho, linha

    t0 = time.perf_counter()
    print("[saida_deixa_correr] preparando cache no processo principal "
          "(sinais + hipoteticos deixa-correr -- pode levar alguns minutos)...", flush=True)
    dias, m1_por_dia, ticks_por_dia, sinais_todos = _carrega_cache()
    print(f"[saida_deixa_correr] janela IS: {len(dias)} pregoes ({dias[0]}..{dias[-1]}) "
          f"-- cache pronto em {time.perf_counter()-t0:.1f}s", flush=True)

    for nome in ("seguir3", "lado_vencedor", "cego"):
        for tm in TRAIL_MULTS:
            n = sum(sinais_todos[nome][tm][d].notna().sum() for d in dias)
            print(f"[saida_deixa_correr] gatilhos {nome} trail={tm}x: {n}", flush=True)

    fid = fidelidade_for("WDO@")
    print(f"[saida_deixa_correr] fidelidade WDO@: queue_ahead_qty(entrada)={fid.queue_ahead_qty} "
          f"medido_em={fid.medido_em}\n", flush=True)

    specs = []
    for nome_sinal in ("seguir3", "lado_vencedor", "cego"):
        for trail_mult in TRAIL_MULTS:
            for modo in ("teto", "limite"):
                rotulo = f"{nome_sinal} trail{trail_mult:.0f}x {modo}"
                specs.append(dict(rotulo=rotulo, nome_sinal=nome_sinal, trail_mult=trail_mult,
                                   modo_entrada=modo, queue_ahead_qty=fid.queue_ahead_qty))
    total = len(specs)
    for idx, spec in enumerate(specs, start=1):
        spec["idx"], spec["total"] = idx, total

    print(f"[saida_deixa_correr] {total} rodadas (6 celulas x 2 entradas), rodando em paralelo\n", flush=True)
    print(cabecalho(EXTRAS, 11), flush=True)

    resultados: dict[str, object] = {}
    stats_por_rotulo: dict[str, dict] = {}
    n_workers = min(total, 8)
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            rotulo, item, stats, texto = future.result()
            resultados[rotulo] = item
            stats_por_rotulo[rotulo] = stats
            print(texto, flush=True)

    print(f"\n[saida_deixa_correr] total: {time.perf_counter() - t0:.1f}s")

    print("\n=== TETO A MERCADO (6 celulas) ===")
    print(cabecalho(EXTRAS, 11))
    for nome_sinal in ("seguir3", "lado_vencedor", "cego"):
        for trail_mult in TRAIL_MULTS:
            item = resultados.get(f"{nome_sinal} trail{trail_mult:.0f}x teto")
            if item is not None:
                print(linha(item, EXTRAS, 11))

    print("\n=== ENTRADA-LIMITE (6 celulas) ===")
    print(cabecalho(EXTRAS, 11))
    for nome_sinal in ("seguir3", "lado_vencedor", "cego"):
        for trail_mult in TRAIL_MULTS:
            item = resultados.get(f"{nome_sinal} trail{trail_mult:.0f}x limite")
            if item is not None:
                print(linha(item, EXTRAS, 11))

    # diferencas -- ver docstring do modulo sobre por que ha' DOIS cegos
    # internos (um espelhando seguir3, outro espelhando lado_vencedor).
    print("\n=== seguir3 - cego(seguir3) e lado_vencedor - cego(lado_vencedor), teto ===")
    for trail_mult in TRAIL_MULTS:
        specs_cego_seguir3 = dict(rotulo=f"cego(seguir3) trail{trail_mult:.0f}x teto",
                                   nome_sinal="cego_de_seguir3", trail_mult=trail_mult,
                                   modo_entrada="teto", queue_ahead_qty=fid.queue_ahead_qty,
                                   idx=0, total=0)
        _, _, stats_cego_seguir3, _ = _roda_uma(specs_cego_seguir3)
        for nome_sinal, rot_cego in (("seguir3", None), ("lado_vencedor", None)):
            if nome_sinal == "seguir3":
                st, st_cego = stats_por_rotulo[f"seguir3 trail{trail_mult:.0f}x teto"], stats_cego_seguir3
                label = "seguir3 - cego(seguir3)"
            else:
                st = stats_por_rotulo[f"lado_vencedor trail{trail_mult:.0f}x teto"]
                st_cego = stats_por_rotulo[f"cego trail{trail_mult:.0f}x teto"]
                label = "lado_vencedor - cego(lado_vencedor)"
            if st["n"] == 0 or st_cego["n"] == 0:
                print(f"  {label} [trail{trail_mult:.0f}x]: sem trades suficientes")
                continue
            diff = st["media"] - st_cego["media"]
            se1 = st["desvio"] / (st["n"] ** 0.5) if st["n"] > 1 else 0.0
            se2 = st_cego["desvio"] / (st_cego["n"] ** 0.5) if st_cego["n"] > 1 else 0.0
            se_diff = (se1 ** 2 + se2 ** 2) ** 0.5
            lo, hi = diff - 1.96 * se_diff, diff + 1.96 * se_diff
            print(f"  {label:32s} [trail{trail_mult:.0f}x]  diff={diff:8.2f}  "
                  f"IC95=[{lo:8.2f};{hi:8.2f}]  (n={st['n']}/{st_cego['n']})")


if __name__ == "__main__":
    main()
