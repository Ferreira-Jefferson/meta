"""WDO F1 (T2/S6): quanto vale posicionar a ordem-limite de SAIDA no FILL da
entrada, em vez de so' quando o preco TOCA o alvo -- IS+OOS, capital REAL.

POR QUE ESTA RODADA EXISTE
--------------------------
2026-09-09, primeiro dia do T2/S6 ao vivo com dinheiro real. Sete saidas por
alvo num pregao: UMA preencheu como ordem-limite, seis estouraram o prazo
(`exit_ttl_bars=60`) e sairam a MERCADO, cada uma pagando o tick que a saida
maker existia para nao pagar. O backtest da mesma geometria previa +R$36,00
no dia. O dia deu -R$14,00.

A tabela que calibrou `exit_ttl_bars=60` dizia 92,8% de preenchimento. O real
deu 14% (1/7). A tabela nao mentiu sobre o que mediu -- ela mediu num motor
que nao tem fila nenhuma do lado da saida: bastava o preco TOCAR o nivel e
haver volume na barra para a fatia preencher. No book de verdade, o preco ter
negociado no seu nivel significa que alguem negociou ali, quase sempre com
quem estava na FRENTE da fila. E' o mesmo otimismo que `queue_ahead_qty`
corrigiu do lado da ENTRADA em 2026-08-26 (PMAM3: 12 ordens reais, 0 fills,
contra 7 trades do gemeo em sombra no mesmo pregao) -- um mes depois, do
outro lado da operacao.

Duas coisas mudaram no motor para esta rodada poder existir
(`backtest/intraday/machine.py`, 2026-09-09):

  * `IntradayBacktestConfig.exit_queue_ahead_qty` -- Q_frente do lado da
    saida. Default 0,0 = o motor antigo, byte a byte.
  * `IntradayBacktestConfig.exit_arms_at_fill` -- a fatia entra no book no
    FILL DA ENTRADA, nao no primeiro toque do alvo.

O QUE A RODADA COMPARA, E O QUE ELA NAO CONSEGUE DECIDIR SOZINHA
----------------------------------------------------------------
As duas mecanicas NAO diferem por "geometria": o alvo e' o mesmo nivel, o
stop e' o mesmo. Elas diferem em DUAS coisas:

  1. QUANTA FILA voce pega. Armar no toque poe a ordem no fim da fila de um
     nivel que ACABOU de virar o topo do book. Armar no fill poe a ordem la'
     quando o alvo ainda e' o 2o/3o nivel -- na frente de todo mundo que so'
     vai chegar depois. A coleta de DOM do WDO@ em 2026-09-09 deu ordem de
     grandeza de ~400 contratos no 1o nivel e ~800 no 2o/3o. ORDEM DE
     GRANDEZA, nao constante.
  2. O ATRASO ESTRUTURAL DE 1 BARRA. Armando no toque, o motor (e a execucao
     real) nunca preenche na propria barra em que armou. Armando no fill, a
     fatia ja estava parada e a primeira barra que tocar pode preencher.

Q_frente e' INOBSERVAVEL no dado que este repo tem (tick MT5: bid/ask/last/
volume/flags; profundidade de book nao existe -- ver `market_data_intraday/
tick_storage.py`). Por isso a saida desta rodada e' uma GRADE de
sensibilidade, nunca uma linha unica: para cada mecanica, o liquido em varios
Q. Quem le escolhe o par (Q_no_toque, Q_no_fill) em que acredita e olha a
diferenca -- o script nao finge saber qual e'.

A linha `Q=0` de cada mecanica reproduz o motor SEM fila. Ela esta' na tabela
como REFERENCIA do quanto o numero antigo era otimista, nao como candidata.

O PRAZO TAMBEM ESTA' NA GRADE
-----------------------------
`exit_ttl_bars=60`, com `feed_kind="tick"`, sao 60 NEGOCIOS -- medidos ao
vivo em 2026-09-09 a 2,76 trades/s, ~22 segundos, nao um minuto. Com fila no
modelo, o prazo deixa de ser um detalhe: e' exatamente o tempo que a fatia
tem para a fila andar. Por isso ele entra como eixo (60 = producao hoje;
240 = ~88s), e nao como constante -- foi tambem a suspeita do dono ("o tempo
que ele desiste e vende a mercado e' muito curto").

COMO LER
--------
Antes do `liquido R$`, olhe `trades` e `pregoes_sem_trade`: com capital real
R$375 (piso EXATO de 1 contrato) um unico stop derruba o caixa abaixo do piso
de reabertura e o robo fica inerte em SILENCIO pelo resto da janela. Janela
assim esta' CENSURADA -- ela mede o portao de capital, nao a estrategia (item
6.15/6.16 de LICOES_DE_PRODUCAO.md). `saida_alvo` x `saida_prazo` e' a leitura
central desta rodada: e' a taxa de fill que o real mediu em 14%.

Janelas congeladas: IS 72 pregoes (2026-02-27..2026-06-12), OOS 51 pregoes.
Capital R$375 nas duas -- margem R$150 x buffer 2,0 x reserva 1,25, o que o
slot ao vivo tem de verdade.

Rodar so' um pedaco (a rodada inteira leva horas e um kill no fim nao pode
custar tudo):
    WDOF1_JANELAS=OOS WDOF1_WORKERS=2 python -u <este script>
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
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo (WDO@) -- margem R$150 x buffer 2,0 x reserva
#: 1,25. Nunca um capital nocional de calibracao (ordem do dono, 2026-09-08).
CAPITAL_REAL_BRL = 375.0

MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "3"))

JANELAS_PEDIDAS = tuple(
    j.strip().upper()
    for j in os.environ.get("WDOF1_JANELAS", "OOS,IS").split(",")
    if j.strip()
)

CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks", "profit_ticks", "stop_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "risco_pct_por_trade", "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
    # A saida FATIADA e' a razao de ser desta rodada -- sem ela nao ha fatia,
    # nao ha prazo e nao ha fila. Estava faltando na lista copiada do sweep de
    # deslize, onde o alvo era o NATIVO.
    "fatiar_saida_alvo",
)

EXTRAS = ("saida_alvo", "saida_prazo", "saida_stop", "fill%",
          "pregoes_sem_trade", "qtd_max", "zerou", "caixa_min")

#: `(rotulo, ttl_barras, arma_no_fill, q_frente)`. A ORDEM e' a da tabela
#: final: referencia primeiro, depois o par que responde a pergunta, depois a
#: sensibilidade.
#:
#: A grade e' ENXUTA de proposito. Uma celula custa ~30 min no OOS e ~42 min
#: no IS (0,29 ms/barra x 6,2 / 8,7 milhoes de barras, medido em 2026-09-09):
#: o produto cartesiano 2 prazos x 2 mecanicas x 4 Q daria 6,4 horas de
#: maquina para responder uma pergunta que 6 celulas respondem. O que sobrou
#: cobre exatamente os eixos que decidem, um de cada vez a partir da mesma
#: base:
#:
#:   * `Q=0` -- o motor SEM fila, que e' o backtest que vinha decidindo tudo
#:     ate hoje. Referencia do otimismo, nunca candidata.
#:   * `arma@toque` x `arma@fill` no MESMO Q e MESMO prazo -- isola a
#:     mecanica (chegar antes na fila, e o atraso estrutural de 1 barra).
#:   * `ttl60` x `ttl240` -- isola o prazo, que com fila no modelo deixou de
#:     ser detalhe: e' o tempo que a fatia tem para a fila andar.
#:   * `Q=800` -- sensibilidade. Se o veredito virar entre 400 e 800, ele
#:     depende de um numero que este repo NAO observa, e isso e' o resultado.
#:
#: Q=400 e' a ancora porque foi a ordem de grandeza do 1o nivel do WDO@ na
#: coleta de DOM de 2026-09-09 (~400 contratos; ~800 no 2o/3o).
CELULAS = (
    ("ref  ttl60  arma@toque Q=0",   60,  False, 0.0),
    ("     ttl60  arma@toque Q=400", 60,  False, 400.0),
    ("     ttl60  arma@fill  Q=400", 60,  True,  400.0),
    ("     ttl240 arma@toque Q=400", 240, False, 400.0),
    ("     ttl240 arma@fill  Q=400", 240, True,  400.0),
    ("sens ttl60  arma@fill  Q=800", 60,  True,  800.0),
)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    """Fatia OHLCV da janela pedida, cacheada por PROCESSO.

    O filtro vai para o LEITOR do parquet (`filters=`), nao para um
    `df[df["janela"] == ...]` depois de carregar tudo: sao 20,6 milhoes de
    linhas, e a coluna `janela` materializada como objeto Python passa de
    1 GB. Um processo morto por memoria no meio de uma batelada de horas
    custa a batelada inteira."""
    if janela not in _DF_CACHE:
        _DF_CACHE.clear()  # nunca segura duas janelas ao mesmo tempo
        df = pd.read_parquet(
            CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", janela)],
        )
        _DF_CACHE[janela] = df.sort_index()
        del df
    return _DF_CACHE[janela]


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(janela, rotulo, LinhaResultado,
    texto_pronto, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_do_processo(spec["janela"])

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    # O prazo e' EIXO desta rodada; producao hoje = 60.
    kwargs["exit_ttl_bars"] = int(spec["ttl"])
    strat = WdoGridReloadMaker(**kwargs)

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        # Producao ligou em 2026-09-09 -- a rodada tem de descrever o robo que
        # esta' no ar, nao um parente dele.
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        exit_queue_ahead_qty=spec["q_frente"],
        exit_arms_at_fill=spec["arma_no_fill"],
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    # Saida por alvo que preencheu COMO LIMITE x que estourou o prazo e foi a
    # mercado: as duas carimbam `TARGET` como motivo, e distinguir e' o ponto
    # inteiro desta rodada (o real mediu 1 de 7). `exit_detail` existe desde
    # 2026-09-09 exatamente para separar as duas -- e' tambem o que faz a
    # segunda pagar `slippage_ticks`, que ela nao pagava.
    por_prazo = sum(1 for t in trades if t.exit_detail == "target_timeout")
    por_alvo = contagem.get("target", 0) - por_prazo
    total_alvo = contagem.get("target", 0)
    fill_pct = (100.0 * por_alvo / total_alvo) if total_alvo else float("nan")

    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    qtd_max = max((t.quantity for t in trades), default=0)

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "saida_alvo": str(por_alvo),
        "saida_prazo": str(por_prazo),
        "saida_stop": str(contagem.get("stop", 0)),
        "fill%": num_br(fill_pct, 1),
        "pregoes_sem_trade": f"{len(dias_janela - dias_com_trade)}/{len(dias_janela)}",
        "qtd_max": str(qtd_max),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
        "caixa_min": num_br(caixa_min, 2),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['janela']}, {dt:6.1f}s] {linha(item, EXTRAS)}", flush=True)
    return (spec["janela"], spec["rotulo"], item, buf.getvalue(), dt)


def _specs(janela: str) -> list[dict]:
    return [
        {"janela": janela, "ttl": ttl, "arma_no_fill": arma,
         "q_frente": q, "rotulo": rotulo}
        for rotulo, ttl, arma, q in CELULAS
    ]


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_fila_saida] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt
    from strategy.daytrade.registry import get_daytrade_robot

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    print("[wdof1_fila_saida] kwargs de PRODUCAO "
          "(get_daytrade_robot('wdo_grid_reload_maker')):")
    for campo in CAMPOS_KWARGS:
        print(f"    {campo} = {getattr(robo, campo)!r}")
    print(f"    exit_ttl_bars (producao) = {robo.exit_ttl_bars!r}")
    print(f"    anchor_exits_at_fill     = {robo.anchor_exits_at_fill!r}")
    print()
    print("[wdof1_fila_saida] Q_frente da saida e' PARAMETRO, nunca fato: "
          "profundidade de book nao existe no tick MT5. Q=0 e' o motor SEM "
          "fila (referencia do otimismo antigo), nao candidata.")
    print(f"[wdof1_fila_saida] capital real R${CAPITAL_REAL_BRL:.2f}, "
          f"{len(CELULAS)} celulas por janela, janelas "
          f"{list(JANELAS_PEDIDAS)}, {MAX_WORKERS} processos "
          f"(~30 min/celula no OOS, ~42 no IS)\n", flush=True)

    resultados: dict = {}
    t0 = time.perf_counter()
    total = sum(len(_specs(j)) for j in JANELAS_PEDIDAS)
    concluidos = 0

    # UMA BATELADA POR JANELA: todos os processos de uma batelada leem a MESMA
    # fatia do parquet, entao o cache por processo serve para as celulas
    # seguintes dela em vez de ser jogado fora a cada tarefa.
    for janela in JANELAS_PEDIDAS:
        specs = _specs(janela)
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futuros = {pool.submit(_roda_uma, s): s for s in specs}
            for fut in as_completed(futuros):
                jan, rotulo, item, texto, _dt = fut.result()
                concluidos += 1
                # Cada unidade imprime a linha DELA assim que termina (regra
                # do repo): uma rodada de horas nunca fica muda, e um kill no
                # fim nao apaga o que ja rodou.
                print(f"({concluidos:2d}/{total}) {texto}", end="", flush=True)
                resultados[(jan, rotulo)] = item

    print(f"\n[wdof1_fila_saida] {concluidos} celulas em "
          f"{(time.perf_counter() - t0) / 60:.1f} min\n", flush=True)

    for janela in JANELAS_PEDIDAS:
        print(f"\n=== {janela} — T2/S6, capital R${CAPITAL_REAL_BRL:.0f} ===")
        print(cabecalho(EXTRAS))
        for spec in _specs(janela):
            item = resultados.get((janela, spec["rotulo"]))
            if item is not None:
                print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
