# -*- coding: utf-8 -*-
"""`win_retangulo` -- POR QUE o teto de R$80 "funciona" naquela celula, e existe
teto ideal deduzivel do dado que se tem ANTES?

Pergunta do dono (2026-09-15), depois de ver que o eixo do teto de risco nao
tem estrutura: no IS R$80 e' o PIOR valor da vizinhanca R$70-120 e no OOS e'
um pico de uma celula so' (os vizinhos empatam em R$905,50).

## PARTE A -- a hipotese do mecanismo

O teto age na DETECCAO, nao na operacao. Quando ele recusa um retangulo largo,
o robo nao perde um trade: ele continua procurando e detecta OUTRO retangulo,
noutra barra, noutro lugar do grafico. A partir dali as duas linhas do tempo
divergem e nunca mais se reencontram.

Se isso for verdade, o teto **nao e' um filtro, e' um embaralhamento** -- e
entao a diferenca de liquido entre R$70 e R$80 nao mede qualidade de filtro
nenhuma, mede quais retangulos alternativos o acaso ofereceu. A previsao
testavel: entre dois tetos vizinhos, a INTERSECAO dos conjuntos de operacoes
tem de ser pequena. Um filtro de verdade produziria subconjuntos encaixados
(o teto menor opera um subconjunto do maior); um embaralhamento produz
conjuntos que mal se tocam.

## PARTE B -- a largura e' o eixo certo?

Vale lembrar o que ja foi medido nesta linha: o PISO de largura (328 pontos) e'
o unico filtro que manteve sinal e magnitude nas duas janelas, e o efeito mora
nos retangulos LARGOS. Um TETO de largura corre, portanto, na direcao contraria
ao unico achado robusto do desenho. A tabela de resultado por faixa de largura
diz se o teto esta cortando o que paga.

## PARTE C -- teto RELATIVO, deduzido do dado previo

Se um teto em R$ absoluto e' arbitrario, a pergunta do dono e' a certa: existe
uma regra que diga, a cada retangulo, qual o teto daquela situacao? Tres
candidatas, todas causais (so' olham para tras):

  1. **fracao do pregao** -- largura <= k x amplitude do pregao ate a barra de
     deteccao. Um retangulo de 800 pontos num dia de 4.000 e' normal; no mesmo
     tamanho num dia de 2.000 e' metade do dia inteiro.
  2. **quantil rolante** -- largura <= quantil q das larguras dos ultimos N
     retangulos JA detectados. Autocalibra: se o mercado inteiro alargou, o
     teto alarga junto.
  3. **fracao do caixa** -- risco <= p% do caixa (o teto absoluto de hoje,
     escrito na unidade que importa para quem opera).

A diferenca entre "achado" e "garimpo" aqui e' simples: uma regra boa tem de
ser MONOTONA ou ao menos ESTAVEL no seu proprio eixo, e concordar entre IS e
OOS. O teto absoluto falha nos dois testes. Se as tres falharem igual, a
resposta honesta e' que teto de largura nao e' alavanca -- e' so' limite de
risco, e o valor sai do caixa, nao do backtest.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_teto_mecanismo_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from strategy.daytrade.lab.win_retangulo import WinRetangulo, detecta_retangulo  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "estr_mec", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_mec"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL = 1_100.0
TETOS_ABS = (float("inf"), 120.0, 100.0, 90.0, 80.0, 70.0, 60.0)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class RetanguloTetoRelativo(WinRetangulo):
    """Mesmo robo, com as tres regras de teto candidatas.

    Tudo CAUSAL: `_amp_sessao` acumula so' as barras ja fechadas do pregao, e
    `_larguras_vistas` guarda as larguras dos retangulos JA detectados. Nenhum
    dos dois olha um minuto a frente."""

    def __init__(self, *args, regra: str = "absoluto", k: float = 0.0,
                 quantil: float = 0.0, memoria: int = 40, **kw):
        self.regra = regra
        self.k = float(k)
        self.quantil = float(quantil)
        self.memoria = int(memoria)
        self._larguras_vistas: deque = deque(maxlen=self.memoria)
        super().__init__(*args, **kw)
        self.rejeitados = 0
        self.aceitos = 0

    def _reset_sessao(self):
        super()._reset_sessao()
        self._amp_hi = -np.inf
        self._amp_lo = np.inf

    def _teto_de_largura(self) -> float:
        """Largura maxima permitida AGORA, em pontos."""
        if self.regra == "absoluto":
            denom = self.stop_fracao_largura * self.valor_do_ponto_brl * self.quantidade
            return self.risco_maximo_brl / denom if denom > 0 else np.inf
        if self.regra == "fracao_pregao":
            amp = self._amp_hi - self._amp_lo
            return self.k * amp if np.isfinite(amp) and amp > 0 else np.inf
        if self.regra == "quantil_rolante":
            if len(self._larguras_vistas) < 10:
                return np.inf          # sem amostra ainda: nao corta nada
            return float(np.quantile(np.array(self._larguras_vistas), self.quantil))
        raise ValueError(self.regra)

    def _tenta_detectar(self):
        if len(self._hist) < 3 * self.janela_barras:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior,
                                tolerancia=self.tolerancia_borda)
        if ret is None:
            return
        from strategy.daytrade.lab.win_retangulo import LARGURA_MINIMA_TICKS
        if ret["largura"] < LARGURA_MINIMA_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_minima_pontos:
            return
        # a largura entra na memoria ANTES do corte -- senao o quantil so'
        # aprenderia com o que ja passou pelo proprio quantil (realimentacao)
        self._larguras_vistas.append(ret["largura"])
        if ret["largura"] > self._teto_de_largura():
            self.rejeitados += 1
            return
        self.aceitos += 1
        self._retangulo = ret
        self._fora_seguidas = 0

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._amp_hi = max(self._amp_hi, bar.high)
        self._amp_lo = min(self._amp_lo, bar.low)
        return super().on_bar(ts, bar, positions, session_pnl_brl)


def _unidade(args):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    rotulo, janela, dias, kw = args
    strat = RetanguloTetoRelativo(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                     initial_capital=CAPITAL,
                     target_fills_as_maker=strat.target_fills_as_maker,
                     limit_fill_capped_by_volume=True,
                     queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    seq = np.array([t.pnl_brl for t in trades], dtype=float)
    c["pior"] = float(seq.min()) if len(seq) else 0.0
    c["chaves"] = {t.entry_ts.isoformat() for t in trades}
    c["rejeitados"] = strat.rejeitados
    c["aceitos"] = strat.aceitos
    # resultado por FAIXA DE LARGURA (a largura vai no `reason` da ordem)
    por_largura = []
    for t in trades:
        raz = getattr(t, "entry_reason", "") or ""
        if "_L" in raz:
            try:
                por_largura.append((float(raz.split("_L")[-1]), t.pnl_brl))
            except ValueError:
                pass
    c["por_largura"] = por_largura
    c.pop("serie", None)
    return dict(rotulo=rotulo, janela=janela, c=c)


def _linha(rot, c):
    pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
    return (f"  {rot:<28}{br(c['liquido']):>11}{c['n']:>8}{pc(c['win']):>7}"
            f"{pc(c['be']):>8}{br(c['pts'],1):>8}{br(c['pior']):>10}"
            f"{c['rejeitados']:>8}{c['aceitos']:>8}"
            f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>10}")


CAB = (f"  {'variante':<28}{'liquido':>11}{'trades':>8}{'win%':>7}{'be%':>8}"
       f"{'pts/op':>8}{'pior op.':>10}{'rejeit.':>8}{'aceitos':>8}{'sem_tr':>10}")


def main():
    df, dias_todos = _base._df()
    JAN = {"IS": [d for d in dias_todos if d < CORTE_OOS],
           "OOS": [d for d in dias_todos if d >= CORTE_OOS]}

    print("=" * 120)
    print("win_retangulo -- POR QUE o teto de R$80? E existe teto deduzivel do dado previo?")
    print("=" * 120)
    print(f"  capital R$ {br(CAPITAL,0)} (piso novo) | tol 20% | demais parametros do robo")
    print("  fila NAO calibrada para WIN@: preenche no TOQUE\n", flush=True)

    tarefas = []
    for jn, dd in JAN.items():
        for t in TETOS_ABS:
            tarefas.append((f"abs {br(t,0) if np.isfinite(t) else 'sem'}", jn, dd,
                            dict(regra="absoluto", risco_maximo_brl=t)))
        for k in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.60):
            tarefas.append((f"pregao k={br(k,2)}", jn, dd,
                            dict(regra="fracao_pregao", k=k,
                                 risco_maximo_brl=float("inf"))))
        for q in (0.50, 0.60, 0.70, 0.80, 0.90):
            tarefas.append((f"quantil q={br(q,2)}", jn, dd,
                            dict(regra="quantil_rolante", quantil=q,
                                 risco_maximo_brl=float("inf"))))

    out = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["rotulo"], r["janela"])] = r["c"]
            feitos += 1
            if feitos % 10 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    # -------------------------------------------------------------- PARTE A
    print("\n" + "=" * 120)
    print("(A) O TETO E' FILTRO OU EMBARALHAMENTO?")
    print("=" * 120)
    print("  Se fosse FILTRO, o conjunto de operacoes de um teto menor seria")
    print("  SUBCONJUNTO do maior (contido = 100%). Se for EMBARALHAMENTO, as")
    print("  duas linhas do tempo divergem e a intersecao desaba.\n")
    for jn in JAN:
        base = out[("abs sem", jn)]["chaves"]
        print(f"  --- {jn} ---")
        print(f"  {'teto':>10}{'trades':>8}{'iguais ao sem teto':>22}"
              f"{'contido no sem teto':>22}{'so nele':>10}")
        for t in TETOS_ABS[1:]:
            rot = f"abs {br(t,0)}"
            ch = out[(rot, jn)]["chaves"]
            inter = len(base & ch)
            print(f"  {br(t,0):>10}{len(ch):>8}{inter:>22}"
                  f"{(br(100*inter/max(1,len(ch)),1)+'%'):>22}{len(ch-base):>10}")
        print()

    # -------------------------------------------------------------- PARTE B
    print("=" * 120)
    print("(B) A LARGURA E' O EIXO CERTO? -- resultado por faixa de largura, SEM teto")
    print("=" * 120)
    for jn in JAN:
        pl = out[("abs sem", jn)]["por_largura"]
        if not pl:
            print(f"  {jn}: sem dado de largura por operacao")
            continue
        larg = np.array([p[0] for p in pl])
        pnl = np.array([p[1] for p in pl])
        cortes = [328, 450, 550, 650, 800, 1000, np.inf]
        print(f"  --- {jn} ({len(pl)} operacoes) ---")
        print(f"  {'faixa de largura':<22}{'n':>7}{'R$/op':>10}{'win%':>8}{'soma R$':>12}")
        for a, b in zip(cortes[:-1], cortes[1:]):
            m = (larg >= a) & (larg < b)
            if m.sum() == 0:
                continue
            rot = f"{a:.0f}-{b:.0f} pts" if np.isfinite(b) else f"{a:.0f}+ pts"
            print(f"  {rot:<22}{int(m.sum()):>7}{br(pnl[m].mean()):>10}"
                  f"{(br(100*(pnl[m]>0).mean(),1)+'%'):>8}{br(pnl[m].sum()):>12}")
        print()

    # -------------------------------------------------------------- PARTE C
    print("=" * 120)
    print("(C) AS TRES REGRAS DE TETO -- o eixo tem estrutura, ou e' ruido?")
    print("=" * 120)
    grupos = [("TETO ABSOLUTO em R$", [f"abs {br(t,0) if np.isfinite(t) else 'sem'}"
                                       for t in TETOS_ABS]),
              ("TETO = k x AMPLITUDE DO PREGAO ate agora",
               [f"pregao k={br(k,2)}" for k in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.60)]),
              ("TETO = quantil ROLANTE das larguras ja vistas",
               [f"quantil q={br(q,2)}" for q in (0.50, 0.60, 0.70, 0.80, 0.90)])]
    for titulo, rots in grupos:
        for jn in JAN:
            print(f"\n  ### {titulo} -- {jn}")
            print(CAB)
            for rot in rots:
                print(_linha(rot, out[(rot, jn)]))

    # -------------------------------------------------------------- veredito
    print("\n" + "=" * 120)
    print("CONCORDANCIA IS x OOS -- qual regra ORDENA igual nas duas janelas?")
    print("=" * 120)
    for titulo, rots in grupos:
        li = [out[(r, "IS")]["liquido"] for r in rots]
        lo = [out[(r, "OOS")]["liquido"] for r in rots]
        rho = float(pd.Series(li).rank().corr(pd.Series(lo).rank()))
        melhor_is = rots[int(np.argmax(li))]
        melhor_oos = rots[int(np.argmax(lo))]
        print(f"  {titulo:<45} correlacao de POSTO IS x OOS: {br(rho,2):>7}")
        print(f"  {'':<45} melhor no IS: {melhor_is:<18} melhor no OOS: {melhor_oos}")
    print("\n  Correlacao de posto perto de 0 (ou negativa) = o eixo nao carrega")
    print("  informacao: a ordem das celulas numa janela nao diz nada sobre a outra.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
