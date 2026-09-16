# -*- coding: utf-8 -*-
"""WIN@ retangulo D1 -- dado o candidato de detector (tol=20%, deriva_max e
contencao_min ORIGINAIS -- achado de `win_retangulo_tol_refinamento_2026_09_15.py`:
liquido R$4.366,70 IS, 615 trades, win 45,2% vs breakeven 39,3%, sem_tr 10/129,
contra baseline R$2.834,10/403/45,7%/39,7%/33/129), este script testa DUAS
alavancas independentes do briefing do dono, SO' NO IS:

  (3) ENTRADA em OFFSET do meio, nao no meio exato. As bordas medidas tem
      ruido de 10-17% da largura (`copawin_retangulo_lateral_2026_09_15.py`)
      -- talvez o meio exato nao seja o melhor nivel de entrada. offset>0
      move a entrada para MAIS PERTO do preco atual (do lado de dentro do
      meio, precisa de MENOS "volta" para encher -> mais fills, alvo/stop
      ficam mais distantes/mais pertos respectivamente porque continuam
      ancorados no MEIO original); offset<0 move para o lado OPOSTO (mais
      longe do preco, menos fills, mas R:R melhora).

  (4) TETO DE RISCO POR OPERACAO -- seguranca. O stop e' 0,50xL e a largura
      varia a cada retangulo (risco medido: R$32 a R$110,50 por operacao na
      linha original). Testa pular a entrada (quantity=0, NAO abrir posicao)
      quando o risco projetado da operacao (stop_frac x L x R$0,20/ponto)
      excede um teto em R$ -- corta a CAUDA de perdas grandes sem mudar a
      geometria de quem entra.

Detector-base desta rodada: tol=20%, deriva_max e contencao_min ORIGINAIS
(o candidato do refinamento anterior) -- geometria D1 congelada (alvo 0,80xL,
stop 0,50xL), largura minima 328 pts, 1 contrato, capital R$650.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_offset_e_seguranca_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[apelido] = mod
    spec.loader.exec_module(mod)
    return mod


_crit = _carrega("win_retangulo_criterios_2026_09_15.py", "crit_off")
_estr = _crit._estr
_base = _crit._base
CAPITAL = _crit.CAPITAL
GEO_BASE = _crit.GEO_BASE
LARGURA_328 = _crit.LARGURA_328
RetanguloFlex = _crit.RetanguloFlex
CORTE_OOS = pd.Timestamp("2026-06-13").date()

# o candidato do refinamento anterior: SO' a tolerancia de borda muda.
TOL_CANDIDATO = 0.20


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class RetanguloOffsetSeguro(RetanguloFlex):
    """RetanguloFlex + offset de entrada + teto de risco por operacao."""

    name: str = "retangulo_offset_seguro"
    #: fracao de L: desloca a entrada do meio em direcao ao preco atual
    #: (>0) ou para o lado oposto (<0). 0 = comportamento original (entra em `meio`).
    offset_frac: float = 0.0
    #: teto de risco em R$/operacao (stop_frac x L x 0,20). inf = sem teto.
    teto_risco_brl: float = float("inf")

    def _entrada_centro(self, bar):
        r = self._ret
        meio, topo, piso, L = r["meio"], r["topo"], r["piso"], r["largura"]

        risco_brl = self.stop_frac * L * 0.20
        if risco_brl > self.teto_risco_brl:
            return None

        if bar.close < meio:
            lado, alvo_dist = "short", self.alvo_frac * (meio - piso)
            entrada = meio - self.offset_frac * L
            alvo, stop = meio - alvo_dist, meio + self.stop_frac * L
            sentido = -1
        elif bar.close > meio:
            lado, alvo_dist = "long", self.alvo_frac * (topo - meio)
            entrada = meio + self.offset_frac * L
            alvo, stop = meio + alvo_dist, meio - self.stop_frac * L
            sentido = 1
        else:
            return None
        if self.direcao_filtro:
            if len(self._hist) <= self.direcao_barras:
                return None
            var = bar.close - self._hist[-1 - self.direcao_barras].close
            if (var < 0 and sentido > 0) or (var > 0 and sentido < 0):
                return None
        return lado, entrada, alvo, stop


def _roda(dias, kw):
    from backtest.intraday.engine import run_intraday_backtest

    strat = RetanguloOffsetSeguro(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg, _corte = _base._cfg_com_folga(_estr.FOLGA_PRODUCAO, CAPITAL, strat)
    return run_intraday_backtest(bars, strat, cfg)


def _caixa_realizado(trades, capital):
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, capital
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _unidade(args):
    fase, rot, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, kw)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)
    caixa_min, maxdd_trade = _caixa_realizado(trades, CAPITAL)
    c["caixa_min"] = caixa_min
    c["maxdd_trade"] = maxdd_trade
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c["lucro_dd"] = (c["liquido"] / c["maxdd_trade"]) if c["maxdd_trade"] and c["maxdd_trade"] > 0 else float("nan")
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    c["pior_perda"] = float(min(perdas)) if perdas else 0.0
    c.pop("serie", None)
    return dict(fase=fase, rotulo=rot, c=c)


def _pc(x):
    return (br(100 * x, 1) + "%") if x == x else "--"


def _linha(rot, c):
    return (f"  {rot:<38}{br(c['liquido']):>11}{c['n']:>8}{_pc(c['win']):>7}{_pc(c['be']):>7}"
            f"{br(c['pts'],1):>8}{br(c['maxdd_trade']):>10}{br(c['lucro_dd'],2):>8}"
            f"{br(c['pior_perda']):>11}{br(c['caixa_min']):>11}{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]

    print("=" * 140)
    print("WIN@ retangulo D1 -- OFFSET DE ENTRADA e TETO DE RISCO, sobre o candidato tol=20% -- SO' NO IS")
    print("=" * 140)
    print(f"  IS: {len(IS)} pregoes | capital R$ {br(CAPITAL,0)}\n", flush=True)

    hdr = (f"  {'variante':<38}{'liquido':>11}{'trades':>8}{'win%':>7}{'be%':>7}"
           f"{'pts/op':>8}{'MaxDD':>10}{'luc/DD':>8}{'pior perda':>11}{'caixa min':>11}{'sem_tr':>9}")

    # -------------------- (3) offset de entrada -----------------------------
    OFFSETS = (-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20)
    tarefas = [("offset", f"offset {o:+.2f}xL", IS,
                dict(GEO_BASE, largura_min_pontos=LARGURA_328, tol=TOL_CANDIDATO, offset_frac=o))
               for o in OFFSETS]

    print(f"FASE OFFSET: {len(tarefas)} rodadas...\n", flush=True)
    out_offset = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out_offset[r["rotulo"]] = r["c"]

    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for o in OFFSETS:
        rot = f"offset {o:+.2f}xL"
        print(_linha(rot, out_offset[rot]))

    # -------------------- (4) teto de risco por operacao ---------------------
    TETOS = (float("inf"), 100.0, 80.0, 70.0, 60.0, 50.0)
    tarefas2 = [("teto", f"teto risco R$ {br(t,0) if t!=float('inf') else 'sem teto'}", IS,
                 dict(GEO_BASE, largura_min_pontos=LARGURA_328, tol=TOL_CANDIDATO, teto_risco_brl=t))
                for t in TETOS]

    print(f"\nFASE TETO DE RISCO: {len(tarefas2)} rodadas...\n", flush=True)
    out_teto = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas2}
        for fut in as_completed(futs):
            r = fut.result()
            out_teto[r["rotulo"]] = r["c"]

    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for t in TETOS:
        rot = f"teto risco R$ {br(t,0) if t!=float('inf') else 'sem teto'}"
        print(_linha(rot, out_teto[rot]))

    print("\nFIM.")


if __name__ == "__main__":
    main()
