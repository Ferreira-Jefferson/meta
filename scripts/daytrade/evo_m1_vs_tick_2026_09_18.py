"""CALIBRACAO DO SURROGADO (2026-09-18) -- de quanto o M1 e' mais generoso
que o tick, e qual agravamento de fila cancela essa generosidade.

## A pergunta

A busca evolutiva do WDO@ precisa rodar em M1: em tick um pregao custa 74,9s
contra 0,21s, e uma evolucao de ~7.200 avaliacoes em tick levaria dezenas de
milhares de horas de CPU. Mas M1 e' um SURROGADO do tick, e todo surrogado
tem desvio.

O desvio conhecido tem MECANISMO, nao e' suspeita vaga. O motor consome a
fila (`queue_ahead_qty`) creditando o volume da BARRA toda vez que a barra
TOCA o nivel da ordem-limite. Em base de tick a barra e' UM negocio num preco
so', entao "volume da barra que tocou o nivel" e' literalmente volume NO
NIVEL -- a conta que `fidelidade.py` calibrou contra extrato. Em M1 a barra
e' um minuto inteiro, e quase todo o volume dela negociou em OUTROS precos.
A fila de 329 contratos e' varrida por um unico minuto ativo, e a ordem
preenche.

Uma busca evolutiva encontra esse tipo de folga com uma eficiencia que
nenhuma varredura manual tem. Foi o que a grade de 250 celulas fez ao eleger
o T1: a celula que mais explorava a lacuna do modelo de custo da epoca.

## O metodo

Mesmo robo (`WdoOrb` de PRODUCAO -- nenhum parametro de estrategia tocado),
mesmos pregoes, mesmo capital, mesmo motor, mesma janela de pregao. So' muda
a BASE e, no lado M1, o tamanho da fila. A referencia e' o TICK com a fila
calibrada de `fidelidade.py` (329/494), que e' a unica premissa deste repo
aferida contra extrato real.

O unico parametro traduzido e' o prazo da ordem de entrada: `entrada_ttl_bars
=5000` foi calibrado em BARRAS DE TICK (~336 barras/minuto -> ~14,9 min), e
5000 barras M1 seriam tres dias e meio. Nao traduzir seria comparar dois
robos diferentes, nao duas bases. Ver CLAUDE.md, "nunca traduza prazo em
barras para prazo em tempo sem calibrar".

## O que decide

O criterio NAO e' "qual multiplicador reproduz melhor o tick". Reproduzir e'
uma coisa; o que este projeto precisa e' outra -- que o M1 **nunca seja mais
generoso** que o tick. Erro pessimista so' pode subestimar o individuo, e a
confirmacao em tick so' pode melhorar o numero dele. Erro otimista e' o que
produziu um motor prevendo +R$3,82/op num pregao que deu -R$3,00.

Entao o multiplicador adotado e' o MENOR que satisfaz, ao mesmo tempo:

    trades(M1) <= trades(tick)      e      R$/op(M1) <= R$/op(tick)

Se nenhum satisfizer, o M1 nao serve de surrogado e o projeto muda de
desenho -- e isso tambem e' resultado, nao fracasso.

Uso: `python -u scripts/daytrade/evo_m1_vs_tick_2026_09_18.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
for _p in (RAIZ / "src", Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.fidelidade import fidelidade_for  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from strategy.daytrade.lab.wdo_orb import WdoOrb  # noqa: E402
from evo.dados import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, ECONOMIA_WDO, SYMBOL, bars_m1, bars_tick, pregoes,
)

FID = fidelidade_for(SYMBOL)
#: Prazo da entrada do ORB traduzido de tick para M1: 5000 barras de tick
#: / ~336 barras por minuto ~= 15 minutos = 15 barras M1.
TTL_M1_BARRAS = 15

#: Multiplicadores de fila testados no lado M1. O 1x reproduz o motor como
#: ele esta' hoje -- e' o que mostra o TAMANHO do problema, nao um candidato.
MULTIPLICADORES = (1, 3, 6, 10, 20, 40)

JANELA = "TREINO"
MAX_WORKERS = min(12, os.cpu_count() or 4)
SAIDA = RAIZ / "scratch" / "evo_wdo_2026_09_18"


def _config(strategy: WdoOrb, q_ent: float, q_sai: float):
    """MESMO montador que `scripts/run_live.py` usa para subir o robo sombra
    -- e' o que garante que a janela de pregao (12:00-21:30 UTC, achatamento
    21:25), o custo (R$0,50 round-trip) e o portao de caixa aqui sejam
    literalmente os da operacao real, e nao uma reconstrucao parecida."""
    valor_tick, tam_tick = ECONOMIA_WDO
    return config_for(
        profile_for(SYMBOL),
        trade_tick_value=valor_tick, trade_tick_size=tam_tick,
        target_fills_as_maker=strategy.target_fills_as_maker,
        anchor_exits_at_fill=strategy.anchor_exits_at_fill,
        initial_capital=CAPITAL_PARTIDA_BRL,
        queue_ahead_qty=q_ent, exit_queue_ahead_qty=q_sai,
    )


def _metricas(res, rotulo: str, dia: str, extra: dict) -> dict:
    trades = list(res.trades)
    return {
        "celula": rotulo,
        "dia": dia,
        "trades": len(trades),
        "liquido": sum(t.pnl_brl for t in trades),
        "vencedores": sum(1 for t in trades if t.pnl_brl > 0),
        **extra,
    }


def roda_pregao(dia: str) -> list[dict]:
    """UM pregao: as celulas M1, mais a referencia em tick. O tick custa ~75s
    e domina o tempo; as celulas M1 sao troco perto disso, entao rodam todas
    no mesmo processo que ja' pagou o custo de abrir o dia."""
    linhas: list[dict] = []
    with redirect_stdout(StringIO()):
        bm1 = bars_m1(dia)
        for mult in MULTIPLICADORES:
            s = WdoOrb(entrada_ttl_bars=TTL_M1_BARRAS)
            cfg = _config(s, FID.queue_ahead_qty * mult,
                          FID.exit_queue_ahead_qty * mult)
            res = run_intraday_backtest(bm1, s, cfg)
            linhas.append(_metricas(res, f"M1_x{mult}", dia,
                                    {"barras": len(bm1)}))

        bt = bars_tick(dia)
        if not bt.empty:
            s = WdoOrb()
            cfg = _config(s, FID.queue_ahead_qty, FID.exit_queue_ahead_qty)
            res = run_intraday_backtest(bt, s, cfg)
            minutos = max(1.0, (bt.index[-1] - bt.index[0]).total_seconds() / 60)
            linhas.append(_metricas(res, "TICK", dia, {
                "barras": len(bt), "barras_por_minuto": len(bt) / minutos}))
    return linhas


