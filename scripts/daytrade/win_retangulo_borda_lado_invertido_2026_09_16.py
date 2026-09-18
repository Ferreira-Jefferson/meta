# -*- coding: utf-8 -*-
"""`win_retangulo` -- ENTRADA NA BORDA com o lado INVERTIDO: a leitura do dono
no grafico, na unica forma que o motor aceita executar.

## O que o dono viu na sombra (2026-09-16)

"O preco estava no piso, foi subindo em direcao ao centro, quando chegou no
centro ativou a ordem. Achei que a ordem seria de COMPRA, pois o preco esta'
subindo, vai ao centro e segue ate' o topo. Mas nao, a ordem colocada foi de
VENDA -- e' como se se esperasse que o preco batesse no centro e voltasse para
o piso."

A observacao esta' CORRETA: e' exatamente isso que o robo faz
(`WinRetangulo.on_bar`, `if bar.close < meio: lado = "short"`).

## Por que o lado NAO e' uma escolha do robo -- e por que o desenho do dono
## nao existe NAQUELE ponto de entrada

Desenho de execucao fechado (`CLAUDE.md`): entrada so' por `EnterLimit`. Uma
limite de COMPRA so' descansa ABAIXO do preco; uma de VENDA, so' ACIMA. Entao,
para uma entrada NO CENTRO:

  preco ABAIXO do centro -> o centro esta' ACIMA do preco -> so' cabe VENDA
  preco ACIMA  do centro -> o centro esta' ABAIXO do preco -> so' cabe COMPRA

"Comprar no centro enquanto o preco sobe do piso" pede uma ordem que dispara
quando o preco ALCANCA um nivel vindo de baixo -- isso e' ordem STOP, que o
motor recusa de proposito (`EntradaAMercadoNaoSuportada`). O robo ja usa o
UNICO lado legal em cada caso; nao ha' parametro a inverter ali.

## A forma EXECUTAVEL da intuicao do dono: entrar na BORDA, nao no centro

Se o preco esta' na metade de baixo, o nivel que fica ABAIXO dele e' o PISO --
e uma COMPRA-limite no piso e' legal. Entao a intencao ("o preco veio do piso
subindo, quero estar comprado rumo ao topo") vira:

  preco na metade de BAIXO -> COMPRA-limite no PISO,  alvo m x L acima,  stop k x L abaixo do piso
  preco na metade de CIMA  -> VENDA-limite no TOPO,   alvo m x L abaixo, stop k x L acima do topo

Isto e' o lado OPOSTO ao da producao em cada metade do retangulo -- exatamente
a inversao que o dono esperava ver --, no unico preco em que ele e' executavel.

## E isto ENGLOBA a outra ideia do dono, a do stop

"Quando ele vai no stop e' sinal que foi no outro lado do retangulo, e por ser
lateralizacao o esperado e' que volte ao centro no minimo -- por que nao
colocar uma ordem no sentido oposto ao que pegou o stop?"

O stop da producao fica em `meio +/- 0,50 x L`, que E' a borda oposta. Entao
"operar de volta ao centro depois do stop" e' a celula `m = 0,50` desta mesma
grade (borda -> centro), so' que armada SEMPRE em vez de so' depois de um stop.
A grade mede as duas perguntas de uma vez, e mede tambem se o alvo curto (o
centro) e' mesmo o certo -- a historia desta linha diz duas vezes que nao: o
desenho original do dono (alvo a 90% do centro ate' a borda) deu 14/15 celulas
negativas, e as 12 reentradas pos-rompimento com alvo no meio foram as piores
da familia. Por isso `m` vai ate' 1,30 (0,30 x L ALEM da borda oposta, a mesma
sobra que a producao usa).

## Metodo

Motor de PRODUCAO, sem atalho: a decisao inteira roda dentro de uma subclasse
de `WinRetangulo` que herda deteccao, morte do retangulo, reset de sessao,
tratamento de ordem rejeitada/expirada e a conferencia mecanica de lado. **So'
o bloco de armar muda.** O que o motor recebe e' `EnterLimit` com prazo, como
sempre.

- 1 contrato fixo, capital R$1.100, custo 7,5 pontos, achatamento de
  `config_for`. WIN@ sem fila calibrada: enche no TOQUE (otimista, e vale
  igual para todas as linhas).
- `risco_maximo_brl=inf` na GRADE E nos dois controles. O teto de R$80 foi
  calibrado contra um stop de `0,50 x L`; aqui o stop e' `k x L`, entao manter
  o teto compararia populacoes diferentes de retangulo. Fica um controle COM
  teto so' para amarrar o numero a' producao de verdade.
- **IS primeiro, sozinho.** O OOS so' roda para as celulas que passarem no IS
  (veredito POSITIVO ou R$/op > 0 com n >= 100). O OOS desta linha ja foi
  gasto duas vezes; nao vai ser varrido por uma grade inteira.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_borda_lado_invertido_2026_09_16.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "_base_borda", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
sys.modules["_base_borda"] = _base
_spec.loader.exec_module(_base)

SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL = 1_100.0
VALOR_PONTO = 0.20
MARGEM_WIN = 100.0
#: piso DESTE desenho, nao do `win_retangulo`: pior rebaixamento por operacao
#: medido nas 8 celulas (R$1.372) + margem crua do WIN@, arredondado. Existe
#: so' para tornar a grade LEGIVEL -- a R$1.100 todas as celulas ficam
#: censuradas e o liquido delas mede o portao de caixa.
CAPITAL_LEITURA = 1_500.0

#: alvo, em fracao da largura, contado A PARTIR DA BORDA de entrada.
#:   0,50 = o CENTRO (a ideia do dono sobre o stop)
#:   1,00 = a borda OPOSTA
#:   1,30 = 0,30xL alem da oposta (a mesma sobra que a producao usa)
ALVOS = (0.50, 0.75, 1.00, 1.30)
#: stop, em fracao da largura, ALEM da borda de entrada.
#:   0,25 = a propria linha de MORTE do retangulo (`MARGEM_MORTE`)
STOPS = (0.25, 0.50)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pc(v, dec=1):
    return "--" if v != v else br(100 * v, dec) + "%"


def _resumo(trades, dias, capital=CAPITAL):
    c = _base.consistencia(trades, dias)
    seq = np.array([t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)],
                   dtype=float)
    c["caixa_min"] = float(capital + np.cumsum(seq).min()) if len(seq) else capital
    c["pior"] = float(seq.min()) if len(seq) else 0.0
    c["rs_op"] = (c["liquido"] / c["n"]) if c["n"] else float("nan")
    c["pts_op"] = c["rs_op"] / VALOR_PONTO if c["n"] else float("nan")
    eq = np.cumsum(seq)
    c["maxdd_op"] = float(np.maximum.accumulate(eq).__sub__(eq).max()) if len(seq) else 0.0
    c.pop("serie", None)
    return c


def _unidade(args):
    """Uma celula: (rotulo, desenho, alvo_mult, stop_mult, teto, janela, dias)."""
    rotulo, desenho, alvo_m, stop_m, teto, janela, dias, capital = args

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import EnterLimit, no_tick
    from strategy.daytrade.lab.win_retangulo import WinRetangulo

    class RetanguloBorda(WinRetangulo):
        """Entra na BORDA, no lado OPOSTO ao da producao.

        Herda TUDO -- deteccao, morte do retangulo, reset de sessao, os hooks
        de ordem rejeitada/expirada, o dimensionamento. So' o bloco de armar e'
        outro, e a conferencia mecanica de lado continua obrigatoria: se o
        arredondamento ao tick puser a limite em cima do preco, a barra passa
        sem ordem, como na classe-mae.
        """

        def __init__(self, *, alvo_mult: float, stop_mult: float, **kw):
            super().__init__(**kw)
            self.alvo_mult = float(alvo_mult)
            self.stop_mult = float(stop_mult)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._hist.append(bar)

            if self._retangulo is not None and self._morreu(bar):
                self._retangulo = None
                self._barras_esperando = None
            if self._retangulo is None:
                self._tenta_detectar()
                if self._retangulo is None:
                    return []

            if positions:
                self._barras_esperando = None
                return []

            if self._barras_esperando is not None:
                self._barras_esperando += 1
                if self._barras_esperando < self.ttl_barras:
                    return []
                self._barras_esperando = None

            r = self._retangulo
            meio, largura = r["meio"], r["largura"]
            topo, piso = r["topo"], r["piso"]

            # A BORDA de entrada e' a mais proxima: aquela de onde o preco
            # acabou de sair. E' o lado OPOSTO ao da producao em cada metade.
            if bar.close < meio:
                lado, borda = "long", piso
                alvo = piso + self.alvo_mult * largura
                stop = piso - self.stop_mult * largura
            elif bar.close > meio:
                lado, borda = "short", topo
                alvo = topo - self.alvo_mult * largura
                stop = topo + self.stop_mult * largura
            else:
                return []

            limite = no_tick(borda, self.tick_size)
            # Mesma conferencia mecanica da classe-mae, pelo mesmo motivo:
            # limite do lado errado e' ordem a mercado disfarcada.
            if lado == "short" and limite <= bar.close:
                return []
            if lado == "long" and limite >= bar.close:
                return []

            self._barras_esperando = 0
            return [EnterLimit(
                side=lado, limit_price=limite,
                initial_stop=no_tick(stop, self.tick_size),
                initial_target=no_tick(alvo, self.tick_size),
                quantity=self._contratos, ttl_bars=self.ttl_barras,
                reason=f"borda_m{self.alvo_mult:.2f}_k{self.stop_mult:.2f}",
            )]

    comum = dict(symbol=SYMBOL, escala_por_caixa=False, quantidade=1,
                 risco_maximo_brl=(80.0 if teto else float("inf")))
    if desenho == "producao":
        strat = WinRetangulo(**comum)
    else:
        strat = RetanguloBorda(alvo_mult=alvo_m, stop_mult=stop_m, **comum)

    df, _ = _base._df()
    alvo_dias = set(dias)
    bars = df[[d in alvo_dias for d in df.index.date]]

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=VALOR_PONTO, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    c = _resumo(list(res.trades), dias, capital)
    motivos = {}
    for t in res.trades:
        motivos[t.exit_reason.value] = motivos.get(t.exit_reason.value, 0) + 1
    c["motivos"] = motivos
    return dict(rotulo=rotulo, janela=janela, capital=capital, c=c)


def _linha(rot, c):
    ic = "[" + pc(c["lo"]) + " ; " + pc(c["hi"]) + "]"
    alvo_n = c["motivos"].get("target", 0)
    return (f"  {rot:<26}{c['n']:>7}{br(c['liquido']):>11}{pc(c['win']):>8}"
            f"{ic:>20}{pc(c['be']):>8}{c['veredito']:>12}{br(c['rs_op']):>9}"
            f"{br(c['pts_op'], 1):>9}{br(c['maxdd_op']):>10}{br(c['caixa_min']):>10}"
            f"{(str(c['sem_trade']) + '/' + str(c['pregoes'])):>9}"
            f"{pc(alvo_n / c['n']) if c['n'] else '--':>8}")


HDR = (f"  {'celula':<26}{'trades':>7}{'liquido':>11}{'acerto':>8}{'IC95':>20}"
       f"{'BEemp':>8}{'veredito':>12}{'R$/op':>9}{'pts/op':>9}{'DD op.':>10}"
       f"{'caixa min':>10}{'sem_tr':>9}{'alvo%':>8}")


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]
    OOS = [d for d in dias_todos if d >= CORTE_OOS]

    print("=" * 146)
    print("win_retangulo -- ENTRADA NA BORDA, LADO INVERTIDO (a leitura do dono no grafico)")
    print("=" * 146)
    print(f"  IS {len(IS)} pregoes | 1 contrato fixo | capital R${br(CAPITAL,0)} | "
          f"custo 7,5 pontos | achatamento de config_for")
    print("  WIN@ SEM fila calibrada: enche no TOQUE nas duas pontas (otimista, igual para todas as linhas)")
    print("  teto de risco DESLIGADO na grade e no controle-espelho: ele foi calibrado para um stop de 0,50xL")
    print("  m = alvo em fracao da largura A PARTIR DA BORDA (0,50 = centro; 1,00 = borda oposta)")
    print("  k = stop em fracao da largura ALEM da borda (0,25 = a propria linha de morte do retangulo)\n",
          flush=True)

    tarefas = [("PRODUCAO (com teto R$80)", "producao", 0, 0, True, "IS", IS, CAPITAL),
               ("PRODUCAO (sem teto)", "producao", 0, 0, False, "IS", IS, CAPITAL)]
    for m in ALVOS:
        for k in STOPS:
            tarefas.append((f"borda m={br(m,2)} k={br(k,2)}", "borda", m, k, False,
                            "IS", IS, CAPITAL))
    # A MESMA grade no piso que ESTE desenho exige. Nao e' "folga": as 8 celulas
    # rebaixam R$1.170-1.372 por operacao, acima do capital de partida do
    # `win_retangulo` -- entao a R$1.100 elas ficam CENSURADAS e o liquido delas
    # mede o portao de caixa, nao a geometria. `CAPITAL_LEITURA` e' o piso
    # derivado do jeito de sempre (pior rebaixamento por operacao + margem crua),
    # medido no proprio desenho. Nao e' recomendacao de capital: e' o minimo para
    # a linha ser LEGIVEL.
    for m in ALVOS:
        for k in STOPS:
            tarefas.append((f"borda m={br(m,2)} k={br(k,2)} @{br(CAPITAL_LEITURA,0)}",
                            "borda", m, k, False, "IS", IS, CAPITAL_LEITURA))

    res_is = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            res_is[r["rotulo"]] = r["c"]
            feitos += 1
            c = r["c"]
            print(f"  [{feitos:>2}/{len(tarefas)}] {r['rotulo']:<26} "
                  f"liquido {br(c['liquido']):>10} | {c['n']:>4} op | "
                  f"acerto {pc(c['win'])} vs BE {pc(c['be'])} | {c['veredito']}",
                  flush=True)

    print("\n" + "=" * 146)
    print("A GRADE, SO' NO IS -- o OOS nao entra aqui de proposito")
    print("=" * 146)
    print(HDR)
    print("  " + "-" * (len(HDR) - 2))
    for rot, *_ in tarefas:
        print(_linha(rot, res_is[rot]))
        if rot in ("PRODUCAO (sem teto)", f"borda m=1,30 k=0,50"):
            print("  " + "-" * (len(HDR) - 2))
    print("\n  'alvo%' = fracao das saidas pelo ALVO. 'caixa min' abaixo de "
          f"R${br(MARGEM_WIN,0)} (margem crua do WIN@) = janela CENSURADA:")
    print("   o robo ficou sem caixa e parou, entao o liquido mede o portao, nao a geometria.")

    # ---------------- portao: quem merece gastar OOS ----------------------
    print("\n" + "=" * 146)
    print("PORTAO DE IS -- so' passa quem tiver veredito POSITIVO ou R$/op > 0 com n >= 100")
    print("=" * 146)
    sobrevivem = []
    for rot, desenho, m, k, teto, _, _, cap in tarefas:
        if desenho == "producao":
            continue
        c = res_is[rot]
        censurada = c["caixa_min"] < MARGEM_WIN
        passa = (not censurada) and (
            c["veredito"] == "POSITIVO" or (c["rs_op"] > 0 and c["n"] >= 100))
        motivo = ("CENSURADA" if censurada else
                  "passa" if passa else
                  f"R$/op {br(c['rs_op'])} / n {c['n']} / {c['veredito']}")
        print(f"  {rot:<26}{'PASSA' if passa else 'para aqui':>12}   {motivo}")
        if passa:
            sobrevivem.append((rot, desenho, m, k, teto, cap))

    if not sobrevivem:
        print("\n  Nenhuma celula passou o portao do IS. O OOS fica INTACTO -- e' o desfecho")
        print("  mais barato possivel: a inversao de lado na borda nao sobrevive nem ao IS.")
        print("\nFIM.")
        return

    print(f"\n  {len(sobrevivem)} celula(s) passaram. O OOS roda SO' para elas.\n", flush=True)
    tarefas_oos = [("PRODUCAO (com teto R$80)", "producao", 0, 0, True, "OOS",
                    OOS, CAPITAL)]
    tarefas_oos += [(rot, des, m, k, teto, "OOS", OOS, cap)
                    for rot, des, m, k, teto, cap in sobrevivem]
    res_oos = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas_oos]
        for fut in as_completed(futs):
            r = fut.result()
            res_oos[r["rotulo"]] = r["c"]
            print(f"  ok OOS {r['rotulo']}", flush=True)

    print("\n" + "=" * 146)
    print("AS SOBREVIVENTES NO OOS -- conferencia de SINAL (o efeito replica ou inverte?)")
    print("=" * 146)
    print(HDR)
    print("  " + "-" * (len(HDR) - 2))
    for rot, *_ in tarefas_oos:
        print(_linha(rot, res_oos[rot]))
    print("\n  Replicar = mesmo SINAL nas duas janelas. Uma celula que ganha no IS e perde no")
    print("  OOS e' sign-flip, que e' como toda familia encerrada deste projeto se despediu.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
