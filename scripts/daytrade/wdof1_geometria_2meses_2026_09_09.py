"""WDO F1: qual geometria (alvo x stop x prazo) tem expectativa POSITIVA com a
fila da saida no modelo -- baterias de ~2 meses, capital REAL R$375.

POR QUE ESTA RODADA EXISTE
--------------------------
2026-09-09, dia real completo do T2/S6 (34 operacoes depois do ajuste das
14:30): bruto -R$85,00, liquido -R$102,00, -R$3,00 por operacao. Das 34
saidas, 27 sairam por prazo (a mercado, 0/+-1 tick) e so' 9 pegaram o alvo
inteiro de 2 ticks. Isso confirma NA PRATICA o que a medicao com fila do
mesmo dia disse: o T2/S6 nao tem expectativa positiva.

A pergunta do dono passa a ser outra: existe alguma geometria que tenha?
Especificamente (1) T3/S6 e (2) aumentar o stop.

O QUE MUDA EM RELACAO A TODA MEDICAO ANTERIOR DE GEOMETRIA
-----------------------------------------------------------
Esta e' a primeira varredura de geometria rodada com o motor que:

  * modela FILA do lado da saida (`exit_queue_ahead_qty`) -- antes bastava o
    preco tocar o nivel e haver volume na barra para a fatia preencher;
  * cobra `slippage_ticks` na fatia que estoura o prazo e sai a MERCADO
    (`IntradayTrade.exit_detail == "target_timeout"`) -- antes essa saida era
    precificada como maker, de graca, e ela e' a que mais acontece de verdade
    (27 de 34 hoje).

Qualquer numero de geometria medido antes de 2026-09-09 esta' viciado nesses
dois eixos e NAO e' comparavel com as linhas desta tabela.

METODO
------
Busca nas DUAS metades do IS (J1 e J2, ~2 meses cada). Uma geometria so' vale
alguma coisa se aparecer nas duas -- uma metade sozinha e' um sorteio sobre
quais foram as primeiras operacoes, ainda mais com capital no piso. O OOS
(J3) fica INTOCADO nesta rodada, para validar depois so' o que sobreviver.

COMO LER (nao pule)
-------------------
1. `trades` e `pregoes_sem_trade` ANTES de `liquido R$`. Com R$375 (piso
   exato de 1 contrato) uma sequencia de stops derruba o caixa abaixo da
   margem crua de R$150 e o robo fica inerte em SILENCIO. Janela assim esta'
   CENSURADA: mede o portao de capital, nao a geometria.
2. Em janela censurada quem informa e' `R$/trade` e `win%` contra o
   `breakeven` da coluna -- os dois sao invariantes ao portao de capital.
3. `breakeven` = perda/(ganho+perda), com ganho = alvo*R$5 - R$0,50 e perda =
   (stop+1)*R$5 + R$0,50 (o +1 tick e' o deslize do stop, medido em 5 de 5).
4. `fill%` = quantas saidas por alvo preencheram COMO LIMITE, contra as que
   estouraram o prazo e sairam a mercado. O real de 2026-09-09 deu 25%.

T1 (`profit_ticks=1`) NAO entra -- ordem do dono, 2026-09-08: e' geometria que
o motor sabe simular e a corretora nao sabe executar.

Rodar so' uma bateria:
    WDOF1_BLOCOS=J1 WDOF1_WORKERS=9 python -u <este script>
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
#: Base de barras-tick. O default e' a canonica (IS+OOS). `WDOF1_CACHE`
#: aponta para outra -- foi como o pregao de 2026-09-09 entrou na conta antes
#: de existir na canonica, para conferir o motor contra o dia REAL.
CACHE = Path(os.environ.get(
    "WDOF1_CACHE", str(RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet")))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
CORRETAGEM_RT = 0.50
VALOR_TICK = 5.0

MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "9"))

#: Blocos de ~2 meses. J1 e J2 sao as duas metades do IS (busca). J3 e' o OOS
#: inteiro e fica FORA por padrao -- so' se roda nele o que sobreviver as duas
#: metades, senao o OOS vira mais um IS.
BLOCOS = {
    "J1": ("2026-02-27", "2026-04-24"),
    "J2": ("2026-04-27", "2026-06-12"),
    "J3": ("2026-06-15", "2026-08-25"),
    # As janelas CONGELADAS inteiras, para o veredito IS/OOS de uma
    # geometria ja' escolhida -- J1/J2 sao as metades do IS, usadas para
    # BUSCAR. Quem busca em J1/J2 e valida em OOS nao gastou o OOS.
    "IS": ("2026-02-27", "2026-06-12"),
    "OOS": ("2026-06-15", "2026-08-25"),
    # Um pregao so'. Serve para AFERIR o motor contra o extrato, nao para
    # decidir geometria. 2026-09-10 e' o primeiro pregao real SEM PRAZO --
    # ordem do dono nesse dia: e' a UNICA referencia a usar, porque
    # 2026-09-09 rodou com prazo e a fila de la' saiu de 68% de censura.
    "HOJE": ("2026-09-10", "2026-09-10"),
}
BLOCOS_PEDIDOS = tuple(
    b.strip().upper()
    for b in os.environ.get("WDOF1_BLOCOS", "J1,J2").split(",")
    if b.strip()
)

#: Fila a frente da fatia de saida. 400 e' a mesma ancora da medicao de
#: 2026-09-09 (coleta de DOM do WDO@: ~338 no 1o nivel, ~596 no 2o). E'
#: PARAMETRO, nunca fato -- profundidade de book nao existe no tick MT5.
#: `WDOF1_QS` aceita LISTA: Q vira eixo da grade em vez de constante. Medido
#: nas 34 ordens-limite de saida REAIS de 2026-09-09 (`history_orders_get` +
#: `copy_ticks_range`, volume negociado NO NIVEL entre postar e preencher):
#: das que esperaram e preencheram (n=8), mediana 374, media 421, p75 598,
#: max 806. As que esperaram e foram canceladas (n=17) tiveram mediana 20 --
#: elas nao perderam para uma fila grande, e' que quase nada negociou naquele
#: preco. Q=400 era chute ate' esta medicao; agora tem apoio.
QS_FRENTE = tuple(float(x) for x in
                  os.environ.get("WDOF1_QS", os.environ.get("WDOF1_Q", "400")).split(","))

#: Fila do lado da ENTRADA (`queue_ahead_qty`). Existe no motor desde
#: 2026-08-26 e NUNCA foi setada em lugar nenhum do repo -- ficava no default
#: 0,0, isto e', toda ordem-limite de entrada enchia no PRIMEIRO toque do
#: nivel. Medida em 2026-09-09 pelo mesmo Kaplan-Meier da saida, nas 67
#: ordens-limite de entrada REAIS que esperaram (30 preencheram, 37
#: censuradas): MEDIANA 438, quartil 1 194.
Q_ENTRADA = float(os.environ.get("WDOF1_QENTRADA", "0"))

ALVOS = tuple(int(x) for x in os.environ.get("WDOF1_ALVOS", "2,3,4,6").split(","))
STOPS = tuple(int(x) for x in os.environ.get("WDOF1_STOPS", "6,10,16").split(","))

#: Prazo da fatia de saida, em barras (= negocios, com `feed_kind="tick"`).
#: 60 = producao hoje (~22s a 2,76 trd/s); 240 = ~88s.
#:
#: `0` e' o caso SEM PRAZO, pedido do dono em 2026-09-09: a ordem-limite fica
#: parada no livro e a posicao so' sai quando o mercado PAGA o alvo -- nunca
#: a mercado por impaciencia. Nao e' "sem saida": o stop continua valendo e o
#: motor achata tudo no fim do pregao (`session_end_time`, machine.py:1478),
#: entao as saidas passam a ser so' tres: alvo preenchido como limite, stop,
#: ou fim de pregao. E' implementado como um prazo grande o bastante para
#: nunca estourar (o motor exige `exit_ttl_bars` declarado para fatiar --
#: `machine.py:2024`), nao como `None`.
PRAZO_SEM_LIMITE = 10 ** 9
PRAZOS = tuple(int(x) for x in os.environ.get("WDOF1_PRAZOS", "60,240").split(","))

CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "risco_pct_por_trade", "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
    "fatiar_saida_alvo",
)

EXTRAS = ("R$/trade", "breakeven", "saida_alvo", "saida_prazo", "saida_stop",
          "saida_outras", "fill%", "pregoes_sem_trade", "caixa_min", "zerou")

_DF_CACHE: dict[str, pd.DataFrame] = {}


def breakeven_pct(alvo: int, stop: int) -> float:
    ganho = alvo * VALOR_TICK - CORRETAGEM_RT
    perda = (stop + 1) * VALOR_TICK + CORRETAGEM_RT
    return 100.0 * perda / (ganho + perda)


def _bars_do_processo(bloco: str) -> pd.DataFrame:
    """Fatia OHLCV do bloco, cacheada por PROCESSO. O filtro vai para o LEITOR
    do parquet: sao 20,6 milhoes de linhas e carregar tudo estoura memoria com
    9 processos."""
    if bloco not in _DF_CACHE:
        _DF_CACHE.clear()
        ini, fim = BLOCOS[bloco]
        df = pd.read_parquet(
            CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("dia", ">=", pd.Timestamp(ini).date()),
                     ("dia", "<=", pd.Timestamp(fim).date())],
        )
        _DF_CACHE[bloco] = df.sort_index()
        del df
    return _DF_CACHE[bloco]


def _roda_uma(spec: dict):
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_do_processo(spec["bloco"])

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo, campo) for campo in CAMPOS_KWARGS}
    kwargs["profit_ticks"] = int(spec["alvo"])
    kwargs["stop_ticks"] = int(spec["stop"])
    kwargs["exit_ttl_bars"] = (PRAZO_SEM_LIMITE if int(spec["prazo"]) == 0
                               else int(spec["prazo"]))
    strat = WdoGridReloadMaker(**kwargs)

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=Q_ENTRADA,
        exit_queue_ahead_qty=spec["q"],
        exit_arms_at_fill=False,          # producao arma no TOQUE
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    n = len(trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    por_prazo = sum(1 for t in trades if t.exit_detail == "target_timeout")
    total_alvo = contagem.get("target", 0)
    por_alvo = total_alvo - por_prazo
    fill_pct = (100.0 * por_alvo / total_alvo) if total_alvo else float("nan")

    liquido = sum(t.pnl_brl for t in trades)
    dias_bloco = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "R$/trade": num_br(liquido / n, 3) if n else "-",
        "breakeven": num_br(breakeven_pct(spec["alvo"], spec["stop"]), 2),
        "saida_alvo": str(por_alvo),
        "saida_prazo": str(por_prazo),
        "saida_stop": str(contagem.get("stop", 0)),
        # Sem prazo, o que nao preenche nem bate stop sai no achatamento do
        # fim do pregao -- e essa coluna deixa de ser detalhe.
        "saida_outras": str(n - total_alvo - contagem.get("stop", 0)),
        "fill%": num_br(fill_pct, 1),
        "pregoes_sem_trade": f"{len(dias_bloco - dias_com_trade)}/{len(dias_bloco)}",
        "caixa_min": num_br(caixa_min, 2),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['bloco']}, {dt:6.1f}s] {linha(item, EXTRAS)}", flush=True)
    return (spec["bloco"], spec["rotulo"], item, buf.getvalue())


def _specs(bloco: str) -> list[dict]:
    return [
        {"bloco": bloco, "alvo": a, "stop": s, "prazo": p, "q": q,
         "rotulo": f"T{a}/S{s} " + ("ttlINF" if p == 0 else f"ttl{p}")
                   + f" Q{q:.0f}"}
        for q in QS_FRENTE for p in PRAZOS for a in ALVOS for s in STOPS
    ]


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}")
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    total = sum(len(_specs(b)) for b in BLOCOS_PEDIDOS)
    print(f"[geometria] capital real R${CAPITAL_REAL_BRL:.2f}, Q_frente="
          f"{QS_FRENTE}, alvos {ALVOS}, stops {STOPS}, prazos {PRAZOS}")
    print(f"[geometria] base {CACHE.name}, Q_entrada={Q_ENTRADA:.0f}")
    print(f"[geometria] blocos {list(BLOCOS_PEDIDOS)}")
    print(f"[geometria] {total} celulas, {MAX_WORKERS} processos\n", flush=True)

    resultados: dict = {}
    t0 = time.perf_counter()
    concluidos = 0
    for bloco in BLOCOS_PEDIDOS:
        specs = _specs(bloco)
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futuros = {pool.submit(_roda_uma, s): s for s in specs}
            for fut in as_completed(futuros):
                bl, rotulo, item, texto = fut.result()
                concluidos += 1
                print(f"({concluidos:2d}/{total}) {texto}", end="", flush=True)
                resultados[(bl, rotulo)] = item

    print(f"\n[geometria] {concluidos} celulas em "
          f"{(time.perf_counter() - t0) / 60:.1f} min\n", flush=True)

    for bloco in BLOCOS_PEDIDOS:
        ini, fim = BLOCOS[bloco]
        print(f"\n=== {bloco} ({ini}..{fim}) — capital "
              f"R${CAPITAL_REAL_BRL:.0f} ===")
        print(cabecalho(EXTRAS))
        for spec in _specs(bloco):
            item = resultados.get((bloco, spec["rotulo"]))
            if item is not None:
                print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
