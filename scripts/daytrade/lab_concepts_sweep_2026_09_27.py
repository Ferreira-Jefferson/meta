"""Varredura de PRIMEIRO PASSE sobre o catálogo de conceitos WDO (brainstorm
de 2026-09-27, ~909 conceitos catalogados, subconjunto escolhido pelo dono:
"Indicadores Técnicos" + "Price Action e Padrões", 189 conceitos) —
implementados um a um em `strategy.daytrade.lab.lab_concepts` (um arquivo por
conceito, `IntradayStrategy`, desenho de execução FECHADO: `EnterLimit`,
nunca `Enter`/`tp` nativo, ver CLAUDE.md).

## NÃO RE-RODÁVEL desde 2026-09-27 (registro histórico)

`strategy/daytrade/lab/lab_concepts/` (os 189 arquivos que este script
descobria por introspecção) foi APAGADO por decisão do dono depois da
validação IS/OOS (`lab_concepts_validacao_5_candidatos_2026_09_27.py`):
apenas 5 dos 189 passaram neste filtro grosso, e só 1 deles
(`MicroTopoFundoDuploM1`, promovido para `strategy/daytrade/lab/
micro_topo_fundo_duplo_m1.py`) sobreviveu à validação de verdade — "guardar
apenas o MicroTopoFundoDuploM1". Rodar este script agora falha com
`SystemExit` ("nenhuma estrategia encontrada"). Ele fica como registro do
MÉTODO usado (filtro grosso antes de validação cara), não como ferramenta
viva — o resultado que ele produziu está congelado no output salvo em
`lab_concepts_sweep_2026_09_27_resultado.csv` e no resumo da conversa que o
gerou.

## O que este script fazia (histórico)

Um FILTRO GROSSO, não uma validação. Roda cada uma das ~189 estratégias UMA
vez, com UM conjunto de parâmetros "razoável" (escolhido por quem implementou
o conceito, sem sweep de hiperparâmetro), no mesmo recorte de histórico e no
mesmo capital real (R$375, mínimo do WDO@ com reserva de segurança —
`strategy.daytrade.base.contracts_from_capital_com_reserva`), e imprime a
TABELA PADRÃO (`backtest/intraday/report.py`) para cada uma, streamando cada
linha assim que fica pronta (nunca espera o pool inteiro). No fim, separa as
que teriam sobrevivido a um corte ingênuo de "líquido > 0 com amostra
mínima" — **isso não é veredito** (nenhuma tem IS/OOS, nenhuma tem IC95%
contra o breakeven empírico, nenhuma foi calibrada por fila real via
`fidelidade.py` além do que `config_for` já aplica por padrão para o WDO@).
É o corte que decide quais das 189 merecem uma segunda olhada — o resto,
sem dado forte o bastante nem para essa pergunta, não precisa de mais tempo
de máquina agora.

## Janela

3 meses mais recentes de M1 salvo do WDO@ (mesmo recorte de
`wdo_cor_volume_reversao_2026_09_04.py`) — amostra pequena de propósito
(múltiplos meses x 189 estratégias em loop Python bar-a-bar não cabe no
mesmo orçamento de tempo de uma rodada só; ver LICOES_DE_PRODUCAO.md,
"teste pequeno valida hipótese primeiro"). Sobreviventes deste filtro pedem
depois uma rodada própria com janela IS/OOS completa antes de qualquer
promoção.

## Descoberta das estratégias

Por introspecção de módulo (`pkgutil.iter_modules` sobre o pacote
`lab_concepts`), não por um registro central mantido à mão — 189 entradas
digitadas duas vezes (aqui e em cada arquivo) é exatamente o tipo de
divergência que este projeto evita (AGENTS.md). Cada módulo `cNNN_slug.py`
expõe UMA classe `IntradayStrategy` definida NELE PRÓPRIO (`cls.__module__
== module.__name__` filtra qualquer import de classe-base auxiliar).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`),
`redirect_stdout` por tarefa, `flush=True`, streaming — mesma disciplina de
`gremah_defesa_corte_sweep_2026_09_03.py`. Uma estratégia com bug (erro de
implementação num conceito específico, esperado numa leva de 189 arquivos
escritos em lote) é capturada e reportada como FALHA na própria linha, sem
derrubar o restante da varredura.

Uso: `python -u scripts/daytrade/lab_concepts_sweep_2026_09_27.py`
"""
from __future__ import annotations

