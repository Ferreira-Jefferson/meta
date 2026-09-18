# -*- coding: utf-8 -*-
"""`win_retangulo` -- DIAGNOSTICO por operacao: a tendencia vigente muda o
ACERTO, muda a MAGNITUDE, e qual regua descreve melhor o tamanho do movimento?

Pedido do dono (2026-09-16), tres ideias:

  1. Priorizar a tendencia vigente (em queda, esperar subir para vender).
  2. Alvo MENOR na operacao CONTRA a tendencia (onda corretiva e' menor).
  3. Usar razoes de Elliott/Fibonacci como regua de alvo e stop.
  4. "Quando ele vai no stop e' sinal que foi no outro lado do retangulo, e por
     ser lateralizacao o esperado e' que volte ao centro no minimo -- por que
     nao colocar uma ordem no sentido oposto ao que pegou o stop?"

A ideia 4 tem uma base MECANICA que as outras tres nao tem: o stop do robo
fica em `meio +/- 0,50 x L`, que e' exatamente a BORDA oposta, e a linha de
MORTE do retangulo so' vem em `meio +/- 0,75 x L` (`MARGEM_MORTE`). Tomar
stop e', literalmente, chegar a' borda com o retangulo ainda vivo. O fade
dali de volta ao meio vale 0,50xL de alvo contra 0,25xL de risco -- razao
2:1, o INVERSO da geometria "stop longe / alvo perto" que ja foi reprovada
duas vezes nesta linha (os 14/15 do desenho D1 original e as 12 reentradas
pos-rompimento). Por isso ela nao esta' coberta por aquelas refutacoes.

## Por que DIAGNOSTICO e nao varredura

A ideia 1 ja tem medicao anterior apontando contra: `copawin_retangulo_
continuacao_2026_09_15.py` mediu se a QUEBRA do retangulo segue a tendencia
anterior em 5 reguas x 4 faixas de forca -- continuacao ~50% em todas as
celulas, nas duas janelas. Mas aquilo mediu a DIRECAO da quebra, nao o
RESULTADO da operacao do robo (que tem stop 0,50xL e alvo 0,80xL, geometria
assimetrica), e nao mediu MAGNITUDE nenhuma. A ideia 2 vive exatamente ai':
direcao 50/50 e amplitude assimetrica sao afirmacoes independentes.

Entao o passo certo e' o menor que refuta: rodar o robo de PRODUCAO uma vez
por janela, carimbar cada operacao com o estado de tendencia no instante em
que a ordem foi ARMADA (causal -- so' barras <= ts da armada) e ler as
diferencas. Nenhum parametro novo, nenhuma grade. Se acerto e MFE nao se
separam por alinhamento, as ideias 1 e 2 morrem sem custar uma varredura.

## As reguas de tendencia (todas causais)

  perna_pre   -- a perna IMEDIATAMENTE anterior ao retangulo: close[i-W] menos
                 close[i-3W]. E' a mesma janela que o teste de CONTRACAO do
                 detector consome, e e' a leitura mais "Elliott" das cinco: o
                 retangulo como CORRECAO de um impulso que acabou de ocorrer.
  K20/K60/K120-- close[i] menos close[i-K] barras M1.
  abertura    -- close[i] menos o close da PRIMEIRA barra do pregao.

FORCA = |variacao| / largura do retangulo. Uma perna que andou menos que a
propria largura da banda nao e' tendencia, e' ruido (mesma convencao do script
de continuacao).

ALINHADO = o lado da operacao concorda com o sinal da regua. Atencao a uma
sutileza que inverte a leitura ingenua: o lado do robo e' decidido pela
METADE do retangulo em que o preco esta' (abaixo do meio -> vende no meio).
Entao "alinhado" aqui significa que a operacao anda NO SENTIDO da tendencia
vigente -- que e' exatamente o que o dono pediu para priorizar.

## MFE / MAE -- o numero que decide a ideia 2

MFE = maior excursao a FAVOR entre o fill de entrada e o de saida; MAE =
maior excursao CONTRA. Post-hoc, lidos da serie M1 (medicao, nao decisao).
Normalizados pela largura do retangulo, porque e' a largura a regua atual do
alvo (0,80xL) e do stop (0,50xL).

Se a onda contra a tendencia for menor, o MFE das operacoes DESALINHADAS tem
de ser menor que o das ALINHADAS -- e a diferenca tem de aparecer nas duas
janelas. Se nao aparecer, encurtar o alvo contra a tendencia e' cortar de um
lugar onde nao ha' assimetria.

## Ideia 3, o que este script consegue responder

Elliott/Fibonacci e' uma REGUA (0,382 / 0,50 / 0,618 / 1,000 / 1,618) e uma
ANCORA (o impulso anterior, nao a largura da banda). O script mede as duas
coisas que decidem se vale construir a estrategia:
  (a) a fracao de operacoes que ALCANCA cada nivel de Fibonacci, com a ancora
      LARGURA e com a ancora PERNA ANTERIOR;
  (b) qual das duas ancoras CORRELACIONA melhor com o MFE realizado. Se a
      largura explicar melhor (e ela ja e' a regua em uso), a ancora de
      Elliott nao tem nada a acrescentar e a ideia 3 morre aqui.

## Convencoes obrigatorias do repo

- Robo de PRODUCAO, kwargs de `registry._KWARGS_PADRAO`, nunca redigitados.
- **1 contrato fixo** (`escala_por_caixa=False`): isola a GEOMETRIA do portao
  de capital. E' a mesma configuracao da tabela estatistica da docstring do
  robo (IS 615 operacoes / 44,9% / R$3.720,70), que serve de CONFERENCIA de
  arranque aqui -- se o numero nao bater, o diagnostico nao vale.
- Capital R$1.100 (o piso medido), corte de achatamento vindo de `config_for`.
- WIN@ **nao tem fila calibrada** (`fidelidade.py` so' tem WDO@): enche no
  TOQUE nas duas pontas. Vale para todas as linhas igualmente, entao nao
  contamina a COMPARACAO entre grupos -- mas contamina o nivel absoluto.
- IS < 2026-06-13, OOS >= 2026-06-13. **Nenhum parametro e' escolhido aqui**:
  o OOS entra so' como conferencia de SINAL (o efeito replica ou inverte).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_tendencia_diagnostico_2026_09_16.py`
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
    "_base_tend", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
sys.modules["_base_tend"] = _base
_spec.loader.exec_module(_base)

SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL = 1_100.0
VALOR_PONTO = 0.20
FIB = (0.382, 0.500, 0.618, 0.800, 1.000, 1.618)
REGUAS = ("perna_pre", "K20", "K60", "K120", "abertura")
#: IDEIA 4 -- o stop novo, em fracao da largura ALEM da borda em que o robo
#: tomou o stop. 0,25 e' a propria linha de MORTE do retangulo (`MARGEM_MORTE`).
K_STOP_FADE = (0.15, 0.25, 0.50)
#: prazo da limite de reentrada na borda, em barras M1 (o mesmo `ttl` do robo).
TTL_FADE = 10
CUSTO_PTS = 7.5


def _corrida(post, side, entrada, meio, k, largura):
    """Do preco de ENTRADA ate o desfecho: alcanca o MEIO (alvo) ou anda
    `k x largura` ALEM da borda (stop)? Devolve (desfecho, pontos brutos).

    Empate dentro da MESMA barra conta como STOP -- o M1 nao diz a ordem dos
    dois toques, e chutar a favor e' exatamente o tipo de otimismo que ja
    inverteu o sinal de um resultado neste projeto.
    """
    if side == "short":
        alvo, stop = meio, entrada + k * largura
        for h, lo in zip(post["high"].to_numpy(float), post["low"].to_numpy(float)):
            if h >= stop:
                return "stop", -(k * largura)
            if lo <= alvo:
                return "alvo", entrada - alvo
        if len(post) == 0:
            return "sem_barra", 0.0
        return "aberto", entrada - float(post["close"].iloc[-1])
    alvo, stop = meio, entrada - k * largura
    for h, lo in zip(post["high"].to_numpy(float), post["low"].to_numpy(float)):
        if lo <= stop:
            return "stop", -(k * largura)
        if h >= alvo:
            return "alvo", alvo - entrada
    if len(post) == 0:
        return "sem_barra", 0.0
    return "aberto", float(post["close"].iloc[-1]) - entrada


def _retoque(post, side, borda, ttl):
    """Indice da barra em que a limite parada NA BORDA encheria, ou None.

    Duas condicoes, nesta ordem, porque e' o que o motor exige: (1) o preco
    precisa se AFASTAR da borda para que a ordem possa sequer descansar do
    lado certo (venda so' acima do preco, compra so' abaixo); (2) depois
    disso, a borda precisa ser TOCADA de novo dentro do prazo.
    """
    close = post["close"].to_numpy(float)
    high = post["high"].to_numpy(float)
    low = post["low"].to_numpy(float)
    armada = None
    for j in range(len(close)):
        if armada is None:
            if (side == "short" and close[j] < borda) or \
               (side == "long" and close[j] > borda):
                armada = j
            continue
        if j - armada > ttl:
            return None
        if (side == "short" and high[j] >= borda) or \
           (side == "long" and low[j] <= borda):
            return j
    return None


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pc(v, dec=1):
    return "--" if v != v else br(100 * v, dec) + "%"


def _resumo(sub) -> dict:
    """Bloco padrao de leitura de um subconjunto de operacoes."""
    n = len(sub)
    if n == 0:
        return dict(n=0, win=float("nan"), be=float("nan"), rs=float("nan"),
                    pts=float("nan"), lo=float("nan"), hi=float("nan"), ver="--",
                    liquido=0.0)
    g = sub.loc[sub.pnl > 0, "pnl"]
    p = sub.loc[sub.pnl <= 0, "pnl"]
    gm = float(g.mean()) if len(g) else 0.0
    pm = float(abs(p.mean())) if len(p) else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = _base.ic95(len(g), n)
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be else "--"
    return dict(n=n, win=len(g) / n, be=be, rs=float(sub.pnl.mean()),
                pts=float(sub.pnl.mean()) / VALOR_PONTO, lo=lo, hi=hi, ver=ver,
                liquido=float(sub.pnl.sum()))


# ---------------------------------------------------------------------------
# a unidade de trabalho: um backtest por janela, com as ordens ARMADAS gravadas
# ---------------------------------------------------------------------------

def _unidade(args):
    janela, dias = args
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import EnterLimit
    from strategy.daytrade.lab.win_retangulo import WinRetangulo
    from strategy.daytrade.registry import _KWARGS_PADRAO

    class _Diag(WinRetangulo):
        """So' GRAVA. Nao muda uma virgula da decisao -- `super().on_bar` e' a
        unica coisa que decide, e o que sai dela e' o que o motor recebe."""

        def __init__(self, **kw):
            super().__init__(**kw)
            self.armadas = []

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
            for a in acoes:
                if isinstance(a, EnterLimit):
                    r = self._retangulo
                    self.armadas.append(dict(
                        ts=ts, side=a.side, limite=float(a.limit_price),
                        largura=float(r["largura"]), meio=float(r["meio"]),
                        topo=float(r["topo"]), piso=float(r["piso"]),
                        contracao=float(r["contracao"]),
                        contencao=float(r["contencao"]),
                        deriva=float(r["deriva_frac"]),
                    ))
            return acoes

    kw = dict(_KWARGS_PADRAO.get("win_retangulo", {}))
    kw["symbol"] = SYMBOL
    kw["escala_por_caixa"] = False      # 1 contrato fixo: isola a geometria
    kw["quantidade"] = 1
    strat = _Diag(**kw)

    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=VALOR_PONTO, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    W = strat.janela_barras
    ttl = strat.ttl_barras
    armadas = pd.DataFrame(strat.armadas)

    linhas = []
    sem_par = 0
    for t in res.trades:
        dia = t.entry_ts.date()
        dbars = bars[bars.index.date == dia]
        idx = dbars.index
        # a armada que originou este fill: mesma ponta, ts <= entrada, dentro
        # do prazo da ordem. A mais recente que satisfaz e' a correta -- o robo
        # nao rearma por cima de ordem viva (`_barras_esperando`).
        cand = armadas[(armadas.side == t.side)
                       & (armadas.ts <= t.entry_ts)
                       & (armadas.ts >= t.entry_ts - pd.Timedelta(minutes=ttl))]
        if len(cand) == 0:
            sem_par += 1
            continue
        a = cand.iloc[-1]

        i = int(idx.get_indexer([a["ts"]])[0])
        if i < 0:
            sem_par += 1
            continue
        c = dbars["close"].to_numpy(float)

        def _delta(k, _c=c, _i=i):
            j = _i - k
            return float(_c[_i] - _c[j]) if j >= 0 else float("nan")

        perna_pre = (float(c[i - W] - c[i - 3 * W]) if i - 3 * W >= 0
                     else float("nan"))
        reguas = dict(perna_pre=perna_pre, K20=_delta(20), K60=_delta(60),
                      K120=_delta(120), abertura=float(c[i] - c[0]))

        # MFE/MAE entre fill de entrada e fill de saida
        jan = dbars[(dbars.index >= t.entry_ts) & (dbars.index <= t.exit_ts)]
        if len(jan) == 0:
            mfe = mae = float("nan")
        elif t.side == "long":
            mfe = float(jan["high"].max() - t.entry_price)
            mae = float(t.entry_price - jan["low"].min())
        else:
            mfe = float(t.entry_price - jan["low"].min())
            mae = float(jan["high"].max() - t.entry_price)

        linha = dict(
            janela=janela, dia=dia, ts=a["ts"], side=t.side,
            pnl=float(t.pnl_brl), motivo=t.exit_reason.value,
            largura=float(a["largura"]), contracao=float(a["contracao"]),
            entry=float(t.entry_price),
            casou_preco=abs(float(a["limite"]) - float(t.entry_price)),
            mfe=max(0.0, mfe), mae=max(0.0, mae),
            barras=int(len(jan)),
        )
        for nome, v in reguas.items():
            linha[f"t_{nome}"] = v
            linha[f"f_{nome}"] = abs(v) / linha["largura"] if v == v else float("nan")
            if v != v or v == 0:
                linha[f"al_{nome}"] = None
            else:
                linha[f"al_{nome}"] = bool(
                    (t.side == "long" and v > 0) or (t.side == "short" and v < 0))

        # ---- IDEIA 5: DE ONDE o preco veio antes de preencher a ordem? ----
        # Observacao do dono (2026-09-16): "se o preco esta' vindo do piso, o
        # caminho natural numa lateralizacao e' ir em direcao ao topo; hoje
        # parece que se decide sempre que o preco chega no centro, mas nao
        # esta' considerando DE ONDE o preco esta' vindo".
        #
        # Esta' correto: `WinRetangulo` decide por `close < meio`, que e' uma
        # FOTO da posicao. A perna que preenche a ordem sempre vem do lado
        # oposto (a venda parada no centro so' enche com preco SUBINDO), mas o
        # TAMANHO dessa perna -- veio do piso, ou estava encostado no centro? --
        # nao entra na decisao. Aqui ele e' medido: o extremo alcancado antes
        # do fill, em fracao da largura a partir do preco de entrada.
        #   ~0,50 -> veio da borda, traves sou meia largura
        #   ~0,10 -> mal se afastou do centro
        pre = dbars[dbars.index <= t.entry_ts]
        for k_look, rot in ((10, "10"), (20, "20")):
            jj = pre.iloc[-k_look:]
            if len(jj) == 0:
                linha[f"origem{rot}"] = float("nan")
                continue
            ext = (float(jj["low"].min()) if t.side == "short"
                   else float(jj["high"].max()))
            linha[f"origem{rot}"] = abs(t.entry_price - ext) / linha["largura"]
        desde = pre[pre.index >= a["ts"]]
        if len(desde):
            ext = (float(desde["low"].min()) if t.side == "short"
                   else float(desde["high"].max()))
            linha["origem_armada"] = abs(t.entry_price - ext) / linha["largura"]
        else:
            linha["origem_armada"] = float("nan")

        # ---- IDEIA 4: depois do STOP na borda, o preco volta ao meio? -----
        if t.exit_reason.value == "stop":
            L = linha["largura"]
            meio = float(a["meio"])
            borda = float(t.exit_price)
            post = dbars[dbars.index > t.exit_ts]
            for k in K_STOP_FADE:
                d, p = _corrida(post, t.side, borda, meio, k, L)
                linha[f"ideal_k{k:g}_desf"] = d
                linha[f"ideal_k{k:g}_pts"] = p - CUSTO_PTS
            j = _retoque(post, t.side, borda, TTL_FADE)
            linha["fade_encheu"] = j is not None
            for k in K_STOP_FADE:
                if j is None:
                    linha[f"exec_k{k:g}_desf"] = "sem_fill"
                    linha[f"exec_k{k:g}_pts"] = float("nan")
                else:
                    d, p = _corrida(post.iloc[j + 1:], t.side, borda, meio, k, L)
                    linha[f"exec_k{k:g}_desf"] = d
                    linha[f"exec_k{k:g}_pts"] = p - CUSTO_PTS
        linhas.append(linha)

    ops = pd.DataFrame(linhas)
    return dict(janela=janela, ops=ops, armadas=len(armadas), sem_par=sem_par,
                pregoes=len(dias), n_trades=len(res.trades))


