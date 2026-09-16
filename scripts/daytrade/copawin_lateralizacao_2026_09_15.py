# -*- coding: utf-8 -*-
"""copa_win: o robo consegue ver LATERALIZACAO -- e deixar de operar nela paga?

## A pergunta do dono (2026-09-15)

"O sistema consegue identificar lateralizacao do mercado? Em varios minutos?
Podemos medir para descobrir quais sao os resultados quando se opera em
lateralizacao." E, na sequencia: "teste a hipotese de nao operar quando
identificar lateralizacao."

Resposta da primeira parte, antes de qualquer medicao: hoje NAO. O unico
portao de mercado do `copa_win` e' `vol_min_ticks=8`, que e' um PISO DE
AMPLITUDE (`_volatilidade()` = amplitude MEDIA das barras da faixa). Amplitude
nao e' lateralizacao -- e' justamente a medida que CONFUNDE os dois regimes:

    amplitude ALTA + deslocamento ALTO  = tendencia forte
    amplitude ALTA + deslocamento BAIXO = LATERALIZACAO violenta

O robo ja calcula os DOIS ingredientes da razao que os separa, na MESMA janela
de 10 barras, e nunca divide um pelo outro:

    caminho       = soma(high - low) da faixa   (= `_volatilidade()` x 10)
    deslocamento  = max(high) - min(low)        (= `teto_faixa - piso_faixa`)

## As medidas

1. `comp_faixa` = deslocamento / caminho, sobre a PROPRIA faixa de 10 barras do
   robo. Vive em (0, 1]: perto de 1 a faixa inteira foi percorrida numa
   direcao; perto de 0 o preco fez o mesmo caminho indo e voltando. E' a
   informacao que o robo ja tem em maos e joga fora.

2. `|ER_N|` -- razao de eficiencia de Kaufman sobre fechamentos de MINUTO,
   N in {10, 20, 30, 60} minutos antes do sinal, mais a janela desde a
   abertura do pregao ("varios minutos", pedido do dono):

       ER_N = (fecha[ts] - fecha[ts-N]) / soma(|variacoes minuto a minuto|)

   Vive em [-1, +1]; o SINAL e' direcao, o MODULO e' o regime. |ER| perto de 0
   e' lateralizacao. Mesma regua ja usada no repo em
   `wdof1_tendencia_confirmacao_2026_08_28.py` e no
   `wdo_orb_lateralizacao_2026_09_15.py` (outro robo, mesma pergunta).

ARMADILHA declarada antes de medir: a janela de 10 minutos e' PARCIALMENTE
COLINEAR com o proprio sinal -- o rompimento e' definido sobre essa mesma
faixa, entao um sinal so' existe se o preco saiu dela. A informacao NOVA esta'
nas janelas largas (30 e 60) e em `comp_faixa`, que e' razao, nao amplitude.
Segunda armadilha ja medida: `vol_ref` SOZINHO (a amplitude) foi testado em
`copawin_preditor_stop_2026_09_15.py` e nao sobrevive -- o ponto aqui e' a
RAZAO, nunca a amplitude.

## O indicio que motivou (e que NAO conta como evidencia)

`copawin_anatomia_1a_entrada_2026_09_15.py`: a 1a operacao do dia rompe a faixa
mais LATERAL de todas (eficiencia 0,272) e e' a que mais estopa (P(stop)
18,8%); a 3a rompe a faixa mais direcional (0,360) e estopa 5,6%. Isso gerou a
hipotese; a hipotese nao pode ser testada no mesmo numero que a gerou.

## Fase 1 -- DESCRITIVA (quais sao os resultados quando se opera em lateral?)

Uma rodada CONTINUA de 191 pregoes (o caixa nao reseta, mesma convencao de
`copawin_preditor_stop_2026_09_15.py`, com a mesma conferencia de arranque:
564 trades / 58 stops). Cada sinal carrega as medidas do instante em que foi
emitido. Tercos congelados no IS e aplicados ao OOS -- recalcular o terco
dentro de cada janela testaria "abaixo do terco local", que e' outro criterio.

## Fase 2 -- A HIPOTESE DO DONO: nao operar quando identificar lateralizacao

Nao e' contrafactual: e' backtest de verdade, com a entrada BLOQUEADA quando a
medida fica abaixo do limiar. O bloqueio passa pelo portao que o robo JA TEM
(`vol_min_ticks`), que e' checado antes de `_entrada` e nao consome
`max_entradas_dia` nem o prazo da ordem -- ou seja, o robo simplesmente nao
emite aquele sinal e segue vivo para o proximo. Como o motor nao piramida,
bloquear uma entrada LIBERA o robo para entrar depois no mesmo pregao: o efeito
medido aqui e' o efeito INTEIRO, nao um piso (ao contrario dos contrafactuais
de gestao de posicao medidos hoje).

Se a medida for indefinida no instante (historia curta demais), o robo NAO e'
bloqueado -- "nao consegui identificar" nao e' "e' lateral".

CRITERIO CONGELADO ANTES DE VER O NUMERO: o filtro so' conta se o liquido
melhorar no IS **e** no OOS. Melhora em uma so' janela e' sign-flip, que ja
matou o filtro dia/hora, os 7 sinais de timing, os 5 ajustes estruturais, o
filtro de agitacao do wdo_orb e as 24 regras de gestao do proprio copa_win.

RESSALVAS:
  - WIN@ nao tem fila calibrada em `fidelidade.py` (so' WDO@) -- toda linha
    assume preenchimento no TOQUE. Carimbado na tabela.
  - O OOS do WIN@ ja foi gasto varias vezes; nao e' teste cego.
  - Config de PRODUCAO importada de `registry._KWARGS_PADRAO['copa_win']`,
    nunca redigitada; corte de achatamento de producao (folga 5min).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_lateralizacao_2026_09_15.py`
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

_spec = importlib.util.spec_from_file_location(
    "_base_lat", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL                 # R$3.000 -- o que o slot usa hoje
SYMBOL = _base.SYMBOL                   # WIN@
FOLGA_PRODUCAO = 5                      # corte de achatamento de producao
CORTE_OOS = pd.Timestamp("2026-06-13").date()
SCRATCH = ROOT / "scratch"

#: conferencia contra o FATO ja medido (rodada CONTINUA de 191 pregoes,
#: `copawin_onde_perde_2026_09_14.log`, tabela HISTORICO COMPLETO).
FATO_TRADES, FATO_STOPS = 564, 58

#: "varios minutos" -- as janelas de retrovisor do ER, em minutos.
LOOKBACKS = (10, 20, 30, 60)
#: minimo de fechamentos de minuto para a janela valer. Abaixo disso o ER e'
#: ruido de 2 pontos, e chutar 0 seria AFIRMAR "nao ha direcao".
MIN_MINUTOS = 5

#: as medidas que viram PORTAO na fase 2. `aber_10` entra apesar da
#: colinearidade declarada na docstring -- se ela vencer as largas, isso ja e'
#: o diagnostico de que o filtro esta' lendo o proprio sinal.
MEDIDAS_PORTAO = ("comp_faixa", "aber_10", "aber_30", "aber_60")
#: quantis da distribuicao IS dos sinais -- congelados la' e aplicados igual
#: nas tres janelas. Bloqueia quem fica ABAIXO (mais lateral).
QUANTIS_PORTAO = (0.20, 0.33, 0.50)


def br(v, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def er_kaufman(closes) -> float:
    """Razao de eficiencia COM sinal. `nan` quando a janela e' curta demais ou
    o caminho e' zero (preco literalmente parado: indefinido, nao 0)."""
    c = np.asarray(closes, dtype=float)
    if len(c) < MIN_MINUTOS:
        return float("nan")
    caminho = float(np.abs(np.diff(c)).sum())
    if caminho <= 0.0:
        return float("nan")
    return float((c[-1] - c[0]) / caminho)


