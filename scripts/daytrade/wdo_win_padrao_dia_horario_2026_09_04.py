"""Melhores/piores DIAS DA SEMANA e HORARIOS para WDO F1 e CopaWin -- pedido
do dono, 2026-09-04: "rode um teste com wdo e win, o objetivo e' descobrir
os melhores e piores dias para operar e dentro de cada dia os melhores e
piores horarios".

## O que isto NAO e'

Isto NAO propoe um filtro novo de ENTRADA. "Tendencia de dia/semana prediz
direcao" ja foi testado e refutado 2x nesta familia (`wdof1_padrao_
semana_2026_08_28.py`, `wdof1_tendencia_confirmacao_2026_08_28.py` -- cara-
ou-coroa, 48,7%). A pergunta aqui e' outra: dado que os dois robos JA
operam (a decisao de entrar e' do motor, sem mudanca nenhuma), EM QUE dia
da semana e QUE hora o resultado ja medido se concentra -- puramente
DESCRITIVO sobre trades que ja aconteceram. Sem risco de look-ahead (dia da
semana e hora de ENTRADA sao conhecidos no instante da entrada, ao
contrario da fracao-de-tempo-do-trade de `wdof1_padrao_tempo_
adverso_2026_09_03.py`).

## Robos, config de PRODUCAO (via `get_daytrade_robot`, sem digitar parametro)

- `wdo_grid_reload_maker` (TOP-1 do podio, WDO@).
- `copa_win` (TOP-2 do podio, WIN@).

## Capital: COM FOLGA, de proposito -- nao o capital real do dono

O capital real (~R$100/mes) censura a maior parte do historico pelo PISO de
capital (LICOES_DE_PRODUCAO.md, "dois pisos censuram todo backtest") -- um
pregao pulado por caixa insuficiente nao diz nada sobre terca ser melhor
que quinta, so' diz que faltou dinheiro. Por isso os niveis usados aqui sao
os JA MEDIDOS como estaveis (sem trava de caixa) em rodadas anteriores:
R$5.000 para WDO F1 (`wdof1_stress_capital_real_historico_completo.py` --
unico nivel testado que nunca trava no historico inteiro) e R$3.000 para
CopaWin (`copawin_piso_sobrevivencia_2026_08_29.py` -- identico de R$750 a
R$3.000, piso real e' R$750). A pergunta aqui e' o padrao TEMPORAL do robo
operando LIVRE, nao a sobrevivencia -- essa ja tem resposta registrada.

## Metodo

1. M1 salvo INTEIRO de cada simbolo (descarta pregao incompleto, <400
   barras -- mesmo corte de `wdof1_stress_...`), passada CONTINUA (uma so',
   nao dia a dia -- para o dimensionamento dinamico por caixa se comportar
   como em producao).
2. Cada trade fechado (TODOS os motivos de saida -- diferente de
   `wdof1_padrao_tempo_adverso`, aqui FORCED_FLATTEN tambem conta: e'
   resultado real do robo, nao ruido a descartar) tem `entry_ts` (UTC)
   convertido para `America/Sao_Paulo` -> dia da semana e hora local da
   ENTRADA.
3. Tres tabelas, numeros crus, veredito nenhum (convencao do projeto):
   a. por DIA DA SEMANA -- liquido total e liquido/PREGAO, normalizado
      pelo NUMERO DE PREGOES daquele dia da semana no periodo (nao pelos
      trades: um dia com menos segundas no calendario nao pode parecer
      pior so' por ter menos oportunidade). Dispersao SESSAO a SESSAO
      (mediana/pior/melhor pregao daquele dia da semana), mesma disciplina
      de `wdof1_padrao_semana_2026_08_28.py` -- e' o que separa "todo dia
      assim" de "um pregao bom carregando a media".
   b. por HORA DO DIA -- mesmo formato, liquido/pregao sobre o TOTAL de
      pregoes da amostra (toda sessao completa passa por toda hora).
   c. cruzamento DIA x HORA (a granularidade literal do pedido), com
      contagem de PREGOES COM TRADE naquela celula -- e' esse numero, nao
      o de trades, que decide se uma celula e' padrao ou ruido de 1 dia.

Uso: `python -u scripts/daytrade/wdo_win_padrao_dia_horario_2026_09_04.py`
"""
from __future__ import annotations

import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TZ = "America/Sao_Paulo"
MIN_BARRAS_POR_PREGAO = 400
DIAS_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta")

