"""WDO F1 (T2/S16) re-medido COM o deslize do alvo nativo cobrado pelo motor,
IS/OOS, mais as compensacoes candidatas -- inclusive a que o dono propos.

## O que mudou no motor, e por que esta medicao existe

Ate' 2026-09-08 `IntradaySessionMachine._close_position` fechava a saida por
ALVO maker EXATAMENTE no nivel pedido, de graca (`target_fills_as_maker=True`
=> `exec_px = exit_ref_price`). Isso e' falso para este robo: o alvo dele nao
e' uma ordem-limite resting no book, e' o `tp` NATIVO amarrado no mesmo
request da entrada (`live/broker_mt5.py::place_pending`), e a corretora o
executa como GATILHO varrido a mercado.

Medido no extrato, populacao completa de operacao real deste robo (3 pregoes:
2026-08-28, 2026-09-04, 2026-09-08), reconstruida do historico de DEALS +
ORDENS do terminal -- n=11 saidas por TP nativo:

    deslize (ticks) |  0   -1   -2       contra: 10   a favor: 0   neutro: 1
    contagem        |  1    9    1
    media -1,000  mediana -1,0  desvio 0,447  min -2,0  max 0,0

R$55,00 de deslize; o bruto real das 11 foi R$40,00 contra R$95,00 se todas
tivessem pago o nivel pedido -- 57,9% do bruto teorico. Ver
`backtest.intraday.costs.DESLIZE_ALVO_NATIVO_TICKS` (a constante) e o item 4.8
de `LICOES_DE_PRODUCAO.md`.

Com `profit_ticks=2` (T2, producao) o alvo vale 1,0 ponto = R$10,00/contrato.
1 tick de deslize e' **metade** disso. Ou seja: todo numero ja medido deste
robo e' otimista EXATAMENTE no evento que decidiu quase todos os trades
reais, e "T2 da lucro" era uma afirmacao que a medicao nao sustentava.

## As variantes

Baselines:
  * `T2 s/ deslize`  -- o MOTOR ANTIGO. Nao e' candidato a nada: esta aqui
    so' para medir quanto valia a otimizacao que faltava no modelo.
  * `T2 desliz 1,0t` -- o baseline HONESTO. E' a geometria que roda em
    producao hoje, agora paga.

Compensacao proposta pelo DONO (2026-09-08, textual): "sabendo que ele
escorrega 1 ponto, poderiamos sempre colocar um ponto antes de entrada com
alvo e stop certo, para quando entrar tendo a escorregada ou nao ainda assim
ele entra no local esperado". Aplicada ao alvo, e' pedir 1 tick a MAIS para
que o preco EXECUTADO caia no nivel pretendido:
  * `T3 desliz 1,0t (DONO)` -- pede 3 ticks, recebe 2 = a geometria T2
    pretendida. E' a implementacao literal da ideia.
  * `T4 desliz 1,0t (DONO+1)` -- mesma ideia com 1 tick a mais de folga.

O que a ideia do dono CUSTA, e por isso ela precisa ser medida e nao so'
raciocinada: o gatilho sobe junto. T3 exige que o preco ande 3 ticks para
disparar, contra 2 do T2 -- entrega o mesmo lucro por vitoria, mas com menos
vitorias e mais tempo exposto ao stop. "T3 com deslize" NAO e' igual a "T2 sem
deslize"; so' o P&L final diz qual das duas perdas e' menor.

A parte da proposta do dono sobre a ENTRADA ("colocar um ponto antes de
entrada") NAO e' medida aqui, de proposito: nao existe amostra de deslize de
ENTRADA. As 11 medicoes sao todas de saida por TP, e a entrada deste robo e'
ordem-limite que preenche no nivel (o que o motor ja modela). Deslocar a
entrada para compensar um deslize que ninguem mediu seria inventar custo.

Minhas (do agente, nao do dono):
  * `T6 desliz 1,0t` -- DILUIR em vez de compensar: com alvo de 6 ticks o
    mesmo 1 tick de deslize vira 17% do bruto em vez de 50%. Testa se o
    problema e' o deslize ou o tamanho do alvo.
  * `T2 desliz 0,5t` / `T2 desliz 2,0t` -- SENSIBILIDADE. n=11 e' pouco (2
    pregoes efetivos, 1 contrato); o forte da amostra e' a direcionalidade
    (10 contra, 0 a favor), nao a magnitude. Se o veredito virar entre 0,5 e
    2,0 ticks, ele nao esta decidido por esta amostra.

T1 (`profit_ticks=1`) NAO entra -- nem como baseline, nem como referencia de
tabela. Ordem do dono, 2026-09-08: alvo de 1 tick e' menor que o deslize que
a corretora comete, entao e' uma geometria que o motor sabe simular e a
corretora nao sabe executar. Ver CLAUDE.md.

## Config

`get_daytrade_robot("wdo_grid_reload_maker")` -- o caminho REAL de
`scripts/run_live.py::build_intraday`, com `_KWARGS_PADRAO` (dimensionamento
dinamico por caixa: `margin_per_contract_brl=150`, `hard_cap_contratos=5`,
`risco_pct_por_trade=0.01`). Capital R$375,00, o minimo REAL do WDO@ (margem
R$150 x buffer 2,0 x reserva 1,25), nunca nocional.

Base: `data/raw_ticks/WDO_A_f1.parquet`, coluna `janela` ja rotulada
(IS: 72 pregoes, 2026-02-27..2026-06-12; OOS: 51 pregoes,
2026-06-15..2026-08-25). Split INTACTO -- nao se mexe ao reparar dado.

## Como LER esta tabela

Antes de tratar qualquer `liquido R$` como veredito, olhe `trades` e
`pregoes_sem_trade`: uma janela em que o robo PAROU esta censurada -- ela mede
a restricao que o parou, nao a estrategia (item 6.15 de
`LICOES_DE_PRODUCAO.md`). E o `retorno` de 4-5 digitos e' artefato de
composicao sobre um caixa minusculo, nao previsao: use valor absoluto por
pregao e contagem de trades.

## Extras

`desliz R$` -- soma de `IntradayTrade.slippage_total` das saidas por ALVO,
ou seja, quanto o deslize custou NESTA run (0 na linha do motor antigo).
`saida_alvo`/`saida_stop`/`saida_flatten`, `pregoes_sem_trade`, `qtd_max`,
`zerou`, `caixa_min`, `pior_janela_60s` -- mesmas definicoes de
`wdof1_producao_is_oos_2026_09_07.py`.

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), UMA
BATELADA POR JANELA -- cada processo carrega so' a fatia da janela corrente
(o parquet inteiro sao 2,3 GB em memoria; cachear IS+OOS em N processos
estoura a RAM da maquina). Cada tarefa imprime a linha DELA assim que
termina; as tabelas ordenadas vem no fim.

Uso: `python -u scripts/daytrade/wdof1_deslize_alvo_is_oos_2026_09_08.py`

## RESULTADO (2026-09-08) -- bateria de capital REAL, 14/14 celulas

Colunas abreviadas; `s/trd` = pregoes SEM trade nenhum (leia esta antes do
liquido -- item 6.15), `desl R$` = soma do deslize cobrado nas saidas por
alvo.

    IS (72 pregoes)              liquido R$   MaxDD R$ luc/DD   win%  trades  desl R$  s/trd  caixa_min
    T2/S16 s/ deslize            347.548,50   2.547,50 136,43  94,2%   19893     0,00   0/72     370,00
    T2/S16 desliz 0,5t           137.618,50   3.842,50  35,81  94,5%   19921  156.495   0/72     359,50
    T2/S16 desliz 1,0t (PROD)      -242,50      405,00  -0,60  93,3%     165   770,00  71/72     132,50
    T3/S16 desliz 1,0t (DONO)      -229,00      495,50  -0,46  88,0%     158   695,00  70/72     146,00
    T4/S16 desliz 1,0t             -244,00      442,00  -0,55  83,3%     108   445,00  70/72     131,00
    T6/S16 desliz 1,0t             -230,00      398,00  -0,58  72,5%      40   145,00  71/72     145,00
    T2/S16 desliz 2,0t             -293,00      298,00  -0,98   0,0%      76   730,00  71/72      82,00

    OOS (51 pregoes)             liquido R$   MaxDD R$ luc/DD   win%  trades  desl R$  s/trd  caixa_min
    T2/S16 s/ deslize            143.214,50   2.540,00  56,38  94,5%    9635     0,00   0/51     290,00
    T2/S16 desliz 0,5t            44.817,50   2.036,00  22,01  94,7%   10090   44.570   0/51     269,00
    T2/S16 desliz 1,0t (PROD)      -273,50      578,00  -0,47  94,1%     407  1.915,00  49/51     101,50
    T3/S16 desliz 1,0t (DONO)      -237,00    1.719,50  -0,14  89,2%    1784  7.955,00  37/51     121,00
    T4/S16 desliz 1,0t             -278,50      504,00  -0,55  82,2%     107   440,00  49/51      96,50
    T6/S16 desliz 1,0t             -279,00      319,50  -0,87  71,1%      38   135,00  50/51      96,00
    T2/S16 desliz 2,0t             -258,50      263,50  -0,98   5,4%      37   340,00  50/51     116,50

### Como ler

Toda linha que cobra >=1,0 tick esta CENSURADA nas duas janelas (37 a 71
pregoes sem trade, `caixa_min` abaixo da margem crua de R$150). O liquido
delas mede o portao de capital, nao edge. As unicas linhas nao censuradas
nas duas janelas sao as de 0 e 0,5 tick -- e sao fortemente positivas.

### O veredito

O win% NAO muda com o deslize (o gatilho continua no mesmo nivel, so' o
preco de saida muda), entao o teste valido e' o win% de n grande contra o
breakeven novo. Com stop de 16 ticks e corretagem de R$0,50:

    deslize   ganho/vitoria   breakeven   win% T2 (n=9.635)   E[R$]/trade
      0,0t        R$9,50        90,00%          94,5%            +4,27
      0,5t        R$7,00        92,43%          94,5%            +1,91
      0,905t      R$4,98        94,50%          94,5%             0,00   <- CRITICO
      1,0t        R$4,50        95,00%          94,5%            -0,45
      2,0t       -R$0,50       100,59%          94,5%            -5,18

**T2/S16 NAO TEM EDGE ao deslize medido de 1,0 tick.** O breakeven de 95,00%
fica FORA do IC95% do win% ([94,04% ; 94,96%]), acima dele (z = -2,15).

**A compensacao do dono (T3: pedir 3 ticks para receber 2) nao resgata.** Ela
devolve o payoff de R$9,50, mas o gatilho anda 1 tick junto e o win% cai
para 89,9% (n=5.076) contra breakeven de 90,00% -- o breakeven cai DENTRO do
IC ([89,07% ; 90,73%]). Sai de "negativo mensuravel" para "cara-ou-coroa em
cima do zero" (E = -R$0,09/trade). E' a menos ruim das quatro geometrias com
deslize cobrado (melhor lucro/DD, 4,4x mais trades antes de travar), e move
o ponto critico de 0,905 para 0,979 tick -- melhora real e pequena. Afastar
mais (T4, T6) piora monotonicamente: o win% cai mais rapido que o payoff
sobe.

### O que a rodada mudou de LUGAR na incerteza

O win% esta medido com n de 5 digitos e IC de +-0,5pp. O deslize tem n=11,
media 1,000 tick, desvio 0,447, IC95% (t, gl=10) = [0,700 ; 1,300] -- e esse
intervalo ATRAVESSA o critico de 0,905. Ou seja: mais backtest nao move mais
esta resposta. A medicao que decide e' acumular saidas por TP nativo no
extrato da corretora (~40-50 levariam o IC do deslize para ~+-0,14 tick).

### Duas verificacoes de que o motor cobra o que diz cobrar

1. `desl R$ / saidas por alvo` da EXATO R$5,00 por saida a 1,0t e R$10,00 a
   2,0t em toda celula de 1 contrato (1 tick = 0,5 pt x R$10/pt), e escala
   com a quantidade onde o dimensionamento dinamico destrava contratos.
2. A 2,0t o win% desaba para 0,0% (IS) e 5,4% (OOS) -- com alvo de 2 ticks e
   deslize de 2 ticks o bruto por vitoria e' exatamente R$0,00 menos R$0,50
   de corretagem, entao TEM de ser ~zero. Os 5,4% do OOS sao saidas em GAP,
   onde `_exit_fill_price` da referencia melhor que o nivel antes de o
   deslize entrar -- o mecanismo compoe certo.

### A bateria de R$5.000 NAO rodou

O processo foi MORTO pelo sistema operacional (exit 255, sem traceback e sem
`MemoryError`) ao comecar a 2a bateria, com a maquina a 81% de RAM. As 14
celulas acima sobreviveram porque cada tarefa imprime a linha DELA assim que
termina. Para rodar so' o que falta, com menos pressao de memoria:

    WDOF1_BATERIAS=folga WDOF1_WORKERS=2 python -u <este script>

Ela nao muda o veredito (que sai do win% x breakeven, e o win% de T2/T3 ja
esta medido sem censura nas linhas de 0/0,5 tick) -- serve para ler T4 e T6,
que a R$375 morrem de caixa antes de mostrar geometria.
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
#: 1,25. Nunca um capital nocional de calibracao.
CAPITAL_REAL_BRL = 375.0

#: Quantos processos rodam ao mesmo tempo. BAIXO de proposito: cada um
#: carrega a fatia da janela em memoria (IS ~700 MB), e o gargalo aqui e' RAM,
#: nao CPU.
MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "4"))

#: Quais BATERIAS de capital rodar nesta invocacao -- `"real"`, `"folga"`, ou
#: as duas (default). Existe porque a rodada de 2026-09-08 foi MORTA pelo
#: sistema operacional (exit 255, sem traceback e sem `MemoryError`) ao
#: comecar a 2a bateria, com a maquina a 81% de RAM: 4 processos segurando
#: ~700 MB da fatia IS cada, mais duas rodadas da suite de testes em
#: paralelo. As 14 celulas da bateria REAL sobreviveram porque cada tarefa
#: imprime a linha DELA assim que termina (regra do repo) -- nada se perdeu
#: do que ja tinha rodado.
#:
#: A licao que virou codigo: uma rodada de horas tem de poder ser retomada
#: pelo pedaco que faltou, senao um kill no fim custa tudo de novo. Rode
#: `WDOF1_BATERIAS=folga WDOF1_WORKERS=2 python -u <este script>` para so' a
#: parte que falta, com menos pressao de memoria.
BATERIAS_PEDIDAS = tuple(
    b.strip().lower()
    for b in os.environ.get("WDOF1_BATERIAS", "real,folga").split(",")
    if b.strip()
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
)

EXTRAS = ("desliz R$", "saida_alvo", "saida_stop", "saida_flatten",
          "pregoes_sem_trade", "pior_janela_60s", "qtd_max", "zerou", "caixa_min")

#: Capital COM FOLGA, para separar GEOMETRIA de CENSURA por capital. Nao
#: substitui o capital real: e' uma segunda bateria, ao lado dele.
#:
#: Por que precisa existir: com R$375 (o piso EXATO de 1 contrato) um unico
#: stop de R$80 derruba o caixa abaixo do piso de reabertura e o robo fica
#: inerte pelo resto da janela -- em silencio. Medido em 2026-09-08 (item
#: 6.16 de LICOES_DE_PRODUCAO.md): T4/S16 fez 51 trades em 72 pregoes do IS
#: (71 sem trade nenhum) e o caixa minimo bateu R$124,50, ABAIXO da margem
#: crua de R$150. Aquilo nao mede a geometria T4 -- mede o portao de capital.
#: Afastar o alvo, que e' exatamente o que a compensacao do dono faz, reduz a
#: taxa de acerto por construcao e portanto empurra o robo PARA esse
#: penhasco. Comparar T2 contra T3/T4/T6 so' no piso confundiria "a
#: compensacao nao funciona" com "a compensacao trava o caixa antes de
#: mostrar se funciona".
#:
#: R$5.000 e' o nivel ja MEDIDO neste repo como o primeiro em que o WDO F1
#: sobrevive ao historico inteiro (ver `strategy.daytrade.registry`, nota de
#: 2026-08-29, e `wdof1_stress_capital_real_historico_completo.py`).
CAPITAL_FOLGA_BRL = 5_000.0

#: `(rotulo, profit_ticks, deslize_ticks, autor)`. A ORDEM e' a da tabela
#: final -- baselines primeiro, depois as compensacoes, depois a
#: sensibilidade. `profit_ticks=None` = default de producao (2).
VARIANTES = (
    ("T2/S16 s/ deslize (motor antigo)", None, 0.0,  "referencia"),
    ("T2/S16 desliz 1,0t (BASELINE)",    None, 1.0,  "producao"),
    ("T3/S16 desliz 1,0t (DONO)",        3,    1.0,  "dono"),
    ("T4/S16 desliz 1,0t (DONO+1)",      4,    1.0,  "dono"),
    ("T6/S16 desliz 1,0t (diluir)",      6,    1.0,  "agente"),
    ("T2/S16 desliz 0,5t (sensib.)",     None, 0.5,  "agente"),
    ("T2/S16 desliz 2,0t (sensib.)",     None, 2.0,  "agente"),
)

#: Subconjunto rodado TAMBEM no capital com folga -- so' o que responde
#: "a compensacao do dono vale a pena quando o caixa nao e' a restricao".
#: As duas linhas de sensibilidade ficam de fora: elas ja respondem no piso,
#: que e' onde o robo de verdade opera.
VARIANTES_FOLGA = tuple(v for v in VARIANTES if "sensib." not in v[0])

#: Fatia da janela lida 1x por PROCESSO. Guarda UMA janela so' -- ver
#: "Paralelismo" na docstring do modulo.
_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    """Fatia OHLCV da janela pedida, cacheada por PROCESSO.

    O filtro vai para o LEITOR do parquet (`filters=`), nao para um
    `df[df["janela"] == ...]` depois de carregar tudo: o arquivo inteiro sao
    20,6 milhoes de linhas e a coluna `janela` sozinha, materializada como
    objeto Python, passa de 1 GB. Com 4 processos lendo ao mesmo tempo isso
    e' o que estoura a RAM -- e um processo morto por memoria no meio de uma
    batelada de 2 horas custa a batelada inteira."""
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


def _pior_janela_60s(envios_ts: list) -> int:
    """Pior contagem, numa janela ROLANTE de 60s, de `EnterLimit` emitidas --
    mesma grandeza que `live.intraday_runtime.MAX_ENVIOS_POR_MINUTO` (30)
    limita ao vivo."""
    if not envios_ts:
        return 0
    serie = pd.Series(1, index=pd.DatetimeIndex(sorted(envios_ts)))
    return int(serie.rolling("60s").sum().max())


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(janela, rotulo, LinhaResultado,
    texto_pronto, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from core.models import IntradayExitReason
    from strategy.daytrade.base import EnterLimit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    class _ComContadorEnvios(WdoGridReloadMaker):
        """Mesma classe de producao -- so' registra o timestamp de toda
        `EnterLimit` emitida por `on_bar`. Nao muda comportamento nenhum."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.envios_ts: list[pd.Timestamp] = []

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            actions = super().on_bar(ts, bar, positions, session_pnl_brl)
            for action in actions:
                if isinstance(action, EnterLimit):
                    self.envios_ts.append(pd.Timestamp(ts))
            return actions

    bars = _bars_do_processo(spec["janela"])

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    if spec["profit_ticks"] is not None:
        kwargs["profit_ticks"] = spec["profit_ticks"]
    strat = _ComContadorEnvios(**kwargs)

    capital = float(spec["capital"])
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        # EXPLICITO em toda variante -- inclusive na que reproduz o motor
        # antigo (0,0). Deixar no default automatico aqui esconderia a
        # premissa que ESTA rodada existe para comparar.
        target_slippage_ticks=spec["deslize_ticks"],
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    qtd_max = max((t.quantity for t in trades), default=0)
    desliz_brl = sum(t.slippage_total for t in trades
                     if t.exit_reason == IntradayExitReason.TARGET)

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "desliz R$": num_br(desliz_brl, 2),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "saida_flatten": str(contagem.get("forced_flatten", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "pior_janela_60s": str(_pior_janela_60s(strat.envios_ts)),
        "qtd_max": str(qtd_max),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
        "caixa_min": num_br(caixa_min, 2),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['bateria']} {spec['janela']}, {dt:6.1f}s] "
              f"{linha(item, EXTRAS)}", flush=True)
    return (spec["bateria"], spec["janela"], spec["rotulo"], item,
            buf.getvalue(), dt)


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_deslize_alvo] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.costs import DESLIZE_ALVO_NATIVO_TICKS
    from backtest.intraday.report import cabecalho, linha as linha_fmt
    from strategy.daytrade.registry import get_daytrade_robot

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    print("[wdof1_deslize_alvo] kwargs de PRODUCAO "
          "(get_daytrade_robot('wdo_grid_reload_maker')):")
    for campo in CAMPOS_KWARGS:
        print(f"    {campo} = {getattr(robo, campo)!r}")
    print(f"\n[wdof1_deslize_alvo] deslize medido no extrato: "
          f"{DESLIZE_ALVO_NATIVO_TICKS} tick (n=11, 10 contra / 0 a favor / 1 "
          f"neutro; media -1,000, desvio 0,447) -- ver "
          f"backtest.intraday.costs.DESLIZE_ALVO_NATIVO_TICKS")
    print(f"[wdof1_deslize_alvo] capital real R${CAPITAL_REAL_BRL:.2f} "
          f"({len(VARIANTES)} variantes) + capital com folga "
          f"R${CAPITAL_FOLGA_BRL:.2f} ({len(VARIANTES_FOLGA)} variantes), "
          f"x 2 janelas, {MAX_WORKERS} processos por batelada\n", flush=True)

    todas = (
        ("real", f"R${CAPITAL_REAL_BRL:.0f}", CAPITAL_REAL_BRL, VARIANTES),
        ("folga", f"R${CAPITAL_FOLGA_BRL:.0f}", CAPITAL_FOLGA_BRL, VARIANTES_FOLGA),
    )
    desconhecidas = set(BATERIAS_PEDIDAS) - {chave for chave, *_ in todas}
    if desconhecidas:
        raise SystemExit(
            f"WDOF1_BATERIAS desconhecida(s): {sorted(desconhecidas)} -- "
            f"use 'real', 'folga' ou 'real,folga'"
        )
    baterias = [(rotulo, cap, vs) for chave, rotulo, cap, vs in todas
                if chave in BATERIAS_PEDIDAS]
    if not baterias:
        raise SystemExit("WDOF1_BATERIAS vazia -- nada a rodar")
    resultados: dict = {}
    t0 = time.perf_counter()
    total = sum(len(vs) * 2 for _n, _c, vs in baterias)
    concluidos = 0

    # UMA BATELADA POR (capital, janela): todos os processos de uma batelada
    # seguram a MESMA fatia. Misturar as duas janelas faria cada processo
    # carregar as duas ao longo da fila (2,3 GB de parquet), que e' o que
    # estoura a RAM desta maquina.
    for nome_bat, capital, variantes in baterias:
        for janela in ("IS", "OOS"):
            specs = [dict(bateria=nome_bat, capital=capital, janela=janela,
                          rotulo=rotulo, profit_ticks=pt,
                          deslize_ticks=dt_ticks, autor=autor)
                     for rotulo, pt, dt_ticks, autor in variantes]
            n_workers = max(1, min(len(specs), MAX_WORKERS))
            print(f"--- batelada {nome_bat} / {janela} ({len(specs)} tarefas, "
                  f"{n_workers} processos) ---", flush=True)
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                futures = {pool.submit(_roda_uma, spec): spec["rotulo"]
                           for spec in specs}
                for future in as_completed(futures):
                    bat, jan, rotulo, item, texto, _dt = future.result()
                    resultados[(bat, jan, rotulo)] = item
                    concluidos += 1
                    print(f"[{concluidos}/{total}] {texto}", end="", flush=True)

    print(f"\n[wdof1_deslize_alvo] motor: {time.perf_counter() - t0:.1f}s\n")

    for nome_bat, capital, variantes in baterias:
        for janela in ("IS", "OOS"):
            print(f"\n=== tabela {janela} -- capital {nome_bat} ===")
            print(cabecalho(EXTRAS))
            for rotulo, _pt, _dt, _autor in variantes:
                item = resultados.get((nome_bat, janela, rotulo))
                if item is not None:
                    print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