# ---------------------------------------------------------------------------
# a estrategia com a lente de lateralizacao
#
# `_LenteLateral` so' ACRESCENTA historico e medidas -- nenhuma decisao muda
# (fase 1). O portao da fase 2 vive na subclasse `_ComPortao`, e e' aplicado
# levantando temporariamente `vol_min_ticks`, que e' o portao de mercado que o
# proprio robo ja tem: checado ANTES de `_entrada`, nao consome
# `max_entradas_dia` nem o prazo da ordem de reteste, e deixa o `finally` do
# `on_bar` alimentar a faixa normalmente.
# ---------------------------------------------------------------------------

def _classes():
    from strategy.daytrade.lab.copa_win import CopaWin

    class _LenteLateral(CopaWin):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._log_sinais: list[dict] = []
            self._hist_ts: deque = deque(maxlen=600)
            self._hist_close: deque = deque(maxlen=600)
            self._ts_atual = None

        def on_session_start(self, session_date) -> None:
            # nenhum nivel de preco atravessa a virada -- mesma regra do robo
            super().on_session_start(session_date)
            self._hist_ts.clear()
            self._hist_close.clear()

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            # a barra corrente ja FECHOU quando a decisao e' tomada, entao ela
            # entra no retrovisor; e' a faixa (`_faixa`) que nao pode conte-la.
            self._ts_atual = ts
            self._hist_ts.append(pd.Timestamp(ts))
            self._hist_close.append(float(bar.close))
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        # -- medidas -------------------------------------------------------
        def _comp_faixa(self) -> float:
            """deslocamento / caminho na propria faixa de 10 barras do robo."""
            if len(self._faixa) < self.janela_rompimento:
                return float("nan")
            caminho = sum(b.high - b.low for b in self._faixa)
            if caminho <= 0:
                return float("nan")
            desloc = max(b.high for b in self._faixa) - min(b.low for b in self._faixa)
            return float(desloc / caminho)

        def _er(self, minutos: int) -> float:
            if not self._hist_ts:
                return float("nan")
            limite = self._hist_ts[-1] - pd.Timedelta(minutes=minutos)
            janela = [c for t, c in zip(self._hist_ts, self._hist_close) if t >= limite]
            return er_kaufman(janela)

        def _medidas(self) -> dict:
            d = {"comp_faixa": self._comp_faixa()}
            for n in LOOKBACKS:
                er = self._er(n)
                d[f"er_{n}"] = er
                d[f"aber_{n}"] = abs(er) if er == er else float("nan")
            er_ab = er_kaufman(list(self._hist_close))
            d["er_abertura"] = er_ab
            d["aber_abertura"] = abs(er_ab) if er_ab == er_ab else float("nan")
            return d

        # -- log do sinal (nao muda decisao) --------------------------------
        def _entrada(self, lado, preco, nivel_rompido, vol):
            acao = super()._entrada(lado, preco, nivel_rompido, vol)
            reg = dict(sinal_ts=self._ts_atual, lado=lado,
                       vol_ref=vol, barras_hoje=self._barras_hoje)
            reg.update(self._medidas())
            self._log_sinais.append(reg)
            return acao

    class _ComPortao(_LenteLateral):
        """Nao opera quando a medida escolhida fica ABAIXO do limiar."""

        def __init__(self, *a, medida: str = "comp_faixa",
                     limiar: float = float("-inf"), **kw):
            super().__init__(*a, **kw)
            self.medida_portao = medida
            self.limiar_portao = float(limiar)
            # contagem de BARRAS em que o portao vetou abrir posicao -- nao e' o
            # numero de sinais suprimidos (a maioria dessas barras nao romperia a
            # faixa de qualquer jeito). O numero que mede supressao de verdade e' a
            # coluna `trades` da tabela, contra a linha de producao.
            self.barras_vetadas = 0

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._ts_atual = ts
            self._hist_ts.append(pd.Timestamp(ts))
            self._hist_close.append(float(bar.close))

            bloquear = False
            if not positions:
                v = self._medidas().get(self.medida_portao, float("nan"))
                # medida indefinida => "nao consegui identificar", que NAO e'
                # "e' lateral": o robo segue com o comportamento de producao.
                bloquear = (v == v) and (v < self.limiar_portao)

            original = self.vol_min_ticks
            if bloquear:
                self.barras_vetadas += 1
                self.vol_min_ticks = float("inf")
            try:
                # `super()` de `_LenteLateral` reempilharia a barra no
                # historico; por isso vamos direto ao `CopaWin.on_bar`.
                return CopaWin.on_bar(self, ts, bar, positions, session_pnl_brl)
            finally:
                self.vol_min_ticks = original

    return _LenteLateral, _ComPortao