# ---------------------------------------------------------------------------

def main():
    df, dias_todos = _base._df()
    JAN = {"IS": [d for d in dias_todos if d < CORTE_OOS],
           "OOS": [d for d in dias_todos if d >= CORTE_OOS]}

    print("=" * 128)
    print("win_retangulo -- a TENDENCIA VIGENTE muda o acerto (ideia 1) ou a")
    print("                 MAGNITUDE (ideia 2)? E qual regua descreve o movimento (ideia 3)?")
    print("=" * 128)
    print(f"  IS {len(JAN['IS'])} pregoes | OOS {len(JAN['OOS'])} pregoes | "
          f"1 contrato fixo | capital R${br(CAPITAL,0)} | custo 7,5 pontos")
    print("  robo de PRODUCAO (kwargs do registry), achatamento vindo de config_for")
    print("  WIN@ SEM fila calibrada: enche no TOQUE nas duas pontas")
    print("  OOS entra so' como conferencia de SINAL -- nenhum parametro e' escolhido aqui\n",
          flush=True)

    out = {}
    with ProcessPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(_unidade, (jn, dd)): jn for jn, dd in JAN.items()}
        for fut in as_completed(futs):
            r = fut.result()
            out[r["janela"]] = r
            print(f"  ok {r['janela']}: {r['n_trades']} operacoes, "
                  f"{r['armadas']} ordens armadas, {r['sem_par']} sem par "
                  f"(nao entram nas tabelas)", flush=True)

    ops_all = pd.concat([out[j]["ops"] for j in ("IS", "OOS")], ignore_index=True)
    ops_all.to_csv(ROOT / "scratch" / "win_retangulo_tendencia_ops.csv", index=False)

    # ---------------- 0. conferencia de arranque --------------------------
    print("\n" + "=" * 128)
    print("0. CONFERENCIA DE ARRANQUE -- bate com a tabela da docstring do robo?")
    print("=" * 128)
    print(f"  {'janela':<7}{'operacoes':>11}{'liquido':>12}{'acerto':>9}"
          f"{'pts/op':>9}   {'esperado (docstring)'}")
    esp = {"IS": "615 op / R$3.720,70 / 44,9%", "OOS": "179 op / R$1.464,50 / 45,8%"}
    for jn in ("IS", "OOS"):
        r = _resumo(out[jn]["ops"])
        print(f"  {jn:<7}{r['n']:>11}{br(r['liquido']):>12}{pc(r['win']):>9}"
              f"{br(r['pts'],1):>9}   {esp[jn]}")
    print("\n  (diferenca de poucas operacoes = as que ficaram sem par de armada;")
    print("   diferenca grande = o diagnostico nao descreve o robo e nada abaixo vale)")

    # ---------------- 1. alinhamento x acerto -----------------------------
    print("\n" + "=" * 128)
    print("1. IDEIA 1 -- PRIORIZAR A TENDENCIA: o acerto separa por alinhamento?")
    print("=" * 128)
    hdr = (f"  {'regua':<12}{'grupo':<11}{'jan':<5}{'n':>6}{'acerto':>9}"
           f"{'IC95':>20}{'BEemp':>8}{'veredito':>12}{'R$/op':>9}{'pts/op':>9}"
           f"{'liquido':>11}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for regua in REGUAS:
        col = f"al_{regua}"
        for rot, filtro in (("ALINHADA", True), ("CONTRA", False)):
            for jn in ("IS", "OOS"):
                o = ops_all[(ops_all.janela == jn) & (ops_all[col] == filtro)]
                r = _resumo(o)
                ic = "[" + pc(r["lo"]) + " ; " + pc(r["hi"]) + "]"
                print(f"  {regua:<12}{rot:<11}{jn:<5}{r['n']:>6}{pc(r['win']):>9}"
                      f"{ic:>20}{pc(r['be']):>8}{r['ver']:>12}{br(r['rs']):>9}"
                      f"{br(r['pts'],1):>9}{br(r['liquido']):>11}")
        print("  " + "-" * (len(hdr) - 2))

    # ---------------- 2. so' as tendencias FORTES -------------------------
    print("\n" + "=" * 128)
    print("2. IDEIA 1, versao FORTE -- e se so' contar quando a tendencia for de verdade?")
    print("=" * 128)
    print("  forca = |variacao da regua| / largura do retangulo. 'fraca' e' ruido, nao tendencia.\n")
    hdr2 = (f"  {'regua':<12}{'forca':<17}{'grupo':<10}{'jan':<5}{'n':>6}"
            f"{'acerto':>9}{'BEemp':>8}{'R$/op':>9}{'pts/op':>9}")
    print(hdr2)
    print("  " + "-" * (len(hdr2) - 2))
    FAIXAS = (("fraca (<0,5x)", 0.0, 0.5), ("media (0,5-1x)", 0.5, 1.0),
              ("forte (1-2x)", 1.0, 2.0), ("muito forte (>2x)", 2.0, float("inf")))
    for regua in REGUAS:
        for nome, a, b in FAIXAS:
            for rot, filtro in (("ALINHADA", True), ("CONTRA", False)):
                for jn in ("IS", "OOS"):
                    o = ops_all[(ops_all.janela == jn)
                                & (ops_all[f"al_{regua}"] == filtro)
                                & (ops_all[f"f_{regua}"] >= a)
                                & (ops_all[f"f_{regua}"] < b)]
                    r = _resumo(o)
                    print(f"  {regua:<12}{nome:<17}{rot:<10}{jn:<5}{r['n']:>6}"
                          f"{pc(r['win']):>9}{pc(r['be']):>8}{br(r['rs']):>9}"
                          f"{br(r['pts'],1):>9}")
        print("  " + "-" * (len(hdr2) - 2))

    # ---------------- 3. MAGNITUDE (ideia 2) ------------------------------
    print("\n" + "=" * 128)
    print("3. IDEIA 2 -- A ONDA CONTRA A TENDENCIA E' MENOR? (MFE, em fracao da largura)")
    print("=" * 128)
    print("  MFE = maior excursao a FAVOR entre o fill de entrada e o de saida.")
    print("  O alvo de producao esta' em 0,80xL; o stop em 0,50xL.\n")
    hdr3 = (f"  {'regua':<12}{'grupo':<10}{'jan':<5}{'n':>6}{'MFE med':>10}"
            f"{'MFE p75':>10}{'MFE p90':>10}{'MAE med':>10}{'>=0,80L':>10}{'>=0,50L':>10}")
    print(hdr3)
    print("  " + "-" * (len(hdr3) - 2))
    for regua in REGUAS:
        for rot, filtro in (("ALINHADA", True), ("CONTRA", False)):
            for jn in ("IS", "OOS"):
                o = ops_all[(ops_all.janela == jn) & (ops_all[f"al_{regua}"] == filtro)]
                if len(o) == 0:
                    continue
                mf = (o.mfe / o.largura).to_numpy(float)
                ma = (o.mae / o.largura).to_numpy(float)
                print(f"  {regua:<12}{rot:<10}{jn:<5}{len(o):>6}"
                      f"{br(float(np.nanmedian(mf)),3):>10}"
                      f"{br(float(np.nanpercentile(mf,75)),3):>10}"
                      f"{br(float(np.nanpercentile(mf,90)),3):>10}"
                      f"{br(float(np.nanmedian(ma)),3):>10}"
                      f"{pc(float(np.mean(mf >= 0.80))):>10}"
                      f"{pc(float(np.mean(mf >= 0.50))):>10}")
        print("  " + "-" * (len(hdr3) - 2))

    # ---------------- 4. ideia 3: ancora e niveis de Fibonacci ------------
    print("\n" + "=" * 128)
    print("4. IDEIA 3 -- QUAL ANCORA DESCREVE O MOVIMENTO: a LARGURA ou a PERNA ANTERIOR?")
    print("=" * 128)
    print("  correlacao de posto (Spearman) entre o MFE em PONTOS e cada ancora candidata.")
    print("  Se a largura correlaciona melhor, a ancora de Elliott nao acrescenta regua nova.\n")
    print(f"  {'janela':<7}{'ancora':<24}{'n':>6}{'Spearman(MFE, ancora)':>25}")
    print("  " + "-" * 62)
    for jn in ("IS", "OOS"):
        o = ops_all[ops_all.janela == jn].copy()
        o["perna_abs"] = o.t_perna_pre.abs()
        o["k60_abs"] = o.t_K60.abs()
        for nome, col in (("largura do retangulo", "largura"),
                          ("|perna anterior|", "perna_abs"),
                          ("|K60|", "k60_abs")):
            sub = o[["mfe", col]].dropna()
            # Spearman = Pearson sobre os POSTOS. Feito na mao de proposito:
            # `method="spearman"` do pandas importa scipy, e o projeto nao tem
            # scipy -- e uma correlacao de posto nao justifica uma dependencia.
            rho = (float(sub["mfe"].rank().corr(sub[col].rank()))
                   if len(sub) > 3 else float("nan"))
            print(f"  {jn:<7}{nome:<24}{len(sub):>6}{br(rho,3):>25}")
        print()

    print("  FRACAO DAS OPERACOES QUE ALCANCA CADA NIVEL, por ancora")
    print(f"  {'janela':<7}{'ancora':<24}{'n':>6}"
          + "".join(f"{('x' + br(f, 3)):>10}" for f in FIB))
    print("  " + "-" * (37 + 10 * len(FIB)))
    for jn in ("IS", "OOS"):
        o = ops_all[ops_all.janela == jn].copy()
        o["perna_abs"] = o.t_perna_pre.abs()
        for nome, col in (("largura do retangulo", "largura"),
                          ("|perna anterior|", "perna_abs")):
            sub = o[["mfe", col]].dropna()
            sub = sub[sub[col] > 0]
            frac = (sub["mfe"] / sub[col]).to_numpy(float)
            print(f"  {jn:<7}{nome:<24}{len(sub):>6}"
                  + "".join(f"{pc(float(np.mean(frac >= f))):>10}" for f in FIB))
        print()

    # ---------------- 5. leitura de controle: por LADO --------------------
    print("=" * 128)
    print("5. CONTROLE -- a assimetria esta' no LADO (compra x venda), e nao na tendencia?")
    print("=" * 128)
    print(f"  {'lado':<8}{'jan':<5}{'n':>6}{'acerto':>9}{'BEemp':>8}{'veredito':>12}"
          f"{'R$/op':>9}{'MFE med':>10}")
    print("  " + "-" * 70)
    for lado in ("long", "short"):
        for jn in ("IS", "OOS"):
            o = ops_all[(ops_all.janela == jn) & (ops_all.side == lado)]
            r = _resumo(o)
            mf = (o.mfe / o.largura).to_numpy(float) if len(o) else np.array([np.nan])
            print(f"  {lado:<8}{jn:<5}{r['n']:>6}{pc(r['win']):>9}{pc(r['be']):>8}"
                  f"{r['ver']:>12}{br(r['rs']):>9}{br(float(np.nanmedian(mf)),3):>10}")
    # ---------------- 6. ideia 4: fade da borda depois do STOP ------------
    print("\n" + "=" * 128)
    print("6. IDEIA 4 -- DEPOIS DO STOP NA BORDA, O PRECO VOLTA AO MEIO?")
    print("=" * 128)
    print("  O stop do robo fica em meio +/- 0,50xL, que E' a borda oposta -- e a linha de")
    print("  MORTE do retangulo so' vem em meio +/- 0,75xL. Tomar stop, entao, e' chegar a'")
    print("  borda com o retangulo AINDA VIVO. A operacao proposta e' o fade dali de volta")
    print("  ao meio: alvo 0,50xL, stop k x L alem da borda. Em k=0,25 a razao e' 2:1,")
    print("  breakeven nominal 33,3% -- o INVERSO da geometria 'stop longe/alvo perto' que")
    print("  ja foi reprovada duas vezes nesta linha.\n")
    print("  IDEAL = enche no proprio preco do stop, sem exigir retoque nem fila. E'")
    print("  OTIMISTA de proposito: se nem assim pagar, a ideia morre sem custar desenho.")
    print("  EXECUTAVEL = limite parada NA BORDA, exige (1) o preco se afastar para a ordem")
    print(f"  poder descansar do lado certo e (2) retoque em ate {TTL_FADE} barras. Custo de")
    print(f"  {br(CUSTO_PTS,1)} pontos ja descontado nos dois. Empate na mesma barra conta como STOP.\n")
    hdr6 = (f"  {'versao':<12}{'k (stop)':<10}{'jan':<5}{'n':>6}{'fill%':>8}"
            f"{'alvo%':>8}{'stop%':>8}{'aberto%':>9}{'BEnom':>8}{'pts/op':>9}"
            f"{'R$/op':>9}{'liquido':>11}")
    print(hdr6)
    print("  " + "-" * (len(hdr6) - 2))
    stops = ops_all[ops_all.motivo == "stop"]
    for versao in ("IDEAL", "EXECUTAVEL"):
        pref = "ideal" if versao == "IDEAL" else "exec"
        for k in K_STOP_FADE:
            for jn in ("IS", "OOS"):
                o = stops[stops.janela == jn]
                if len(o) == 0:
                    continue
                col_d, col_p = f"{pref}_k{k:g}_desf", f"{pref}_k{k:g}_pts"
                base = len(o)
                sub = o[o[col_d].isin(("alvo", "stop", "aberto"))]
                if len(sub) == 0:
                    continue
                pts = sub[col_p].to_numpy(float)
                desf = sub[col_d].to_numpy(object)
                be = k / (0.50 + k)
                print(f"  {versao:<12}{br(k,2):<10}{jn:<5}{len(sub):>6}"
                      f"{pc(len(sub) / base):>8}"
                      f"{pc(float(np.mean(desf == 'alvo'))):>8}"
                      f"{pc(float(np.mean(desf == 'stop'))):>8}"
                      f"{pc(float(np.mean(desf == 'aberto'))):>9}"
                      f"{pc(be):>8}{br(float(np.mean(pts)),1):>9}"
                      f"{br(float(np.mean(pts)) * VALOR_PONTO):>9}"
                      f"{br(float(np.sum(pts)) * VALOR_PONTO):>11}")
        print("  " + "-" * (len(hdr6) - 2))
    print("  'alvo%' e' o acerto e compara-se com 'BEnom' = k/(0,50+k) -- o breakeven a custo")
    print("  ZERO da geometria. 'aberto%' e' o fim de pregao chegando antes do desfecho:")
    print("  liquidado no ultimo fechamento, que e' otimista (a producao achataria antes).")

    # ---------------- 7. ideia 5: DE ONDE o preco veio ---------------------
    print("\n" + "=" * 128)
    print("7. IDEIA 5 -- O ROBO IGNORA DE ONDE O PRECO VEIO. ISSO CUSTA ALGUMA COISA?")
    print("=" * 128)
    print("  Observacao do dono: 'se o preco esta' vindo do piso, o caminho natural numa")
    print("  lateralizacao e' ir em direcao ao topo; hoje parece que se decide sempre que o")
    print("  preco chega no centro, mas nao esta' considerando DE ONDE o preco esta' vindo'.")
    print("  Correto: a decisao e' `close < meio`, uma FOTO da posicao. A perna que preenche")
    print("  sempre vem do lado oposto (a venda parada no centro so' enche com preco SUBINDO),")
    print("  mas o TAMANHO dela nao entra em lugar nenhum da decisao.\n")
    print("  origem = |preco de entrada - extremo alcancado antes do fill| / largura.")
    print("  ~0,50 -> a perna atravessou meia largura (veio da borda); ~0,10 -> mal se afastou.\n")
    hdr7 = (f"  {'lookback':<12}{'faixa de origem':<20}{'jan':<5}{'n':>6}{'acerto':>9}"
            f"{'BEemp':>8}{'veredito':>12}{'R$/op':>9}{'pts/op':>9}{'MFE med':>10}")
    print(hdr7)
    print("  " + "-" * (len(hdr7) - 2))
    FX_ORIG = (("rasa (<0,20L)", 0.0, 0.20), ("media (0,20-0,35L)", 0.20, 0.35),
               ("funda (0,35-0,50L)", 0.35, 0.50),
               ("da borda (>=0,50L)", 0.50, float("inf")))
    for look, col in (("10 barras", "origem10"), ("20 barras", "origem20"),
                      ("desde a armada", "origem_armada")):
        for nome, a, b in FX_ORIG:
            for jn in ("IS", "OOS"):
                o = ops_all[(ops_all.janela == jn) & (ops_all[col] >= a)
                            & (ops_all[col] < b)]
                r = _resumo(o)
                mf = (o.mfe / o.largura).to_numpy(float) if len(o) else np.array([np.nan])
                print(f"  {look:<12}{nome:<20}{jn:<5}{r['n']:>6}{pc(r['win']):>9}"
                      f"{pc(r['be']):>8}{r['ver']:>12}{br(r['rs']):>9}"
                      f"{br(r['pts'],1):>9}{br(float(np.nanmedian(mf)),3):>10}")
        print("  " + "-" * (len(hdr7) - 2))
    print("  Se a perna FUNDA (veio da borda) pagar pior que a RASA, a leitura do dono esta'")
    print("  medida: entrar contra um movimento que ja atravessou meia largura e' o caso ruim,")
    print("  e 'de onde veio' vira filtro. Se nao separar, o robo ignora algo que nao informa.")

    print("\n  operacoes exportadas em scratch/win_retangulo_tendencia_ops.csv")
    print("\nFIM.")


if __name__ == "__main__":
    main()
