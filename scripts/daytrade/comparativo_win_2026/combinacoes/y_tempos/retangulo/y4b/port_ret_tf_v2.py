# -*- coding: utf-8 -*-
"""Y4b: RetTF v2 = ../port_ret_tf.py (Y4) + flag `ajustes` em roda(). ajustes=False reproduz a Y4 byte a byte.
ajustes=True aplica os 3 ajustes PRE-REGISTRADOS na secao Y4b do TODO:
  A. Janela entre dias: o historico de velas (hh/ll/cc/tt) NAO e' zerado na virada do dia; o detector usa as ultimas 20 velas
     fechadas (inclusive do pregao anterior) e a amplitude anterior das 40 antes delas. Cai o "3*janela velas NO DIA":
     o minimo 3*janela passa a ser sobre o historico corrido (que e' pre-carregado com as ultimas velas validas anteriores
     ao periodo, para nao perder as primeiras semanas dos tempos grandes).
     Mudancas extras necessarias (documentadas): no virada do dia continuam zerados o RETANGULO (tem_ret, fora) e a ordem
     pendente (o EA zera isso em ZerarPregao as 17:00 e no ResetSessao; em H4 nao ha vela >=17:00 no pregao, entao sem este
     reset o retangulo e a pendente atravessariam a noite); so' o historico de velas e' mantido. O filtro de velas com
     ABERTURA < 09:01 (leilao) fica como no EA: descarta as velas das 08h (H2, H4) e das 09h (H1, H3, M30 das 09:00 etc).
  B. Corte de entrada = min((TTL+1)*vela, 60 min) antes das 17:00.
  C. Descarte de vela com faixa > 2000*sqrt(minutos da vela).
Nao alterado (fiel ao EA): zeragem 17:00 so' e' checada no 1o tick de cada vela nova (IsNewBar); em H2/H3 zera na vela das
18:00; em H4 nao ha vela depois das 17:00 no pregao e a posicao sai pelo "fim_dados" (ultimo tick do dia).
=====
COPIA PARAMETRIZADA (Y4) de ../../../port_retangulo_ema34.py: o tempo gráfico base (`TFMIN`, minutos) é parâmetro.
Reproduz o que o EA faz ao trocar o input TimeframeBase (iMA, IsNewBar, CopyRates, iTime em TimeframeBase):
  - velas = buckets de TFMIN minutos construidos dos ticks (alinhados à meia-noite, como o MT5); high/low/close da vela TF;
  - JANELA (20), TTL (10), aproximacao do alvo (a cada 5 velas) e EMA34 contam em VELAS do novo tempo gráfico;
  - historico de aquecimento da EMA: M1 do `dados.m1()` agregado para TFMIN (iMA tem historico do mesmo TF);
  - descarte de vela com faixa > 2000 pts vale para a vela TF (como o EA: faixa da barra de TimeframeBase);
  - inicio do dia: vela cuja ABERTURA < 09:01 e' descartada (no M5, a vela das 09:00 sai; a 1a contada e' a das 09:05);
  - "nao arma entrada nas ultimas (TTL+1) velas": minutos_barra = TFMIN, como o EA (HoraZerar*60+Min - (TTL+1)*minutos_barra);
  - largura minima 328 pts, tolerancia, fracoes alvo/stop, zeragem 17:00: inalterados;
  - barra do fill / "so' conta velas fechadas depois da vela do fill" no bucket TF.
Com TFMIN=1 e' byte a byte igual ao original (prova em prova.py).
-----
Port tick a tick de `mt5/WinRetanguloEma34.mq5` v1.04 para o replay do Testador (comparativo WIN 2026).

O .mq5 e' a especificacao. Fluxo reproduzido, na ordem do OnTick:
  1. a cada tick, o Testador processa as ordens/posicao ANTES do OnTick:
       - limite de entrada enche ao TOCAR (compra: last <= limite; venda: last >= limite), no preco do limite;
       - SL nativo dispara pelo last e executa no last do tick; alvo (limite real) enche ao tocar, no preco do limite;
       - SL e alvo valem a partir do tick SEGUINTE ao do preenchimento (o EA os arma no OnTick do tick do fill).
  2. no 1o tick de cada vela M1 (IsNewBar): se hora >= 17:00 -> ZerarPregao (cancela pendentes, fecha a mercado no last);
     senao AproximarAlvo (OrderModify do alvo) e ProcessarBarraFechada (detector + EMA34 + arma limite).
  3. ordem armada no tick `e` so' enche de `e+1` em diante; limite so' e' aceita se o preco do tick nao a atravessou
     (BuyLimit exige ask >= limite; SellLimit exige bid <= limite; stops level 0 -> igualdade vale).
bid = ask = last (WIN$N nao tem bid/ask). Velas M1 sao CONSTRUIDAS dos proprios ticks (como o Testador), o historico
de aquecimento da EMA vem de `dados.m1()`. Eventos por searchsorted/argmax em fatias numpy (nada de loop por tick).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[3]  # comparativo_win_2026
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parents[2] / "src"))
import dados  # noqa: E402
from strategy.daytrade.lab.win_retangulo import detecta_retangulo  # noqa: E402

NOME = "WinRetanguloEma34"
# inputs padrao do .mq5
JANELA, TOL, ALVO_F, STOP_F, TTL, LARG_MIN = 20, 0.20, 0.90, 0.45, 10, 328.0
PER_EMA, APROX_BARRAS, APROX_PASSO, ALVO_PISO = 34, 5, 0.10, 0.50
ZERA_MIN = 17 * 60 + 0
INI_MIN = 9 * 60 + 1
RANGE_MAX = 2000.0
TICK = 5.0
LARG_MIN_TICKS = 6.0
MARGEM_MORTE, BARRAS_MORTE = 0.25, 3
LIMITE_EQUITY = 0.0
AJUSTES = False
CORTE_MIN = (TTL + 1) * 1   # minutos antes da zeragem sem armar entrada (B)
TFMIN = 1          # tempo gráfico base em minutos (parametro; setado por roda())
BMS = 60000        # ms por vela TF
ALFA = 2.0 / (PER_EMA + 1)


def no_tick(x: float) -> float:
    return float(np.floor(x / TICK + 0.5) * TICK)  # MathRound do MQL5: meio arredonda para longe de zero (precos > 0)


class Ea:
    def __init__(self, py_fantasma=False):
        self.py_fantasma = py_fantasma  # so' validacao: emula o contador-fantasma do Python (ver compara_port_x_python.py)
        self.dia_atual = None
        self._reset_hist()
        self.pend = None   # dict(side, limite, stop, alvo, esperando)
        self.pos = None    # dict(...)
        self.trades = []
        self.equity = dados.CAPITAL
        self.parou = False
        self.stats = dict(alvo_marcavel=0, armar_rejeitada=0, aproxima=0)

    def _reset_hist(self):
        self.hh, self.ll, self.cc, self.tt = [], [], [], []
        self.tem_ret = False
        self.topo = self.piso = self.larg = self.meio = 0.0
        self.fora = 0

    # ----- execucao tick a tick -------------------------------------------------------------
    def _fecha(self, t, k, px, motivo):
        pos = self.pos
        tr = dados.trade(NOME, pos["t_ent"], int(t[k]), pos["lado"], 1.0, pos["entry"], px, motivo)
        self.trades.append(tr)
        self.equity += tr["rs"]
        self.pos = None
        if self.equity <= LIMITE_EQUITY:
            self.parou = True

    def avanca(self, t, p, s, e):
        """Processa ordens sobre os ticks (s, e]. Ordens armadas no tick s so' valem de s+1 em diante."""
        if e <= s:
            return
        if self.pend is not None:
            pd_ = self.pend
            if pd_.get("fantasma"):
                return
            seg = p[s + 1:e + 1]
            hit = (seg <= pd_["limite"]) if pd_["lado"] > 0 else (seg >= pd_["limite"])
            if not hit.any():
                return
            k = s + 1 + int(np.argmax(hit))
            self.pend = None
            # OnTick do tick k: DetectarPreenchimentoEntrada ancora stop/alvo (delta = 0: fill exatamente no limite)
            entry = pd_["limite"]
            alvo = pd_["alvo"]
            self.pos = dict(lado=pd_["lado"], entry=entry, stop=pd_["stop"], alvo=alvo, t_ent=int(t[k]),
                            barra_fill=int(t[k] // BMS), larg_pos=abs(alvo - entry) / ALVO_F,
                            frac=ALVO_F, barras=0)
            s = k
        if self.pos is not None and e > s:
            pos = self.pos
            seg = p[s + 1:e + 1]
            if pos["lado"] > 0:
                ht, hs = seg >= pos["alvo"], seg <= pos["stop"]
            else:
                ht, hs = seg <= pos["alvo"], seg >= pos["stop"]
            kt = int(np.argmax(ht)) if ht.any() else 1 << 60
            ks = int(np.argmax(hs)) if hs.any() else 1 << 60
            if kt == ks == 1 << 60:
                return
            if kt < ks:
                self._fecha(t, s + 1 + kt, pos["alvo"], "alvo")
            else:
                k = s + 1 + ks
                self._fecha(t, k, float(p[k]), "stop")

    # ----- OnTick no 1o tick de cada vela ---------------------------------------------------
    def zerar(self, t, p, e):
        self.pend = None
        if self.pos is not None:
            self._fecha(t, e, float(p[e]), "zera")
        self.tem_ret = False

    def aproximar(self, p, e, prev_start):
        pos = self.pos
        if APROX_BARRAS <= 0 or pos is None or pos["larg_pos"] <= 0:
            return
        if prev_start // BMS <= pos["barra_fill"]:
            return
        pos["barras"] += 1
        frac = max(ALVO_F - APROX_PASSO * (pos["barras"] // APROX_BARRAS), ALVO_PISO)
        if frac >= pos["frac"] - 1e-9:
            return
        long_ = pos["lado"] > 0
        novo = no_tick(pos["entry"] + pos["lado"] * frac * pos["larg_pos"])
        bid = float(p[e])
        if long_:
            preco = max(novo, bid)
            if novo <= bid:
                self.stats["alvo_marcavel"] += 1
        else:
            preco = min(novo, bid)
            if novo >= bid:
                self.stats["alvo_marcavel"] += 1
        pos["alvo"] = no_tick(preco)
        pos["frac"] = frac
        self.stats["aproxima"] += 1

    def processar_barra(self, p, e, bar):
        """bar = (t_ms_inicio, h, l, c, ema) da ultima vela FECHADA."""
        t0, h, l, c, ema = bar
        mins = (t0 // 60000) % 1440
        dia_barra = (t0 // 60000) // 1440
        if dia_barra != self.dia_atual:
            self.dia_atual = dia_barra
            if AJUSTES:   # A: mantem o historico de velas; zera so' retangulo e pendente
                self.tem_ret = False; self.fora = 0
                self.topo = self.piso = self.larg = self.meio = 0.0
            else:
                self._reset_hist()
            self.pend = None
        if mins < INI_MIN:
            return
        if RANGE_MAX > 0 and (h - l) > RANGE_MAX:
            return
        self.hh.append(h); self.ll.append(l); self.cc.append(c); self.tt.append(t0)
        if AJUSTES and len(self.cc) > 3 * JANELA + 5:
            for L in (self.hh, self.ll, self.cc, self.tt):
                del L[:-(3 * JANELA)]
        if self.tem_ret:
            marg = MARGEM_MORTE * self.larg
            if c > self.topo + marg or c < self.piso - marg:
                self.fora += 1
                morreu = self.fora >= BARRAS_MORTE
            else:
                self.fora = 0
                morreu = False
            if morreu:
                self.tem_ret = False
                self.pend = None
        if not self.tem_ret:
            self._detecta()
            if not self.tem_ret:
                return
        if self.pos is not None:
            return
        if self.pend is not None:
            self.pend["esperando"] += 1
            if self.pend["esperando"] < TTL:
                return
            self.pend = None
        meio, larg = self.meio, self.larg
        if c < meio:
            lado = -1; alvo = meio - ALVO_F * larg; stop = meio + STOP_F * larg
        elif c > meio:
            lado = 1; alvo = meio + ALVO_F * larg; stop = meio - STOP_F * larg
        else:
            return
        limite = no_tick(meio)
        fantasma = False
        if self.py_fantasma:
            # Python G21 arma (e zera o contador de espera) ANTES dos filtros G29/G41 descartarem a ordem
            if (lado < 0 and limite <= c) or (lado > 0 and limite >= c):
                return
            if ema is None or (lado > 0 and c < ema) or (lado < 0 and c > ema) or mins >= ZERA_MIN - CORTE_MIN:
                self.pend = dict(lado=lado, limite=limite, stop=0.0, alvo=0.0, esperando=0, fantasma=True)
                return
        if ema is None:
            return
        if lado > 0 and c < ema:
            return
        if lado < 0 and c > ema:
            return
        if mins >= ZERA_MIN - CORTE_MIN:
            return
        if lado < 0 and limite <= c:
            return
        if lado > 0 and limite >= c:
            return
        # SellLimit exige limite >= bid; BuyLimit exige limite <= ask (stops level 0)
        px = float(p[e])
        if (lado < 0 and limite < px) or (lado > 0 and limite > px):
            self.stats["armar_rejeitada"] += 1
            return
        self.pend = dict(lado=lado, limite=limite, stop=no_tick(stop), alvo=no_tick(alvo), esperando=0)

    def _detecta(self):
        n = len(self.cc)
        W = JANELA
        if n < 3 * W:
            return
        hi = np.asarray(self.hh[-W:]); lo = np.asarray(self.ll[-W:]); cl = np.asarray(self.cc[-W:])
        amp = max(self.hh[-3 * W:-W]) - min(self.ll[-3 * W:-W])
        r = detecta_retangulo(hi, lo, cl, amp, tolerancia=TOL)
        if r is None:
            return
        if r["largura"] < LARG_MIN_TICKS * TICK or r["largura"] < LARG_MIN:
            return
        self.topo, self.piso, self.larg, self.meio = r["topo"], r["piso"], r["largura"], r["meio"]
        self.tem_ret = True
        self.fora = 0


def barras_do_dia(t, p):
    mn = t // BMS
    nb = np.r_[0, np.flatnonzero(np.diff(mn)) + 1]
    last = np.r_[nb[1:] - 1, len(t) - 1]
    return nb, mn[nb] * BMS, np.maximum.reduceat(p, nb), np.minimum.reduceat(p, nb), p[last]


def roda(dias_lista=None, verbose=True, py_fantasma=False, tf=1, limite_equity=None, ajustes=False):
    global TFMIN, BMS, LIMITE_EQUITY, AJUSTES, RANGE_MAX, CORTE_MIN
    TFMIN, BMS = int(tf), int(tf) * 60000
    AJUSTES = bool(ajustes)
    if AJUSTES:
        RANGE_MAX = 2000.0 * float(np.sqrt(TFMIN))          # C
        CORTE_MIN = min((TTL + 1) * TFMIN, 60)              # B
    else:
        RANGE_MAX = 2000.0
        CORTE_MIN = (TTL + 1) * TFMIN
    if limite_equity is not None:
        LIMITE_EQUITY = limite_equity
    dias_lista = dias_lista or dados.dias()
    m = dados.m1()
    ant = m[m.index.date < dias_lista[0]]
    if TFMIN > 1:  # historico do mesmo TF: agrega as M1 em velas TF (meia-noite alinhada)
        ams = ant.index.values.astype("datetime64[ms]").astype(np.int64) // BMS
        ant = ant.groupby(ams).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
        ant.index = pd.to_datetime(ant.index.values * BMS, unit="ms")
    ema_est = float(ant.close.ewm(span=PER_EMA, adjust=False).mean().iloc[-1])
    ult = ant.iloc[-1]
    prev = (dados.ms(ant.index[-1]), float(ult.high), float(ult.low), float(ult.close), ema_est)
    ea = Ea(py_fantasma)
    if AJUSTES:  # A: pre-carrega o historico de velas validas anteriores ao periodo (mesmos filtros do processar_barra)
        for ts_, r_ in ant.iloc[:-1].tail(600).iterrows():
            t0_ = dados.ms(ts_)
            if (t0_ // 60000) % 1440 < INI_MIN or (r_.high - r_.low) > RANGE_MAX:
                continue
            ea.hh.append(float(r_.high)); ea.ll.append(float(r_.low)); ea.cc.append(float(r_.close)); ea.tt.append(t0_)
        for L in (ea.hh, ea.ll, ea.cc, ea.tt):
            del L[:-(3 * JANELA)]
    for dia in dias_lista:
        t, p, _v, _r = dados.ticks(dia)
        nb, bstart, bh, bl, bc = barras_do_dia(t, p)
        # EMA de cada vela do dia (iMA: seed na 1a vela, alfa 2/(N+1))
        emas = np.empty(len(nb)); x = ema_est
        for i, cl in enumerate(bc):
            x = ALFA * cl + (1 - ALFA) * x
            emas[i] = x
        n = len(t)
        s = 0
        for j in range(len(nb)):
            e = int(nb[j])
            ea.avanca(t, p, s, e)
            s = e
            if ea.parou:
                break
            if (int(t[e]) // 60000) % 1440 >= ZERA_MIN:
                ea.zerar(t, p, e)
            else:
                ea.aproximar(p, e, prev[0])
                ea.processar_barra(p, e, prev)
            prev = (int(bstart[j]), float(bh[j]), float(bl[j]), float(bc[j]), float(emas[j]))
        if ea.parou:
            break
        ea.avanca(t, p, s, n - 1)
        if ea.pos is not None:  # nao deveria (zera 17:00); fecha no ultimo tick
            ea._fecha(t, n - 1, float(p[-1]), "fim_dados")
        ea.pend = None
        ema_est = float(emas[-1])
        if verbose:
            print(f"{dia} trades={len(ea.trades)} equity={ea.equity:.2f}", flush=True)
    return ea


def resumo(trades):
    df = pd.DataFrame(trades)
    df["mes"] = df.saida.str[:7]
    g = df.groupby("mes").agg(trades=("rs", "size"), liquido=("rs", "sum"), win=("rs", lambda x: (x > 0).mean() * 100))
    return df, g


if __name__ == "__main__":
    ea = roda()
    out = dados.salvar(NOME, ea.trades)
    df, g = resumo(ea.trades)
    print(g.round(2).to_string(), flush=True)
    print("TOTAL", len(df), round(df.rs.sum(), 2), "motivos", df.motivo.value_counts().to_dict(), flush=True)
    print("stats", ea.stats, "->", out, flush=True)