def _kwargs_producao() -> dict:
    from strategy.daytrade.registry import _KWARGS_PADRAO
    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    return kwargs


def _roda(dias: list, medida: str | None = None, limiar: float = float("-inf")):
    """Um backtest sobre `dias`, com ou sem portao. Caixa parte de R$3.000."""
    from backtest.intraday.engine import run_intraday_backtest

    lente, com_portao = _classes()
    kwargs = _kwargs_producao()
    strat = (lente(**kwargs) if medida is None
             else com_portao(medida=medida, limiar=limiar, **kwargs))
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg, _corte = _base._cfg_com_folga(FOLGA_PRODUCAO, CAPITAL, strat)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


# ---------------------------------------------------------------------------
# FASE 1 -- descritiva
# ---------------------------------------------------------------------------

def _tabela_sinais(res, strat) -> pd.DataFrame:
    """Uma linha por TRADE, com as medidas do instante do SINAL.

    Casamento por ponteiro monotonico (sinais e trades sao ambos crescentes no
    tempo e o robo tem uma posicao por vez), mesma rotina de
    `copawin_preditor_stop_2026_09_15.montar_tabela`."""
    trades = sorted(res.trades, key=lambda t: t.entry_ts)
    sinais = sorted(strat._log_sinais, key=lambda o: o["sinal_ts"])
    i = 0
    linhas = []
    for t in trades:
        while i + 1 < len(sinais) and sinais[i + 1]["sinal_ts"] <= t.entry_ts:
            i += 1
        if not sinais or sinais[i]["sinal_ts"] > t.entry_ts:
            continue
        s = sinais[i]
        razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                 else str(t.exit_reason))
        d = t.entry_ts.date()
        linha = dict(data=d, janela=("IS" if d < CORTE_OOS else "OOS"),
                     lado=s["lado"], pnl_brl=t.pnl_brl,
                     venceu=int(t.pnl_brl > 0), stop=int(razao == "stop"),
                     saida=razao)
        for k, v in s.items():
            if k not in ("sinal_ts", "lado"):
                linha[k] = v
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _por_faixa(df: pd.DataFrame, col: str, cortes: tuple[float, float]) -> pd.DataFrame:
    def balde(v):
        if v != v:
            return "indefinido"
        if v <= cortes[0]:
            return "1-lateral"
        if v <= cortes[1]:
            return "2-meio"
        return "3-direcional"

    d = df.copy()
    d["balde"] = d[col].map(balde)
    linhas = []
    for nome in sorted(d.balde.unique()):
        s = d[d.balde == nome]
        linhas.append({
            "faixa": nome, "n": len(s),
            "liquido": round(s.pnl_brl.sum(), 2),
            "rs_por_op": round(s.pnl_brl.mean(), 2),
            "win_pct": round(100 * s.venceu.mean(), 1),
            "stop_pct": round(100 * s.stop.mean(), 1),
        })
    return pd.DataFrame(linhas)


