"""WDO@ M1: sinal de ENTRADA sem nenhuma cor de candle -- so oscilacao
(filtro de volatilidade) e "pra que lado historicamente deu mais WIN" --
com a MESMA saida dinamica e a MESMA janela IS de
`wdo_cor_minuto_saida_dinamica_2026_09_24.py` (ver a docstring de
`_saida_dinamica_tick_sim.py` para as suposicoes de janela/dados, e a
docstring daquele script para o porque da janela IS reconstruida). Pedido do
coordenador enquanto o script de cor rodava -- MESMO simulador, MESMA regra
de saida (`_saida_dinamica_tick_sim.simular`/`resolver_saida`), so' o
GATILHO de entrada muda.

## Sinais (avaliados no fechamento de CADA barra M1, so em posicao ZERADA)

  1. **FILTRO de oscilacao** -- media do range (high-low) das ultimas N=10
     barras M1, em ticks. So entra se `media10 >= k+2` (k=2 aqui, entao
     `>=4` ticks) -- folga minima para o limiar de lucro (k ticks) ser
     alcancavel liquido de 1 tick de deslize. Variantes `{off, on}`.
  2. **LADO**:
     * `lado_vencedor`: olha as ultimas 21 barras M1; para CADA uma, simula
       (nos ticks, so' com dado PASSADO) um long e um short hipoteticos
       entrando no OPEN daquela barra, com a MESMA regra k/stop da celula
       (`_saida_dinamica_tick_sim.resolver_hipoteticos_dia`); conta vitorias
       por lado ENTRE AS JA RESOLVIDAS antes de agora (uma hipotetica ainda
       pendente nao pode informar a decisao -- e' o que faz isto nao ser
       look-ahead); fica com o lado de mais vitorias, empate (inclusive 0-0)
       pula. Depende do estilo de saida da celula (fixo/trailing usam regras
       de resolucao diferentes), por isso e' recalculado para os dois.
     * `tendencia`: sinal de `close[t] - close[t-10]` (zero pula).
     * `cego`: CONTROLE -- mesma elegibilidade (mediana21 disponivel + filtro,
       se ligado) que as outras duas, lado alternado (as cegas).
  3. Grade: `lado {lado_vencedor, tendencia, cego} x filtro {off, on} x saida
     {fixo, trailing}`, k=2 fixo = 12 celulas, ENTRADA A MERCADO (teto).
     Entrada-limite (fila calibrada de `fidelidade.py`) so' roda para as 2
     melhores celulas teto por R$/op (extra informativo, nao a grade
     inteira -- pedido do coordenador).

## Suposicoes explicitas (regra 1 de disciplina-de-codigo)

  * o hipotetico de `lado_vencedor` entra no OPEN da barra (nao no primeiro
    tick apos o fechamento) e NAO paga deslize/corretagem -- e' feature de
    DECISAO, nao execucao real; o trade de verdade que a decisao resultante
    abre continua pagando os dois, igual a todo o resto deste par de
    scripts;
  * o stop de cada hipotetico usa a MEDIANA21 da PROPRIA barra hipotetica
    (nao a da barra de decisao atual) -- e' "a mesma regra de stop", aplicada
    no contexto de cada barra passada, nao um numero congelado;
  * empate 0-0 em `lado_vencedor` conta como empate (pula), nao como "sem
    dado" -- literal ao pedido ("tie -> skip").
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

K_TICKS = 2.0
FILTRO_MIN_TICKS = K_TICKS + 2.0
TENDENCIA_LOOKBACK = 10
VOL_FILTRO_LOOKBACK = 10

EXTRAS = ("R$/op", "IC95 R$/op", "win%", "breakeven%", "ganho med", "perda med",
          "fill%", "atraso min", "preg s/trade")


def _prep_m1(m1_dia: pd.DataFrame) -> pd.DataFrame:
    m1_dia = m1_dia.copy()
    m1_dia["media10_ticks"] = m1_dia["range_ticks"].rolling(VOL_FILTRO_LOOKBACK).mean()
    m1_dia["tendencia_sinal"] = np.sign(m1_dia["close"] - m1_dia["close"].shift(TENDENCIA_LOOKBACK))
    return m1_dia


def _elegivel(m1_dia: pd.DataFrame, filtro_on: bool) -> pd.Series:
    base = m1_dia["median21_ticks"].notna()
    if not filtro_on:
        return base
    return base & (m1_dia["media10_ticks"] >= FILTRO_MIN_TICKS)


def _sinal_tendencia(m1_dia: pd.DataFrame, filtro_on: bool) -> pd.Series:
    elig = _elegivel(m1_dia, filtro_on)
    lado = pd.Series(None, index=m1_dia.index, dtype=object)
    sinal = m1_dia["tendencia_sinal"]
    lado[elig & (sinal > 0)] = "long"
    lado[elig & (sinal < 0)] = "short"
    return lado


def _sinal_cego(elig_por_dia: dict) -> dict:
    marcados = []
    for dia, elig in elig_por_dia.items():
        for ts in elig[elig].index:
            marcados.append((dia, ts))
    marcados.sort(key=lambda par: par[1])
    cego_por_dia = {dia: pd.Series(None, index=elig.index, dtype=object) for dia, elig in elig_por_dia.items()}
    for k, (dia, ts) in enumerate(marcados):
        cego_por_dia[dia][ts] = "long" if k % 2 == 0 else "short"
    return cego_por_dia


def _sinal_lado_vencedor(m1_dia: pd.DataFrame, hipoteticos: tuple, filtro_on: bool) -> pd.Series:
    long_ts, long_win, short_ts, short_win = hipoteticos
    lado = sim.sinal_lado_vencedor(m1_dia, long_ts, long_win, short_ts, short_win)
    elig = _elegivel(m1_dia, filtro_on)
    return lado.where(elig)


# --------------------------------------------------------------------------
# Cache por processo
# --------------------------------------------------------------------------
_CACHE: dict = {}


def _carrega_cache():
    if "dias" not in _CACHE:
        dias = sim.IS_DIAS
        m1_por_dia = {d: _prep_m1(df) for d, df in sim.carregar_m1(dias).items()}
        ticks_por_dia = sim.carregar_ticks(dias)

        elig_off = {d: _elegivel(m1_por_dia[d], False) for d in dias}
        elig_on = {d: _elegivel(m1_por_dia[d], True) for d in dias}

        tendencia = {False: {d: _sinal_tendencia(m1_por_dia[d], False) for d in dias},
                     True: {d: _sinal_tendencia(m1_por_dia[d], True) for d in dias}}
        cego = {False: _sinal_cego(elig_off), True: _sinal_cego(elig_on)}

        hip_fixo = {d: sim.resolver_hipoteticos_dia(m1_por_dia[d], ticks_por_dia[d], K_TICKS, False)
                    for d in dias if d in ticks_por_dia}
        hip_trail = {d: sim.resolver_hipoteticos_dia(m1_por_dia[d], ticks_por_dia[d], K_TICKS, True)
                     for d in dias if d in ticks_por_dia}
        lado_vencedor = {
            (False, False): {d: _sinal_lado_vencedor(m1_por_dia[d], hip_fixo[d], False) for d in hip_fixo},
            (False, True): {d: _sinal_lado_vencedor(m1_por_dia[d], hip_fixo[d], True) for d in hip_fixo},
            (True, False): {d: _sinal_lado_vencedor(m1_por_dia[d], hip_trail[d], False) for d in hip_trail},
            (True, True): {d: _sinal_lado_vencedor(m1_por_dia[d], hip_trail[d], True) for d in hip_trail},
        }

        _CACHE["dias"] = dias
        _CACHE["m1_por_dia"] = m1_por_dia
        _CACHE["ticks_por_dia"] = ticks_por_dia
        _CACHE["sinais"] = {
            "tendencia": tendencia,
            "cego": {False: {False: cego[False], True: cego[False]}, True: {False: cego[True], True: cego[True]}},
            # cego nao depende do estilo de saida, so' do filtro -- reindexado
            # (filtro, trailing) so' para caber na mesma interface das outras.
            "lado_vencedor": {(f, t): lado_vencedor[(t, f)] for f in (False, True) for t in (False, True)},
        }
    return _CACHE["dias"], _CACHE["m1_por_dia"], _CACHE["ticks_por_dia"], _CACHE["sinais"]


def _pega_sinal(sinais: dict, nome_lado: str, filtro_on: bool, trailing: bool) -> dict:
    if nome_lado == "tendencia":
        return sinais["tendencia"][filtro_on]
    if nome_lado == "cego":
        return sinais["cego"][filtro_on][trailing]
    if nome_lado == "lado_vencedor":
        return sinais["lado_vencedor"][(filtro_on, trailing)]
    raise ValueError(nome_lado)


def _roda_uma(spec: dict) -> tuple[str, object, dict, str]:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _saida_dinamica_tick_sim as sim
    from backtest.intraday.report import linha, linha_de_resultado, num_br

    dias, m1_por_dia, ticks_por_dia, sinais_todos = _carrega_cache()
    sinais = _pega_sinal(sinais_todos, spec["nome_lado"], spec["filtro_on"], spec["trailing"])
    modo = spec["modo_entrada"]
    queue_ahead = spec["queue_ahead_qty"]

    censurado = sim.simular(dias, m1_por_dia, ticks_por_dia, sinais, K_TICKS, spec["trailing"],
                             modo_entrada=modo, queue_ahead_qty=queue_ahead,
                             capital_inicial=sim.CAPITAL_REAL_BRL)
    livre = sim.simular(dias, m1_por_dia, ticks_por_dia, sinais, K_TICKS, spec["trailing"],
                         modo_entrada=modo, queue_ahead_qty=queue_ahead, capital_inicial=None)

    resultado = sim.monta_resultado(censurado.trades, sim.CAPITAL_REAL_BRL)
    stats = sim.estatisticas(livre.trades)

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
        "ganho med": num_br(stats["ganho_medio"], 2),
        "perda med": num_br(stats["perda_media"], 2),
        "fill%": fill_txt,
        "atraso min": atraso_txt,
        "preg s/trade": str(len(dias) - len(censurado.dias_com_trade)),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, sim.CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)
    texto = f"[{spec['idx']}/{spec['total']}] {linha(item, EXTRAS, 13)}"
    return spec["rotulo"], item, stats, texto


def main() -> None:
    from backtest.intraday.fidelidade import fidelidade_for
    from backtest.intraday.report import cabecalho, linha

    t0 = time.perf_counter()
    print(f"[oscilacao_lado_saida_dinamica] preparando cache no processo principal "
          f"(sinais + hipoteticos de lado_vencedor -- pode levar alguns minutos)...", flush=True)
    dias, m1_por_dia, ticks_por_dia, sinais_todos = _carrega_cache()
    print(f"[oscilacao_lado_saida_dinamica] janela IS: {len(dias)} pregoes "
          f"({dias[0]}..{dias[-1]}) -- cache pronto em {time.perf_counter()-t0:.1f}s", flush=True)

    for nome in ("tendencia", "cego", "lado_vencedor"):
        for filtro_on in (False, True):
            n = sum(_pega_sinal(sinais_todos, nome, filtro_on, False)[d].notna().sum() for d in dias)
            print(f"[oscilacao_lado_saida_dinamica] gatilhos {nome} filtro={'on' if filtro_on else 'off'}: {n}",
                  flush=True)

    fid = fidelidade_for("WDO@")
    print(f"[oscilacao_lado_saida_dinamica] fidelidade WDO@: queue_ahead_qty(entrada)={fid.queue_ahead_qty} "
          f"medido_em={fid.medido_em}\n", flush=True)

    specs = []
    for nome_lado in ("lado_vencedor", "tendencia", "cego"):
        for filtro_on in (False, True):
            for trailing, nome_saida in ((False, "fixo"), (True, "trailing")):
                rotulo = f"{nome_lado} filtro-{'on' if filtro_on else 'off'} {nome_saida} teto"
                specs.append(dict(rotulo=rotulo, nome_lado=nome_lado, filtro_on=filtro_on,
                                   trailing=trailing, modo_entrada="teto",
                                   queue_ahead_qty=fid.queue_ahead_qty))
    total = len(specs)
    for idx, spec in enumerate(specs, start=1):
        spec["idx"], spec["total"] = idx, total

    print(f"[oscilacao_lado_saida_dinamica] {total} celulas TETO, rodando em paralelo\n", flush=True)
    print(cabecalho(EXTRAS, 13), flush=True)

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

    print(f"\n[oscilacao_lado_saida_dinamica] 12 celulas teto: {time.perf_counter() - t0:.1f}s")

    # as 2 melhores por R$/op (SEM portao de capital -- a leitura por trade,
    # ver docstring) ganham a rodada informativa de entrada-limite.
    melhores = sorted(specs, key=lambda s: stats_por_rotulo[s["rotulo"]]["media"], reverse=True)[:2]
    print(f"\n[oscilacao_lado_saida_dinamica] 2 melhores por R$/op: "
          f"{[m['rotulo'] for m in melhores]} -- rodando entrada-limite (informativo)\n", flush=True)

    specs_limite = []
    for m in melhores:
        s = dict(m)
        s["rotulo"] = m["rotulo"].replace(" teto", " limite")
        s["modo_entrada"] = "limite"
        specs_limite.append(s)
    for idx, spec in enumerate(specs_limite, start=1):
        spec["idx"], spec["total"] = idx, len(specs_limite)

    with ProcessPoolExecutor(max_workers=len(specs_limite)) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs_limite}
        for future in as_completed(futures):
            rotulo, item, stats, texto = future.result()
            resultados[rotulo] = item
            print(texto, flush=True)

    print(f"\n[oscilacao_lado_saida_dinamica] total: {time.perf_counter() - t0:.1f}s")

    print("\n=== TETO A MERCADO (12 celulas) ===")
    print(cabecalho(EXTRAS, 13))
    for spec in specs:
        item = resultados.get(spec["rotulo"])
        if item is not None:
            print(linha(item, EXTRAS, 13))

    print("\n=== ENTRADA-LIMITE (2 melhores celulas, informativo) ===")
    print(cabecalho(EXTRAS, 13))
    for spec in specs_limite:
        item = resultados.get(spec["rotulo"])
        if item is not None:
            print(linha(item, EXTRAS, 13))

    # diferencas lado_vencedor - cego e tendencia - cego, por (filtro, saida)
    print("\n=== lado_vencedor / tendencia vs cego (R$/op, IC95 da diferenca) ===")
    for filtro_on in (False, True):
        for trailing, nome_saida in ((False, "fixo"), (True, "trailing")):
            rot_cego = f"cego filtro-{'on' if filtro_on else 'off'} {nome_saida} teto"
            st_cego = stats_por_rotulo.get(rot_cego)
            if st_cego is None:
                continue
            for nome_lado in ("lado_vencedor", "tendencia"):
                rot = f"{nome_lado} filtro-{'on' if filtro_on else 'off'} {nome_saida} teto"
                st = stats_por_rotulo.get(rot)
                if st is None or st["n"] == 0 or st_cego["n"] == 0:
                    continue
                diff = st["media"] - st_cego["media"]
                se1 = st["desvio"] / (st["n"] ** 0.5) if st["n"] > 1 else 0.0
                se2 = st_cego["desvio"] / (st_cego["n"] ** 0.5) if st_cego["n"] > 1 else 0.0
                se_diff = (se1 ** 2 + se2 ** 2) ** 0.5
                lo, hi = diff - 1.96 * se_diff, diff + 1.96 * se_diff
                print(f"  {nome_lado:14s} - cego  [filtro-{'on' if filtro_on else 'off':>3s} {nome_saida:9s}]  "
                      f"diff={diff:8.2f}  IC95=[{lo:8.2f};{hi:8.2f}]  (n={st['n']}/{st_cego['n']})")


if __name__ == "__main__":
    main()