import contextlib
import importlib
import io
import pkgutil
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import IntradayStrategy  # noqa: E402
import strategy.daytrade.lab.lab_concepts as lab_concepts  # noqa: E402

SYMBOL = "WDO@"
ECONOMIA_WDO = (0.01, 0.001)  # (trade_tick_value, trade_tick_size) crus do MT5 -- config_for reescala
MARGEM_WDO_BRL = 150.0
CAPITAL_TESTE_BRL = 375.0  # minimo real COM reserva de seguranca -- CLAUDE.md, "capital nunca arbitrario"
MIN_BARRAS_POR_PREGAO = 400
MIN_TRADES_PARA_FILTRO = 10  # abaixo disso, "lucrativo" e' so' sorte de amostra pequena


@dataclass(frozen=True)
class _Resultado:
    nome: str
    ok: bool
    erro: str = ""
    liquido_brl: float = 0.0
    trades: int = 0
    pregoes: int = 0
    win_rate_pct: float = 0.0
    linha_tabela: str = ""


def _descobrir_estrategias() -> list[tuple[str, str]]:
    """`[(modulo_completo, nome_da_classe), ...]`, ordenado por nome de modulo
    (== ordem cNNN, determinístico entre rodadas)."""
    achados: list[tuple[str, str]] = []
    for info in pkgutil.iter_modules(lab_concepts.__path__, prefix=lab_concepts.__name__ + "."):
        if info.ispkg:
            continue
        mod = importlib.import_module(info.name)
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (isinstance(obj, type) and issubclass(obj, IntradayStrategy)
                    and obj is not IntradayStrategy and obj.__module__ == mod.__name__):
                achados.append((info.name, attr_name))
    return sorted(achados)


def _normalizar_volume(bars: pd.DataFrame) -> pd.DataFrame:
    """Adiciona uma coluna `volume` normalizada (mesma regra de
    `backtest.intraday.engine._bar_volume`: `real_volume` quando > 0, senão
    `tick_volume`) -- o parquet que `load_m1` devolve só tem as colunas CRUAS
    do MT5 (`tick_volume`/`real_volume`/`spread`, confirmado por leitura
    direta: `load_m1('WDO@').columns` não tem `volume`), e vários conceitos
    do catálogo (OBV, MFI, Force Index, Ease of Movement, delta/volume,
    VWAP) leem `bars["volume"]` dentro de `initialize()`. Sem isto,
    `KeyError('volume')` derruba boa parte da varredura -- achado real ao
    rodar o sweep pela primeira vez (2026-09-27, relatado por um dos agentes
    de implementação que testou contra dado real em vez de só sintético)."""
    bars = bars.copy()
    real = bars["real_volume"] if "real_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    tick = bars["tick_volume"] if "tick_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    bars["volume"] = real.where(real > 0, tick)
    return bars


def _janela_recente(bars: pd.DataFrame, meses: int = 3) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    bars = bars[[d in completos for d in bars.index.date]]
    if bars.empty:
        return bars
    fim = bars.index.max()
    inicio = fim - pd.DateOffset(months=meses)
    return bars[bars.index >= inicio]


def _rodar_uma(modulo: str, classe: str, bars: pd.DataFrame, capital: float) -> _Resultado:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            mod = importlib.import_module(modulo)
            cls = getattr(mod, classe)
            profile = profile_for(SYMBOL)
            strat = cls(symbol=SYMBOL, tick_size=profile.price_tick_size)
            cfg = config_for(
                profile,
                trade_tick_value=ECONOMIA_WDO[0],
                trade_tick_size=ECONOMIA_WDO[1],
                initial_capital=capital,
                target_fills_as_maker=strat.target_fills_as_maker,
                limit_fill_capped_by_volume=True,
                enforce_capital_cap=True,
            )
            resultado = run_intraday_backtest(bars, strat, cfg)
            item = linha_de_resultado(classe, resultado, capital)
            texto = linha(item)
            trades = list(resultado.trades)
            return _Resultado(
                nome=classe, ok=True,
                liquido_brl=item.liquido_brl, trades=len(trades),
                pregoes=item.pregoes, win_rate_pct=item.win_rate_pct,
                linha_tabela=texto,
            )
        except Exception as exc:  # noqa: BLE001 -- 1 conceito com bug nao derruba os outros 188
            tb = traceback.format_exc(limit=3)
            return _Resultado(nome=classe, ok=False, erro=f"{exc!r}\n{tb}")


