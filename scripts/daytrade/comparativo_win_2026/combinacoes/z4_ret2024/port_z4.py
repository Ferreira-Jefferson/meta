# -*- coding: utf-8 -*-
"""Z4: wrapper (monkeypatch, sem editar o port) de y_tempos/retangulo/y4b/port_ret_tf_v2.py, M15, ajustes=True.

O que o wrapper faz, e so' isso:
  1. No momento em que o port ARMA a ordem-limite de entrada (processar_barra cria um `pend` novo), calcula o contexto
     conhecido naquele instante (vela M15 que acabou de fechar e tudo antes dela) e guarda no `pend`.
  2. Se um filtro foi passado e ele recusa o contexto, o `pend` e' descartado ali mesmo: a ordem nao e' armada, e o EA
     tenta armar de novo na vela seguinte (como faria um filtro dentro do EA). Isso reproduz o efeito "uma posicao por vez":
     remover uma entrada pode liberar outra depois.
  3. Quando a ordem enche, o contexto passa para a posicao; quando a posicao fecha, o contexto vai para a linha da operacao.
Sem filtro, as operacoes sao identicas as de trades/rettf_M15_*.csv (conferido em roda_z4.py --confere).

Instante da decisao: t_arm = fim da vela M15 fechada (abertura + 15 min). Todo contexto usa so' barras com fim <= t_arm
(M15, H1) ou pregoes anteriores (D1). Nada do futuro.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
COMB = AQUI.parent
BASE = COMB.parent  # comparativo_win_2026
Y4B = COMB / "y_tempos" / "retangulo" / "y4b"
TF = 15
BMS = TF * 60000


def prepara(periodo: str):
    """Seleciona o modulo `dados` certo ANTES de importar o port (como run_y4b.py). Devolve (dados, port)."""
    if periodo == "2022_2025":
        os.environ["DADOS_VAL_MODO"] = "continuo"
        sys.path.insert(0, str(COMB / "x_fixas" / "x0"))
        import dados_val
        sys.modules["dados"] = dados_val
        dados = dados_val
    else:
        sys.path.insert(0, str(BASE))
        import dados
    sys.path.insert(0, str(Y4B))
    import port_ret_tf_v2 as P
    return dados, P


def _tr(h, l, c):
    pc = np.r_[np.nan, c[:-1]]
    return np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)


class Contexto:
    """Series pre-calculadas do M1 (so' para consulta por instante; cada consulta usa apenas o que fechou antes)."""

    def __init__(self, m1: pd.DataFrame):
        t1 = m1.index.values.astype("datetime64[ms]").astype(np.int64)
        # M15 (meia-noite alinhada, como o port)
        k = t1 // BMS
        g = m1.groupby(k).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
        self.m15_fim = g.index.values.astype(np.int64) * BMS + BMS
        self.m15_atr = pd.Series(_tr(g.h.values, g.l.values, g.c.values)).rolling(14).mean().values
        # H1 e EMA34 H1
        kh = t1 // 3600000
        gh = m1.groupby(kh).agg(c=("close", "last"))
        self.h1_fim = gh.index.values.astype(np.int64) * 3600000 + 3600000
        self.h1_ema = gh.c.ewm(span=34, adjust=False).mean().values
        # D1
        d = m1.index.normalize()
        gd = m1.groupby(d).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
        atr = pd.Series(_tr(gd.h.values, gd.l.values, gd.c.values)).rolling(14).mean().values
        self.d_dia = gd.index.values.astype("datetime64[ms]").astype(np.int64)  # meia-noite do dia
        self.d_atr_ant = np.r_[np.nan, atr[:-1]]         # ATR14 D1 ate' o pregao ANTERIOR
        self.d_open = gd.o.values
        self.d_close_ant = np.r_[np.nan, gd.c.values[:-1]]
        # para maxima/minima do dia ate' t_arm: M1 por dia
        self.t1 = t1
        self.h1v = m1.high.values
        self.l1v = m1.low.values

    def calcula(self, t_arm, c, lado, larg, meio, ema15):
        i = np.searchsorted(self.m15_fim, t_arm, "right") - 1
        atr15 = float(self.m15_atr[i]) if i >= 0 else np.nan
        j = np.searchsorted(self.h1_fim, t_arm, "right") - 1
        ema_h1 = float(self.h1_ema[j]) if j >= 0 else np.nan
        dia0 = (t_arm // 86400000) * 86400000
        di = np.searchsorted(self.d_dia, dia0)
        atr_d = float(self.d_atr_ant[di]); op = float(self.d_open[di]); cant = float(self.d_close_ant[di])
        a = np.searchsorted(self.t1, dia0); b = np.searchsorted(self.t1, t_arm - 60000, "right")  # M1 fechadas ate' t_arm
        hi = float(self.h1v[a:b].max()); lo = float(self.l1v[a:b].min())
        var_dia = (c - op) / atr_d
        return dict(
            t_arm=int(t_arm), hora_arm=((t_arm // 60000) % 1440) / 60.0, lado_arm=int(lado), larg=float(larg),
            larg_atr15=larg / atr15, larg_atrd=larg / atr_d, atr15=atr15, atr_d=atr_d,
            atr15_atrd=atr15 / atr_d,
            var_dia_atrd=var_dia,                                  # abertura -> close da vela de decisao, em ATR D1
            tend_alinh=int(np.sign(var_dia) * lado),               # +1 entrada a favor da variacao do dia
            h1_lado=int(np.sign(c - ema_h1)),                      # lado do close vs EMA34 H1 (ultima H1 fechada)
            h1_alinh=int(np.sign(c - ema_h1) * lado),
            dist_h1_atrd=(c - ema_h1) / atr_d,
            dist_ema15_pts=float((c - ema15) * lado), dist_ema15_atr15=float((c - ema15) * lado / atr15),
            gap_atrd=(op - cant) / atr_d,
            faixa_dia_atrd=(hi - lo) / atr_d,                       # amplitude do pregao ate' t_arm
            c_vs_meio=float((c - meio) * lado),
        )


POS_MIN = 18 * 60 + 25   # vela que ABRE depois das 18:25 = pos-pregao (no WIN$N 2026: 1 tick isolado as ~18:30 por dia)
CONTA_POS = {}           # ano -> velas pos-pregao que entraram no historico do detector


def _ticks_sem_pos(ticks0):
    """dados.ticks sem os ticks de abertura de vela >= 18:30 (o 18:30 isolado do WIN$N; o WINV26 real termina 18:27)."""
    def ticks(dia):
        t, p, v, r = ticks0(dia)
        ok = (t // 60000) % 1440 < 18 * 60 + 30
        return t[ok], p[ok], v[ok], r
    return ticks


def instala(P, dados, filtro=None, sem_pos=False):
    """Monkeypatch na classe Ea do port. filtro(ctx: dict) -> bool (True = arma). sem_pos: tira o tick pos-pregao."""
    if sem_pos:
        dados.ticks = _ticks_sem_pos(dados.ticks)
    ctx = Contexto(dados.m1())
    proc0, avanca0, fecha0, det0 = P.Ea.processar_barra, P.Ea.avanca, P.Ea._fecha, P.Ea._detecta
    P.Ea.n_bloq = 0

    def _detecta(self):
        det0(self)
        if self.tem_ret:   # janela do retangulo (20) e da amplitude anterior (40): quantas velas pos-pregao
            tj = self.tt[-P.JANELA:]; ta = self.tt[-3 * P.JANELA:-P.JANELA]
            self.ret_pos = (sum((x // 60000) % 1440 >= POS_MIN for x in tj), sum((x // 60000) % 1440 >= POS_MIN for x in ta))

    def processar_barra(self, p, e, bar):
        antes = self.pend
        n0 = len(self.tt); ult0 = self.tt[-1] if self.tt else None
        proc0(self, p, e, bar)
        if self.tt and self.tt[-1] != ult0 and (self.tt[-1] // 60000) % 1440 >= POS_MIN:
            ano = str(P.dados.ts(self.tt[-1]).year)
            CONTA_POS[ano] = CONTA_POS.get(ano, 0) + 1
        if self.pend is not None and self.pend is not antes:
            t0, h, l, c, ema = bar
            f = ctx.calcula(int(t0) + P.BMS, float(c), self.pend["lado"], self.larg, self.meio, ema)
            f["pos_janela"], f["pos_amp"] = getattr(self, "ret_pos", (0, 0))
            self.pend["ctx"] = f
            if filtro is not None and not filtro(f):
                self.pend = None
                P.Ea.n_bloq += 1

    def avanca(self, t, p, s, e):
        pend = self.pend
        pos0 = self.pos
        avanca0(self, t, p, s, e)
        if self.pos is not None and self.pos is not pos0 and pend is not None:
            self.pos["ctx"] = pend.get("ctx", {})
        # a posicao pode abrir e fechar dentro da mesma chamada: _fecha pega o ctx do pend via self._ctx_pend
    def _fecha(self, t, k, px, motivo):
        c = (self.pos or {}).get("ctx")
        if c is None:
            c = getattr(self, "_ctx_pend", {})
        fecha0(self, t, k, px, motivo)
        self.trades[-1].update(c)

    # avanca original cria pos e pode fechar na mesma chamada; guardamos o ctx do pend antes para esse caso
    def avanca_wrap(self, t, p, s, e):
        self._ctx_pend = (self.pend or {}).get("ctx", {})
        avanca(self, t, p, s, e)

    P.Ea.processar_barra = processar_barra
    P.Ea._detecta = _detecta
    P.Ea.avanca = avanca_wrap
    P.Ea._fecha = _fecha


def roda(periodo: str, filtro=None, sem_pos=False):
    dados, P = prepara(periodo)
    instala(P, dados, filtro, sem_pos)
    lim = -1e18
    ea = P.roda(verbose=False, tf=TF, limite_equity=lim, ajustes=True)
    df = pd.DataFrame(ea.trades)
    return df, P.Ea.n_bloq