ROBOS = (
    dict(label="WDO F1 maker", symbol="WDO@", key="wdo_grid_reload_maker",
         economia=(0.01, 0.001), capital=5_000.0),
    dict(label="CopaWin", symbol="WIN@", key="copa_win",
         economia=(0.2, 1.0), capital=3_000.0),
)


def br(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(TZ)


def _carregar_bars(symbol: str) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "src"))
    from market_data_intraday.storage import load_m1

    df = load_m1(symbol).sort_index()
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {symbol!r}.")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return df[[d in completos for d in df.index.date]]


def _rodar(robo: dict) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import cabecalho, linha, linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    symbol = robo["symbol"]
    t0 = time.perf_counter()
    bars = _carregar_bars(symbol)
    strat = get_daytrade_robot(robo["key"], symbol=symbol)
    profile = profile_for(symbol)
    trade_tick_value, trade_tick_size = robo["economia"]
    cfg = config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=robo["capital"],
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    sessoes_locais = sorted(set(_to_local(pd.Timestamp(ts)).date() for ts in bars.index))
    resumo = linha_de_resultado(f"{robo['label']} ({symbol})", resultado, robo["capital"])
    tabela_txt = cabecalho() + "\n" + linha(resumo)

    trades_info = []
    for t in resultado.trades:
        entrada_local = _to_local(pd.Timestamp(t.entry_ts))
        trades_info.append(dict(
            data=entrada_local.date(), dia_semana=entrada_local.weekday(),
            hora=entrada_local.hour, pnl=t.pnl_brl,
        ))

    return dict(
        robo=robo, dt=dt, sessoes=sessoes_locais, trades=trades_info,
        tabela_txt=tabela_txt, wiped_out=resultado.wiped_out_at is not None,
        n_bars=len(bars),
    )


def _tabela_dia_semana(sessoes: list, trades: list) -> None:
    n_pregoes_por_dia = Counter(d.weekday() for d in sessoes)
    pnl_por_sessao: dict = defaultdict(float)
    for t in trades:
        pnl_por_sessao[t["data"]] += t["pnl"]

    print(f"\n--- por DIA DA SEMANA ({len(sessoes)} pregoes na amostra) ---")
    print(f"{'dia':>8} {'pregoes':>8} {'trades':>7} {'win%':>7} "
          f"{'liquido R$':>13} {'R$/pregao':>11} {'mediana/preg':>13} "
          f"{'pior preg':>11} {'melhor preg':>12}")
    print("-" * 96)
    linhas_liquido_pregao = []
    for d in range(5):
        n_pregoes = n_pregoes_por_dia.get(d, 0)
        do_dia = [t for t in trades if t["dia_semana"] == d]
        liquido = sum(t["pnl"] for t in do_dia)
        vencedores = sum(1 for t in do_dia if t["pnl"] > 0)
        win = 100 * vencedores / len(do_dia) if do_dia else 0.0
        pregoes_do_dia = [s for s in sessoes if s.weekday() == d]
        diarios = [pnl_por_sessao.get(s, 0.0) for s in pregoes_do_dia]
        liq_pregao = liquido / n_pregoes if n_pregoes else None
        mediana = statistics.median(diarios) if diarios else None
        pior = min(diarios) if diarios else None
        melhor = max(diarios) if diarios else None
        linhas_liquido_pregao.append((d, liq_pregao))
        print(f"{DIAS_SEMANA[d]:>8} {n_pregoes:>8} {len(do_dia):>7} "
              f"{br(win,1):>6}% {br(liquido):>13} {br(liq_pregao):>11} "
              f"{br(mediana):>13} {br(pior):>11} {br(melhor):>12}")

    validos = [(d, v) for d, v in linhas_liquido_pregao if v is not None]
    if validos:
        melhor_d = max(validos, key=lambda x: x[1])
        pior_d = min(validos, key=lambda x: x[1])
        print(f"\nmelhor dia (R$/pregao): {DIAS_SEMANA[melhor_d[0]]} ({br(melhor_d[1])}) | "
              f"pior dia: {DIAS_SEMANA[pior_d[0]]} ({br(pior_d[1])})")