def main() -> None:
    bars_full = load_m1(SYMBOL)
    if bars_full.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    bars_full = _normalizar_volume(bars_full)
    bars = _janela_recente(bars_full)
    if bars.empty:
        raise SystemExit("sem pregao completo na janela de 3 meses.")
    pregoes = sorted(set(bars.index.date))

    tarefas = _descobrir_estrategias()
    if not tarefas:
        raise SystemExit(
            "nenhuma estrategia encontrada em strategy.daytrade.lab.lab_concepts "
            "-- os arquivos cNNN_*.py ainda nao foram escritos?"
        )

    print(f"[lab_concepts_sweep] {SYMBOL} -- {pregoes[0]}..{pregoes[-1]} "
          f"({len(pregoes)} pregoes completos, {len(bars):,} barras M1)")
    print(f"capital R${num_br(CAPITAL_TESTE_BRL, 0)} | {len(tarefas)} conceitos descobertos\n",
          flush=True)
    print(cabecalho(), flush=True)

    resultados: list[_Resultado] = []
    falhas: list[_Resultado] = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futuros = {
            executor.submit(_rodar_uma, modulo, classe, bars, CAPITAL_TESTE_BRL): (modulo, classe)
            for modulo, classe in tarefas
        }
        for fut in as_completed(futuros):
            modulo, classe = futuros[fut]
            res = fut.result()
            if res.ok:
                print(res.linha_tabela, flush=True)
                resultados.append(res)
            else:
                print(f"{classe:<30}  *** FALHA: {res.erro.splitlines()[0]} ***", flush=True)
                falhas.append(res)

    resultados.sort(key=lambda r: r.liquido_brl, reverse=True)
    candidatos = [
        r for r in resultados
        if r.liquido_brl > 0 and r.trades >= MIN_TRADES_PARA_FILTRO
    ]

    print(f"\n{'=' * 70}")
    print(f"RESUMO: {len(resultados)} rodadas OK, {len(falhas)} com erro de implementacao, "
          f"{len(candidatos)} candidatos (liquido>0 E >= {MIN_TRADES_PARA_FILTRO} trades)")
    print(f"{'=' * 70}\n")

    if candidatos:
        print(f"CANDIDATOS -- filtro grosso, NAO e' veredito (ver docstring do modulo):\n")
        print(cabecalho())
        for r in candidatos:
            print(r.linha_tabela)
    else:
        print("Nenhum conceito passou no filtro grosso nesta janela de 3 meses.")

    if falhas:
        print(f"\n{len(falhas)} conceito(s) com erro de implementacao (corrigir antes de "
              f"re-rodar, nao contam para o filtro):")
        for r in falhas:
            print(f"  - {r.nome}: {r.erro.splitlines()[0]}")

    saida_csv = ROOT / "scripts" / "daytrade" / "lab_concepts_sweep_2026_09_27_resultado.csv"
    pd.DataFrame([
        dict(nome=r.nome, liquido_brl=r.liquido_brl, trades=r.trades,
             pregoes=r.pregoes, win_rate_pct=r.win_rate_pct, ok=r.ok)
        for r in resultados
    ] + [
        dict(nome=r.nome, liquido_brl=None, trades=None, pregoes=None,
             win_rate_pct=None, ok=False)
        for r in falhas
    ]).to_csv(saida_csv, index=False)
    print(f"\nresultado completo salvo em {saida_csv}")


if __name__ == "__main__":
    main()