def fase1():
    print("=" * 108)
    print("FASE 1 -- DESCRITIVA: quais sao os resultados quando o copa_win opera em LATERALIZACAO?")
    print("=" * 108, flush=True)
    res, strat = _roda(_base._df()[1])
    trades = list(res.trades)
    stops = sum(1 for t in trades
                if (t.exit_reason.value if hasattr(t.exit_reason, "value")
                    else str(t.exit_reason)) == "stop")
    print(f"  rodada CONTINUA: trades={len(trades)}  stops={stops}  "
          f"sinais logados={len(strat._log_sinais)}")
    if (len(trades), stops) != (FATO_TRADES, FATO_STOPS):
        print(f"  [ATENCAO] nao bateu com o FATO ja medido ({FATO_TRADES} trades / "
              f"{FATO_STOPS} stops). LEIA tudo abaixo com essa ressalva.")
    else:
        print("  CONFERENCIA OK -- a lente nao mexeu em nenhuma decisao.")

    tab = _tabela_sinais(res, strat)
    tab.to_csv(SCRATCH / "copawin_lateralizacao_trades.csv", index=False, encoding="utf-8")
    is_ = tab[tab.janela == "IS"]
    oos = tab[tab.janela == "OOS"]
    print(f"  {len(tab)} trades casados com sinal -> scratch/copawin_lateralizacao_trades.csv"
          f"   (IS {len(is_)} / OOS {len(oos)})")

    medidas = [("comp_faixa", "compacidade da faixa (10 barras do robo)")]
    medidas += [(f"aber_{n}", f"|ER| {n}min") for n in LOOKBACKS]
    medidas += [("aber_abertura", "|ER| desde a abertura")]

    print("\n  distribuicao das medidas no instante do SINAL (IS, n=%d):" % len(is_))
    hdr = f"    {'medida':<42}{'n':>6}{'p10':>9}{'q33':>9}{'mediana':>9}{'q67':>9}{'p90':>9}"
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    cortes = {}
    for col, rot in medidas:
        v = is_[col].dropna()
        cortes[col] = ((float(v.quantile(1 / 3)), float(v.quantile(2 / 3)))
                       if len(v) >= 30 else (float("nan"), float("nan")))
        print(f"    {rot:<42}{len(v):>6}{br(v.quantile(.10), 3):>9}"
              f"{br(v.quantile(1/3), 3):>9}{br(v.median(), 3):>9}"
              f"{br(v.quantile(2/3), 3):>9}{br(v.quantile(.90), 3):>9}")

    print("\n  RESULTADO POR FAIXA -- tercos CONGELADOS NO IS e aplicados igual ao OOS")
    print("  (faixa '1-lateral' = o terco mais lateral da medida)")
    veredito = []
    for col, rot in medidas:
        if cortes[col][0] != cortes[col][0]:
            continue
        print(f"\n  --- {rot}   (cortes IS: {br(cortes[col][0], 3)} / {br(cortes[col][1], 3)}) ---")
        deltas = {}
        for nome, sub in (("IS", is_), ("OOS", oos)):
            t = _por_faixa(sub, col, cortes[col])
            t.insert(0, "janela", nome)
            print(t.to_string(index=False))
            lat = t[t.faixa == "1-lateral"]
            dir_ = t[t.faixa == "3-direcional"]
            deltas[nome] = ((float(lat.rs_por_op.iloc[0]) - float(dir_.rs_por_op.iloc[0]))
                            if len(lat) and len(dir_) else float("nan"))
        veredito.append({"medida": rot,
                         "IS_lat_menos_dir": round(deltas.get("IS", float("nan")), 2),
                         "OOS_lat_menos_dir": round(deltas.get("OOS", float("nan")), 2)})

    print("\n" + "=" * 108)
    print("OPERAR EM LATERAL E' PIOR? (R$/op do terco LATERAL menos o do terco DIRECIONAL)")
    print("  negativo nas DUAS janelas = lateral e' de fato o terco ruim; sinal trocado entre")
    print("  IS e OOS REFUTA a leitura, e nenhum portao da fase 2 deveria funcionar.")
    print("=" * 108)
    v = pd.DataFrame(veredito)
    v["mesmo_sentido"] = np.where(
        (v.IS_lat_menos_dir < 0) & (v.OOS_lat_menos_dir < 0), "LATERAL PIOR nas duas",
        np.where((v.IS_lat_menos_dir > 0) & (v.OOS_lat_menos_dir > 0),
                 "lateral MELHOR nas duas", "INVERTE"))
    print(v.to_string(index=False))
    v.to_csv(SCRATCH / "copawin_lateralizacao_sentido.csv", index=False, encoding="utf-8")

    limiares = {}
    for col in MEDIDAS_PORTAO:
        s = is_[col].dropna()
        limiares[col] = {q: float(s.quantile(q)) for q in QUANTIS_PORTAO} if len(s) >= 30 else {}
    return tab, limiares


