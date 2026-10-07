"""WDO@ M1: cor/sequencia de candle como GATILHO de entrada, SAIDA DINAMICA
(sai a mercado no primeiro instante em que o P&L aberto, medido tick a tick,
alcanca k ticks favoraveis) em vez de alvo fixo. Pequeno teste, ordem do
dono -- REFUTAR PRIMEIRO, nao rodar a base inteira, nao tocar o OOS.

## Hipotese

`seguir3`: depois de >=3 velas M1 verdes seguidas, compra; depois de >=3
vermelhas, vende -- a leitura de CONTINUACAO que
`wdo_cor_minuto_1mes_2026_09_10.py` (ver a memoria `cor_do_minuto_wdo_
refutada_2026_09_10.md`) achou mais forte (z=1,95, n=411 na frequencia de
cor; +R$1,496 no IS que DISSOLVEU no OOS medindo "compra no open da barra
seguinte, vende no close dela"). A pergunta NOVA aqui e' se uma saida
DINAMICA -- monitorar tick a tick e sair no primeiro lucro aberto, em vez de
fechar sempre no proximo close -- muda o veredito. `cego`: CONTROLE, MESMOS
instantes de entrada, lado escolhido as cegas (par/impar da ordem de entrada,
alternado) -- se `seguir3` nao vencer `cego`, a regra de saida nao e' o edge,
so' mudou a forma de medir o mesmo ruido.

## Janela e suposicoes -- ver docstring de `_saida_dinamica_tick_sim.py`

Script anterior nao existe mais no repo (nao commitado). Janela IS
reconstruida = ultimos 21 pregoes da populacao 177-pregoes documentada em
`backtest.intraday.profiles.FUTURES_PROFILES["WDO@"]`
(2025-12-08..2026-08-25), menos 3 dias com tick ausente/incompleto = 18
pregoes efetivos (`_saida_dinamica_tick_sim.IS_DIAS`).

Outras suposicoes explicitas (regra 1 de disciplina-de-codigo):

  * barra BRANCA (`close==open`) QUEBRA a sequencia (nao conta pra nenhum
    lado) -- e' virtualmente inexistente no M1 continuo ajustado usado aqui
    (precos fracionarios, doji exato e' coincidencia), entao na pratica
    verde/vermelho alternam quase sem freio;
  * mediana21 e sequencia REINICIAM a cada pregao (nao atravessam a virada
    do dia -- gap overnight tem economia diferente de continuidade
    intradiaria);
  * TTL da entrada-limite (modo informativo) = 5 minutos, nao medido --
    "prazo curto" pedido pelo dono, sem calibracao propria;
  * achatamento as 18:25 BRT (corte de 5min antes do fim, 18:30) -- mesma
    regra do motor de producao (`e6d676e`).

## Grade -- 8 celulas (teto a mercado) + 8 informativas (entrada-limite)

`sinal {seguir3, cego} x k {2, 3} x saida {fixo, trailing} = 8`, com
`modo_entrada` em {'teto', 'limite'} -- limite usa a fila calibrada de
`backtest.intraday.fidelidade` (WDO@, `queue_ahead_qty` -- HOJE 329,0
contratos, recalibrado em 2026-09-10; NAO e' o 438 da calibracao de
2026-09-09 que o pedido citou, e o script le' o numero da tabela em tempo de
execucao, nunca digitado na mao).

Cada celula roda DUAS vezes: com o portao de capital R$375,00 (1 contrato,
abre so' com caixa >= R$150,00 -- regra de 2026-09-08, "piso e' indicacao de
PARTIDA") para a linha PADRAO da tabela, e SEM portao (caixa infinito) para
as estatisticas por trade nos `extras` -- um caixa de R$375 pode CENSURAR a
janela depois de poucas perdas, e a leitura por trade nao pode depender
disso (ver CLAUDE.md, "O piso de capital e indicacao de PARTIDA, nunca
condicao de continuidade").
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import _saida_dinamica_tick_sim as sim  # noqa: E402

EXTRAS = ("R$/op", "IC95 R$/op", "win%", "breakeven%", "ganho med", "perda med",
          "fill%", "atraso min", "preg s/trade")


def _sinal_seguir3(m1_dia: pd.DataFrame) -> pd.Series:
    lado = pd.Series(None, index=m1_dia.index, dtype=object)
    cond_long = (m1_dia["streak_cor"] == "verde") & (m1_dia["streak_len"] >= 3)
    cond_short = (m1_dia["streak_cor"] == "vermelho") & (m1_dia["streak_len"] >= 3)
    lado[cond_long] = "long"
    lado[cond_short] = "short"
    return lado


def _sinal_cego(seguir3_por_dia: dict) -> dict:
    """MESMOS instantes de entrada de `seguir3` (concatenados em ordem
    cronologica entre pregoes), lado alternado -- as cegas quanto a cor."""
    marcados = []
    for dia, serie in seguir3_por_dia.items():
        for ts in serie.dropna().index:
            marcados.append((dia, ts))
    marcados.sort(key=lambda par: par[1])
    cego_por_dia = {dia: pd.Series(None, index=serie.index, dtype=object)
                     for dia, serie in seguir3_por_dia.items()}
    for k, (dia, ts) in enumerate(marcados):
        cego_por_dia[dia][ts] = "long" if k % 2 == 0 else "short"
    return cego_por_dia


#: Cache POR PROCESSO (chave = nada, so' existe uma janela) -- cada
#: processo filho carrega M1+tick UMA vez e reusa nas celulas seguintes que
#: caem nele, em vez de o processo PAI serializar ~50MB de DataFrame por
#: `submit` (16 vezes). Mesmo espirito de `_DF_CACHE` em
#: `wdof1_deslize_alvo_is_oos_2026_09_08.py`.
_CACHE: dict = {}


def _carrega_cache():
    if "dias" not in _CACHE:
        import _saida_dinamica_tick_sim as sim
        dias = sim.IS_DIAS
        m1_por_dia = sim.carregar_m1(dias)
        ticks_por_dia = sim.carregar_ticks(dias)
        seguir3_por_dia = {d: _sinal_seguir3(m1_por_dia[d]) for d in dias}
        cego_por_dia = _sinal_cego(seguir3_por_dia)
        _CACHE["dias"] = dias
        _CACHE["m1_por_dia"] = m1_por_dia
        _CACHE["ticks_por_dia"] = ticks_por_dia
        _CACHE["sinais"] = {"seguir3": seguir3_por_dia, "cego": cego_por_dia}
    return (_CACHE["dias"], _CACHE["m1_por_dia"], _CACHE["ticks_por_dia"], _CACHE["sinais"])


def _roda_uma(spec: dict) -> tuple[str, object, str]:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _saida_dinamica_tick_sim as sim
    from backtest.intraday.report import linha, linha_de_resultado, num_br

    dias, m1_por_dia, ticks_por_dia, sinais_por_nome = _carrega_cache()
    sinais = sinais_por_nome[spec["nome_sinal"]]
    k_ticks = spec["k"]
    trailing = spec["trailing"]
    modo = spec["modo_entrada"]
    queue_ahead = spec["queue_ahead_qty"]

    # linha PADRAO: com portao de capital real (R$375,00, so' margem crua p/
    # 1o contrato -- ver docstring do modulo).
    censurado = sim.simular(dias, m1_por_dia, ticks_por_dia, sinais, k_ticks, trailing,
                             modo_entrada=modo, queue_ahead_qty=queue_ahead,
                             capital_inicial=sim.CAPITAL_REAL_BRL)
    # extras: SEM portao, para a leitura por trade nao herdar a censura do caixa.
    livre = sim.simular(dias, m1_por_dia, ticks_por_dia, sinais, k_ticks, trailing,
                         modo_entrada=modo, queue_ahead_qty=queue_ahead, capital_inicial=None)

    resultado = sim.monta_resultado(censurado.trades, sim.CAPITAL_REAL_BRL)
    stats = sim.estatisticas(livre.trades)

    if modo == "limite":
        tent = livre.tentativas_limite
        fill_pct = 100.0 * sum(1 for t in tent if t.preenchida) / len(tent) if tent else float("nan")
        atrasos = [t.atraso_min for t in tent if t.preenchida]
        atraso_med = float(pd.Series(atrasos).median()) if atrasos else float("nan")
        fill_txt = f"{num_br(fill_pct, 1)}%"
        atraso_txt = num_br(atraso_med, 2)
    else:
        fill_txt = "—"
        atraso_txt = "—"

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
    return spec["rotulo"], item, texto


def main() -> None:
    from backtest.intraday.fidelidade import fidelidade_for
    from backtest.intraday.report import cabecalho

    t0 = time.perf_counter()
    dias = sim.IS_DIAS
    print(f"[cor_minuto_saida_dinamica] janela IS: {len(dias)} pregoes "
          f"({dias[0]}..{dias[-1]})", flush=True)

    m1_por_dia = sim.carregar_m1(dias)
    ticks_por_dia = sim.carregar_ticks(dias)
    dt_carga = time.perf_counter() - t0
    print(f"[cor_minuto_saida_dinamica] carga M1+tick: {dt_carga:.1f}s", flush=True)

    seguir3_por_dia = {d: _sinal_seguir3(m1_por_dia[d]) for d in dias}
    cego_por_dia = _sinal_cego(seguir3_por_dia)
    n_seguir3 = sum(s.notna().sum() for s in seguir3_por_dia.values())
    n_cego = sum(s.notna().sum() for s in cego_por_dia.values())
    print(f"[cor_minuto_saida_dinamica] gatilhos seguir3={n_seguir3}  cego={n_cego}"
          f"  (mesmos instantes, tem de bater)", flush=True)

    fid = fidelidade_for("WDO@")
    print(f"[cor_minuto_saida_dinamica] fidelidade WDO@ (backtest.intraday.fidelidade): "
          f"queue_ahead_qty(entrada)={fid.queue_ahead_qty}  medido_em={fid.medido_em}", flush=True)

    specs = []
    for nome_sinal in ("seguir3", "cego"):
        for k in (2, 3):
            for trailing, nome_saida in ((False, "fixo"), (True, "trailing")):
                for modo in ("teto", "limite"):
                    rotulo = f"{nome_sinal} k{k} {nome_saida} {modo}"
                    specs.append(dict(
                        rotulo=rotulo, nome_sinal=nome_sinal, k=float(k), trailing=trailing,
                        modo_entrada=modo, queue_ahead_qty=fid.queue_ahead_qty,
                    ))
    total = len(specs)
    for idx, spec in enumerate(specs, start=1):
        spec["idx"] = idx
        spec["total"] = total

    print(f"[cor_minuto_saida_dinamica] {total} celulas (8 teto + 8 entrada-limite "
          f"informativa), rodando em paralelo\n", flush=True)
    print(cabecalho(EXTRAS, 13), flush=True)

    resultados: dict[str, object] = {}
    n_workers = min(total, 8)
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            rotulo, item, texto = future.result()
            resultados[rotulo] = item
            print(texto, flush=True)

    print(f"\n[cor_minuto_saida_dinamica] total: {time.perf_counter() - t0:.1f}s")

    print("\n=== TETO A MERCADO (8 celulas) ===")
    print(cabecalho(EXTRAS, 13))
    from backtest.intraday.report import linha
    for nome_sinal in ("seguir3", "cego"):
        for k in (2, 3):
            for _t, nome_saida in ((False, "fixo"), (True, "trailing")):
                rotulo = f"{nome_sinal} k{k} {nome_saida} teto"
                item = resultados.get(rotulo)
                if item is not None:
                    print(linha(item, EXTRAS, 13))

    print("\n=== ENTRADA-LIMITE (8 celulas, informativo) ===")
    print(cabecalho(EXTRAS, 13))
    for nome_sinal in ("seguir3", "cego"):
        for k in (2, 3):
            for _t, nome_saida in ((False, "fixo"), (True, "trailing")):
                rotulo = f"{nome_sinal} k{k} {nome_saida} limite"
                item = resultados.get(rotulo)
                if item is not None:
                    print(linha(item, EXTRAS, 13))


if __name__ == "__main__":
    main()
