# -*- coding: utf-8 -*-
"""Quanta FILA o `copa_win` enfrenta de verdade -- medido no TAPE do WIN@.

>>> DESFECHO, mesma data: o BLOQUEIO DE DADO FOI RESOLVIDO.
>>>
>>> A primeira rodada deste script saiu invalida, e a causa nao era mercado:
>>> `data/raw_ticks/WIN_A_.parquet` cobria a MEDIANA de 32,2% dos minutos do
>>> pregao (dias em 1%, 2%, 4%; nenhum acima de 37%). A contradicao interna
>>> denunciou sozinha -- o motor dizia que 28,1% das ordens de saida
>>> PREENCHERAM e o tape nao achava volume nenhum em 92,9% delas. As duas
>>> coisas nao podem ser verdade.
>>>
>>> A base foi recoletada pregao a pregao por
>>> `scripts/daytrade/win_recoleta_tape_por_pregao_2026_09_11.py`: 60 pregoes
>>> (2026-06-17 a 2026-09-10) a **100,2% de cobertura**, ~1,78 MILHAO de
>>> negocios por pregao contra os ~450 mil que a base antiga tinha no dia
>>> inteiro. Nao estava so' furada: faltava 4x o dado.
>>>
>>> Este script agora le' `data/raw_ticks/win_por_pregao/`, e a janela da
>>> medicao passa a ser esses 60 pregoes -- nao o historico inteiro.

Pedido do dono, 2026-09-11: "ajuste a sombra para ficar mais proxima da regua
de teste, ela tem que ficar mais proxima de como o mercado se comporta de
verdade".

PRIMEIRO ACHADO, que tira metade do pedido da mesa: a sombra JA E' a regua.
Conferido campo a campo -- `scripts/run_live.py` e os scripts de backtest
montam `config_for` com o MESMO perfil, e os argumentos `trade_tick_value`/
`trade_tick_size` que os scripts passam sao IGNORADOS para futuro (quem manda
e' `profile.price_tick_size` e `point_value_brl`, vindos de
`core.instruments`). As duas configs saem identicas: tick de 5 pontos,
R$0,20/ponto, slippage 1 tick = R$1,00/perna, corretagem R$0,50/round-trip.
Nao ha' o que "aproximar" -- e' o mesmo objeto.

O QUE DE FATO SEPARA AS DUAS DA REALIDADE e' uma coisa so': o WIN@ nao tem
fidelidade de execucao calibrada. `backtest.intraday.fidelidade.FIDELIDADE` so'
tem WDO@. Para o WIN@ o motor roda com `queue_ahead_qty=0` e
`exit_queue_ahead_qty=0` -- ou seja, assume que a NOSSA ordem-limite preenche
sempre que o preco negocia no nivel. Tocar nao e' preencher, e foi exatamente
essa suposicao que, no WDO F1, fez o motor errar o SINAL do resultado
(+R$3,82/op previsto contra -R$3,00 realizado).

POR QUE ESTA MEDICAO E' POSSIVEL SEM DINHEIRO REAL, e onde ela difere da
calibracao do WDO@. A do WDO@ usou ordens REAIS: `history_orders_get` da' o
instante em que a ordem entrou no livro e o instante em que preencheu, e
`copy_ticks_range` da' o volume negociado NAQUELE PRECO entre os dois --
isso mede `Q_frente`, quantos contratos estavam na nossa frente.

Aqui nao ha' ordem real. O que se mede e' o OUTRO lado da mesma conta, e ele
nao precisa de ordem nenhuma: **quanto volume passou NO PRECO da nossa ordem
enquanto ela estaria parada la'**. Chame de `V`. A relacao e' direta -- uma
ordem com `Q` contratos na frente preenche se e somente se `V >= Q`. Entao
medir a distribuicao de `V` sobre os niveis que ESTE robo de fato escolhe, nos
instantes em que ele de fato escolheria, devolve a **curva de preenchimento em
funcao de Q**: "com fila de Q contratos, X% das nossas ordens teriam
preenchido". Nao inventa `Q`; mede o que `Q` teria de vencer.

Isso e' estritamente melhor que a sensibilidade que eu rodei de manha (fila em
fracoes do volume MEDIANO DA BARRA): a barra inteira soma todos os precos
negociados no minuto, e a nossa ordem so' e' consumida pelo volume que passa
NO NOSSO PRECO. Nos dados deste robo os dois diferem por ordem de grandeza.

A EMENDA DA SERIE, que precisou ser desfeita antes de qualquer cruzamento. A
base M1 do `WIN@` e' contínua AJUSTADA POR RAZAO; a base de tick e' crua. O
fator e' constante dentro do pregao ate' a 5a casa decimal e muda nas
rolagens: 1,062934 (2026-03), 1,040702 (2026-05), 1,020499 (2026-08), 1,0
(2026-09, ancora). Cruzar sem desfazer isso compararia precos com ate' 11.532
pontos de diferenca -- os niveis simplesmente nunca casariam, e a conclusao
seria "fila infinita" por defeito de juncao, nao por mercado.

CONSEQUENCIA COLATERAL QUE VALE POR SI: `no_tick(x, 5.0)` arredonda o nivel
numa grade de 5 pontos DO ESPACO AJUSTADO. Um tick real de 5 pontos vale
5 x razao no espaco ajustado (5,31 em marco), entao a grade do backtest NAO
e' a grade negociavel. Este script mede o tamanho desse desalinhamento.

LIMITACOES, que fazem parte do achado:
  * a base de tick cobre 2026-02-20 a 2026-09-03; fora disso nao ha' medicao;
  * `V` e' o volume disponivel, nao `Q`. A curva diz o que a fila teria de
    vencer, nao qual ela e'. Saber `Q` continua exigindo ordem real;
  * volume no preco inclui negocio dos dois lados. No WDO@ mediu-se que, no
    nivel da propria ordem, 99,3% do volume e' do lado que executa contra
    nos -- refinamento ja testado e REFUTADO la'; aqui assume-se o mesmo.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/win_fila_real_por_tape_2026_09_11.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
TAPE_DIR = ROOT / "data" / "raw_ticks" / "win_por_pregao"
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 3_000.0
TICK_REAL = 5.0
#: Fila hipotetica, em contratos, para a curva de preenchimento.
QS = [0, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000]


def br(v, dec=2):
    if v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def carrega_tape():
    """Devolve (volume por (minuto, preco RAW), ultimo preco por minuto).

    Le um arquivo por PREGAO (`win_por_pregao/`) e agrega cada dia em volume
    por MINUTO x PRECO antes de passar para o proximo -- e' a granularidade
    das janelas (barras M1), e mantem o pico de memoria em UM dia. Agregar
    dia a dia, e nao no fim, e' o que separa este script do `backfill_ticks`
    que precisou ser morto com 17,3 GB de RAM (ver o script de recoleta)."""
    arquivos = sorted(TAPE_DIR.glob("*.parquet"))
    if not arquivos:
        raise SystemExit(
            "sem tape por pregao em " + str(TAPE_DIR) + " -- rode antes "
            "`scripts/daytrade/win_recoleta_tape_por_pregao_2026_09_11.py`")
    partes, ultimos = [], []
    for k, f in enumerate(arquivos, 1):
        t = pd.read_parquet(f)
        t = t[t["last"] > 0]
        if t.empty:
            continue
        if t.index.tz is None:
            t.index = t.index.tz_localize("UTC")
        vol = t["volume_real"].fillna(t["volume"])
        minuto = t.index.floor("min")
        g = pd.DataFrame({"min": minuto, "px": t["last"].values, "v": vol.values})
        partes.append(g.groupby(["min", "px"], sort=False)["v"].sum())
        ultimos.append(t.groupby(minuto)["last"].last())
        print("  tape: " + f.stem + "  (" + str(k) + "/" + str(len(arquivos)) + ")",
              flush=True)
    vol_mp = pd.concat(partes).groupby(level=[0, 1]).sum().sort_index()
    ultimo = pd.concat(ultimos).groupby(level=0).last()
    return vol_mp, ultimo


def razoes_por_pregao(ultimo_tick_por_min, m1):
    """Fator de ajuste da serie continua, por pregao. Mediana das razoes
    minuto a minuto -- e' constante dentro do dia ate' a 5a casa, entao a
    mediana e' o proprio valor, e ela ignora os minutos em que uma das duas
    bases nao tem negocio."""
    j = m1["close"].reindex(ultimo_tick_por_min.index).dropna()
    razao = j / ultimo_tick_por_min.reindex(j.index)
    r = razao.groupby(razao.index.date).median()
    disp = razao.groupby(razao.index.date).std()
    return r, disp


def main() -> None:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import no_tick
    from strategy.daytrade.registry import get_daytrade_robot

    m1 = load_m1(SYMBOL).sort_index()
    cont = m1.groupby(m1.index.date).size()
    dias_ok = {d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO}

    print("carregando o tape do WIN@, um arquivo por pregao...", flush=True)
    vol_mp, ultimo = carrega_tape()
    razao, disp = razoes_por_pregao(ultimo, m1)
    print("\nrazao de ajuste medida em " + str(len(razao)) + " pregoes")
    print("  dispersao DENTRO do pregao (desvio da razao): mediana "
          + f"{float(disp.median()):.2e}" + "  (constante ate' a 5a casa)")

    dias_tape = sorted(set(razao.index) & dias_ok)
    print("  janela cruzavel: " + str(dias_tape[0]) + " a " + str(dias_tape[-1])
          + "  (" + str(len(dias_tape)) + " pregoes)\n", flush=True)

    # ---- roda o robo de PRODUCAO, espionando as ordens armadas -----------
    bars = m1[[d in set(dias_tape) for d in m1.index.date]]
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    armadas: list[dict] = []
    ts_atual = {"t": None}
    on_bar_orig = strat.on_bar
    entrada_orig = strat._entrada

    def on_bar_espiao(ts, bar, positions, session_pnl_brl):
        ts_atual["t"] = ts
        return on_bar_orig(ts, bar, positions, session_pnl_brl)

    def entrada_espiao(lado, preco, nivel, vol):
        acao = entrada_orig(lado, preco, nivel, vol)
        armadas.append(dict(
            ts=ts_atual["t"], side=acao.side,
            limite=float(getattr(acao, "limit_price", preco)),
            alvo=float(acao.initial_target), stop=float(acao.initial_stop),
        ))
        return acao

    strat.on_bar = on_bar_espiao
    strat._entrada = entrada_espiao

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    print("robo rodado: " + str(len(armadas)) + " ordens de entrada armadas, "
          + str(len(trades)) + " operacoes fechadas\n", flush=True)

    # ---- desalinhamento de grade ----------------------------------------
    print("===== A GRADE DO BACKTEST NAO E' A GRADE NEGOCIAVEL =====")
    erros = []
    for a in armadas:
        r = razao.get(a["ts"].date())
        if r is None or r != r:
            continue
        bruto = a["limite"] / r
        erros.append(abs(bruto - round(bruto / TICK_REAL) * TICK_REAL))
    e = pd.Series(erros)
    print("distancia do nivel simulado ate' o tick REAL mais proximo, em pontos:")
    print("  mediana " + br(float(e.median()), 2) + "   p90 " + br(float(e.quantile(0.9)), 2)
          + "   maximo " + br(float(e.max()), 2) + "   (tick real = 5,00 pontos)")
    print("  em R$/contrato: mediana " + br(float(e.median()) * 0.2)
          + "   maximo " + br(float(e.max()) * 0.2))

    # ---- volume no NOSSO preco, nas nossas janelas -----------------------
    def volume_no_nivel(nivel_ajustado, t0, t1, dia):
        r = razao.get(dia)
        if r is None or r != r:
            return None
        px = round((nivel_ajustado / r) / TICK_REAL) * TICK_REAL
        try:
            fatia = vol_mp.loc[(slice(t0, t1), px)]
        except KeyError:
            return 0.0
        return float(fatia.sum())

    # ENTRADA: a ordem e' armada na barra seguinte a decisao e vive `ttl` barras
    ttl = strat.entrada_ttl_barras
    v_ent, encheu_ent = [], []
    entradas_por_preco = {(t.side, round(t.entry_price, 2)): t for t in trades}
    for a in armadas:
        t0 = a["ts"] + pd.Timedelta(minutes=1)
        t1 = t0 + pd.Timedelta(minutes=ttl)
        v = volume_no_nivel(a["limite"], t0, t1, a["ts"].date())
        if v is None:
            continue
        v_ent.append(v)
        chave = (a["side"], round(a["limite"], 2))
        t = entradas_por_preco.get(chave)
        encheu_ent.append(bool(t is not None and t0 <= t.entry_ts <= t1))

    # SAIDA POR ALVO: a limite fica parada da entrada ate' a saida
    v_sai, encheu_sai = [], []
    for t in trades:
        cand = [a for a in armadas
                if a["side"] == t.side and abs(a["limite"] - t.entry_price) < 1e-6
                and a["ts"] <= t.entry_ts]
        if not cand:
            continue
        alvo = cand[-1]["alvo"]
        v = volume_no_nivel(alvo, t.entry_ts, t.exit_ts, t.entry_ts.date())
        if v is None:
            continue
        v_sai.append(v)
        encheu_sai.append(t.exit_reason.value == "target")

    for rot, vs, fills in (("ENTRADA (limite no nivel rompido, prazo "
                            + str(ttl) + " barras)", v_ent, encheu_ent),
                           ("SAIDA POR ALVO (limite parada ate' pagar)",
                            v_sai, encheu_sai)):
        s = pd.Series(vs)
        print("\n\n===== " + rot + " =====")
        print("n = " + str(len(s)) + " ordens   |   o motor encheu "
              + br(100 * pd.Series(fills).mean(), 1) + "% delas (fila ZERO)")
        print("\nvolume negociado NO NOSSO PRECO durante a janela (contratos):")
        for q, val in (("minimo", s.min()), ("p10", s.quantile(.10)),
                       ("p25", s.quantile(.25)), ("MEDIANA", s.median()),
                       ("p75", s.quantile(.75)), ("p90", s.quantile(.90)),
                       ("maximo", s.max())):
            print("  " + q.ljust(10) + br(float(val), 0).rjust(14))
        zero = float((s == 0).mean())
        print("  ordens com volume ZERO no nosso preco: " + br(100 * zero, 1) + "%")
        print("\ncurva de preenchimento -- com fila de Q contratos na frente,")
        print("que fracao das nossas ordens teria preenchido (V >= Q):")
        print("  " + "Q".rjust(10) + "preencheria".rjust(14))
        for q in QS:
            print("  " + br(q, 0).rjust(10) + (br(100 * float((s >= q).mean()), 1) + "%").rjust(14))


if __name__ == "__main__":
    main()