# ---------------------------------------------------------------------------
# FASE 2 -- a hipotese do dono: nao operar quando identificar lateralizacao
# ---------------------------------------------------------------------------

def _unidade(args):
    janela_nome, dias, medida, limiar, rotulo = args
    buf = StringIO()
    with redirect_stdout(buf):
        res, strat = _roda(dias, medida, limiar)
    c = _base.consistencia(list(res.trades), dias)
    return dict(janela=janela_nome, rotulo=rotulo, res=res, c=c,
                barras_vetadas=getattr(strat, "barras_vetadas", 0))


def fase2(limiares: dict):
    from backtest.intraday.report import linha_de_resultado, tabela

    df, dias = _base._df()
    janelas = {
        "IS (<2026-06-13)": [d for d in dias if d < CORTE_OOS],
        "OOS (>=2026-06-13)": [d for d in dias if d >= CORTE_OOS],
        "HISTORICO COMPLETO": dias,
    }
    variantes = [("producao (sem filtro)", None, float("-inf"))]
    for col in MEDIDAS_PORTAO:
        for q in QUANTIS_PORTAO:
            if q in limiares.get(col, {}):
                variantes.append((f"corta {col} < q{int(q*100)} ({br(limiares[col][q], 3)})",
                                  col, limiares[col][q]))

    tarefas = [(jn, dias_j, med, lim, rot)
               for jn, dias_j in janelas.items()
               for rot, med, lim in variantes]

    print("\n\n" + "=" * 108)
    print("FASE 2 -- NAO OPERAR QUANDO IDENTIFICAR LATERALIZACAO (backtest de verdade, nao contrafactual)")
    print("=" * 108)
    print(f"{len(variantes)} variantes x {len(janelas)} janelas = {len(tarefas)} rodadas. "
          f"Limiares CONGELADOS na distribuicao IS dos sinais (fase 1).")
    print("Criterio congelado: so' conta quem melhora o liquido no IS E no OOS.\n", flush=True)

    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["janela"], {})[r["rotulo"]] = r
            c = r["c"]
            print(f"  {r['janela']:<22}{r['rotulo']:<40} liquido={br(c['liquido']).rjust(12)}"
                  f"  trades={c['n']:>5}  sem_trade={c['sem_trade']:>3}d"
                  f"  barras_vetadas={r['barras_vetadas']:>6}", flush=True)

    EXTRAS = ("preg+", "bl20+", "mes+", "seq-", "BEemp%", "veredito", "sem_tr", "bloqB")
    for jn, dias_j in janelas.items():
        print(f"\n\n===== WIN@, R$ {br(CAPITAL, 0)} -- {jn} ({len(dias_j)} pregoes) =====")
        linhas = []
        for rot, _m, _l in variantes:
            r = out[jn][rot]
            c = r["c"]
            extras = {
                "preg+": (br(100 * c["frac_preg"], 0) + "%") if c["frac_preg"] == c["frac_preg"] else "--",
                "bl20+": (br(100 * c["frac_bl"], 0) + "%") if c["frac_bl"] == c["frac_bl"] else "--",
                "mes+": (br(100 * c["frac_mes"], 0) + "%") if c["frac_mes"] == c["frac_mes"] else "--",
                "seq-": str(c["seq_neg"]),
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "veredito": c["veredito"],
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
                "bloqB": str(r["barras_vetadas"]),
            }
            linhas.append(linha_de_resultado(rot, r["res"], CAPITAL, extras=extras))
        print(tabela(linhas, extras=EXTRAS))

    print("\n\n" + "=" * 108)
    print("VEREDITO -- delta de liquido contra a producao, nas DUAS janelas cegas")
    print("=" * 108)
    base_is = out["IS (<2026-06-13)"]["producao (sem filtro)"]["c"]["liquido"]
    base_oos = out["OOS (>=2026-06-13)"]["producao (sem filtro)"]["c"]["liquido"]
    hdr = (f"  {'variante':<40}{'d IS':>13}{'d OOS':>13}{'trades IS':>11}"
           f"{'trades OOS':>12}{'veredito':>24}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    passou = []
    for rot, med, _l in variantes:
        if med is None:
            continue
        ci = out["IS (<2026-06-13)"][rot]["c"]
        co = out["OOS (>=2026-06-13)"][rot]["c"]
        di, do = ci["liquido"] - base_is, co["liquido"] - base_oos
        ok = di > 0 and do > 0
        if ok:
            passou.append(rot)
        print(f"  {rot:<40}{br(di):>13}{br(do):>13}{ci['n']:>11}{co['n']:>12}"
              f"{('MELHORA nas duas' if ok else 'nao passa'):>24}")
    print()
    if passou:
        print(f"  {len(passou)} de {len(variantes)-1} celulas melhoram nas DUAS janelas: {passou}")
        print("  A 5%, 12 celulas produzem ~0,6 positivo falso por acaso -- uma celula isolada")
        print("  num canto da grade ainda e' suspeita. Olhe se as vizinhas (mesma medida, quantil")
        print("  adjacente) acompanham: efeito real e' MONOTONICO na grade, ruido e' pontual.")
    else:
        print(f"  NENHUMA das {len(variantes)-1} celulas melhora o liquido nas duas janelas.")
        print("  A hipotese 'nao operar em lateralizacao' esta' REFUTADA para o copa_win no")
        print("  desenho de producao -- a lateralizacao e' visivel (fase 1 mede), mas cortar")
        print("  o terco lateral nao paga.")
    print("\nRESSALVA: WIN@ sem fila calibrada (fidelidade.py so' tem WDO@) -- preenchimento no")
    print("TOQUE em toda linha. OOS do WIN@ ja foi gasto varias vezes; nao e' teste cego.\n\nFIM.")


def main() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    df, dias = _base._df()
    print("=" * 108)
    print("copa_win -- LATERALIZACAO: medir, e testar NAO OPERAR nela (WIN@, R$3.000, producao)")
    print("=" * 108)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]}), "
          f"corte IS/OOS em {CORTE_OOS}, folga de achatamento {FOLGA_PRODUCAO}min (producao).")
    print("config vinda de registry._KWARGS_PADRAO['copa_win'] -- janela_rompimento=10, "
          "vol_min_ticks=8 (piso de AMPLITUDE, nao de regime).\n", flush=True)
    _tab, limiares = fase1()
    fase2(limiares)


if __name__ == "__main__":
    main()