def _resumo(df: pd.DataFrame) -> None:
    print()
    print("=" * 80)
    print(f"{'celula':<12}{'trades':>8}{'R$/op':>9}{'liquido':>12}"
          f"{'win%':>8}{'pregoes c/ op':>16}")
    print("-" * 80)
    referencia: tuple[int, float] | None = None
    for celula in ["TICK"] + [f"M1_x{m}" for m in MULTIPLICADORES]:
        sub = df[df["celula"] == celula]
        if sub.empty:
            continue
        n = int(sub["trades"].sum())
        liq = float(sub["liquido"].sum())
        rop = liq / n if n else float("nan")
        win = 100.0 * float(sub["vencedores"].sum()) / n if n else float("nan")
        com_op = int((sub["trades"] > 0).sum())
        marca = ""
        if celula == "TICK":
            referencia = (n, rop)
        elif referencia is not None:
            if n <= referencia[0] and rop <= referencia[1]:
                marca = "  <- nao-generoso"
        print(f"{celula:<12}{n:>8}{rop:>+9.2f}{liq:>+12.2f}{win:>8.2f}"
              f"{com_op:>10}/{len(sub):<5}{marca}")
    print("=" * 80)


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    dias = pregoes(JANELA)
    print(f"janela {JANELA}: {len(dias)} pregoes  |  {MAX_WORKERS} processos",
          flush=True)
    print(f"referencia TICK: fila {FID.queue_ahead_qty:.0f}/"
          f"{FID.exit_queue_ahead_qty:.0f}  ({FID.estimador}, medida em "
          f"{FID.medido_em})", flush=True)
    print(f"robo: WdoOrb de producao, capital R${CAPITAL_PARTIDA_BRL:.2f} "
          f"reposto por pregao\n", flush=True)

    tudo: list[dict] = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in dias}
        feitos = 0
        for fut in as_completed(futuros):
            dia = futuros[fut]
            linhas = fut.result()
            tudo.extend(linhas)
            feitos += 1
            tk = next((x for x in linhas if x["celula"] == "TICK"), None)
            m1 = next((x for x in linhas if x["celula"] == "M1_x1"), None)
            parte_tick = ("tick sem dado" if tk is None else
                          f"tick {tk['trades']:>2}op R${tk['liquido']:>+8.2f}")
            parte_m1 = ("m1 sem dado" if m1 is None else
                        f"m1x1 {m1['trades']:>2}op R${m1['liquido']:>+8.2f}")
            print(f"[{feitos:>3}/{len(dias)}] {dia}  {parte_tick}  |  "
                  f"{parte_m1}", flush=True)

    df = pd.DataFrame(tudo)
    df.to_parquet(SAIDA / "m1_vs_tick.parquet")
    _resumo(df)

    tk = df[df["celula"] == "TICK"]
    if not tk.empty and "barras_por_minuto" in tk.columns:
        bpm = tk["barras_por_minuto"].dropna()
        if not bpm.empty:
            print(f"\nbarras por minuto no tick: mediana {bpm.median():.0f}  "
                  f"p25 {bpm.quantile(.25):.0f}  p75 {bpm.quantile(.75):.0f}  "
                  f"(n={len(bpm)} pregoes)")
    print(f"\nbruto em {SAIDA / 'm1_vs_tick.parquet'}")


if __name__ == "__main__":
    main()