def _tabela_hora(sessoes: list, trades: list) -> None:
    horas = sorted(set(t["hora"] for t in trades))
    n_pregoes_total = len(sessoes)
    print(f"\n--- por HORA DO DIA, local (todos os dias juntos, /{n_pregoes_total} pregoes) ---")
    print(f"{'hora':>6} {'trades':>7} {'preg. c/trade':>13} {'win%':>7} "
          f"{'liquido R$':>13} {'R$/trade':>10} {'R$/pregao':>11}")
    print("-" * 72)
    linhas_liquido_pregao = []
    for h in horas:
        da_hora = [t for t in trades if t["hora"] == h]
        liquido = sum(t["pnl"] for t in da_hora)
        vencedores = sum(1 for t in da_hora if t["pnl"] > 0)
        win = 100 * vencedores / len(da_hora) if da_hora else 0.0
        pregoes_c_trade = len(set(t["data"] for t in da_hora))
        liq_trade = liquido / len(da_hora) if da_hora else None
        liq_pregao = liquido / n_pregoes_total if n_pregoes_total else None
        linhas_liquido_pregao.append((h, liq_pregao))
        print(f"{h:>4}h {len(da_hora):>7} {pregoes_c_trade:>13} {br(win,1):>6}% "
              f"{br(liquido):>13} {br(liq_trade):>10} {br(liq_pregao):>11}")

    if linhas_liquido_pregao:
        melhor_h = max(linhas_liquido_pregao, key=lambda x: x[1])
        pior_h = min(linhas_liquido_pregao, key=lambda x: x[1])
        print(f"\nmelhor horario (R$/pregao): {melhor_h[0]}h ({br(melhor_h[1])}) | "
              f"pior horario: {pior_h[0]}h ({br(pior_h[1])})")


def _grade_dia_x_hora(trades: list) -> None:
    print(f"\n--- cruzamento DIA x HORA (n<30 trades = amostra pequena, marcado com *) ---")
    horas = sorted(set(t["hora"] for t in trades))
    for d in range(5):
        do_dia = [t for t in trades if t["dia_semana"] == d]
        if not do_dia:
            print(f"\n{DIAS_SEMANA[d]}: sem trades")
            continue
        print(f"\n{DIAS_SEMANA[d]} ({len(do_dia)} trades, "
              f"{len(set(t['data'] for t in do_dia))} pregoes distintos)")
        print(f"  {'hora':>5} {'trades':>7} {'win%':>7} {'liquido R$':>13} {'R$/trade':>10}")
        melhores_piores = []
        for h in horas:
            da_celula = [t for t in do_dia if t["hora"] == h]
            if not da_celula:
                continue
            liquido = sum(t["pnl"] for t in da_celula)
            vencedores = sum(1 for t in da_celula if t["pnl"] > 0)
            win = 100 * vencedores / len(da_celula)
            liq_trade = liquido / len(da_celula)
            marca = "*" if len(da_celula) < 30 else " "
            melhores_piores.append((h, liq_trade, len(da_celula)))
            print(f"  {h:>4}h {len(da_celula):>7} {br(win,1):>6}% "
                  f"{br(liquido):>13} {br(liq_trade):>10}{marca}")
        confiaveis = [(h, v) for h, v, n in melhores_piores if n >= 30]
        base = confiaveis if confiaveis else [(h, v) for h, v, n in melhores_piores]
        if base:
            melhor_h = max(base, key=lambda x: x[1])
            pior_h = min(base, key=lambda x: x[1])
            ressalva = "" if confiaveis else " (nenhuma celula com n>=30 -- so' amostra pequena)"
            print(f"  melhor: {melhor_h[0]}h ({br(melhor_h[1])}/trade) | "
                  f"pior: {pior_h[0]}h ({br(pior_h[1])}/trade){ressalva}")


def main() -> None:
    print(f"[wdo_win_padrao_dia_horario] {len(ROBOS)} robo(s), config de PRODUCAO, "
          f"capital COM FOLGA (ver docstring)\n", flush=True)
    with ProcessPoolExecutor(max_workers=len(ROBOS)) as ex:
        futuros = {ex.submit(_rodar, robo): robo for robo in ROBOS}
        for fut in as_completed(futuros):
            r = fut.result()
            robo, symbol = r["robo"], r["robo"]["symbol"]
            print("=" * 96)
            print(f"{robo['label']} ({symbol}) -- {r['n_bars']:,} barras M1, "
                  f"{len(r['sessoes'])} pregoes completos, capital R${br(robo['capital'],0)} "
                  f"[{r['dt']:.1f}s]", flush=True)
            print("=" * 96)
            print(r["tabela_txt"])
            if r["wiped_out"]:
                print("\n*** ZERADO durante o historico -- dias apos o zeramento NAO estao "
                      "representados nas tabelas abaixo. ***")
            if not r["trades"]:
                print("\nsem trades fechados -- nada para quebrar por dia/hora.")
                continue
            _tabela_dia_semana(r["sessoes"], r["trades"])
            _tabela_hora(r["sessoes"], r["trades"])
            _grade_dia_x_hora(r["trades"])
            print()


if __name__ == "__main__":
    main()
