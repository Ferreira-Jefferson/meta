"""Simulador de execucao dos setups de Larry Williams.

Recebe os `Sinais` de `lw_setups` (ordens do dia: buy/sell stop, limite, mercado
na abertura) e devolve a lista de TRADES + P&L com custos de `backtest/intraday/costs.py`.

Principios (todos testados em tests/test_larry_williams.py; convencoes em DECISOES.md):
  * Sem look-ahead: o simulador so' enxerga o dia D por barras, na ordem em que
    aconteceram; as decisoes (niveis) ja vieram prontas de D-1 + abertura de D.
  * Empate = PIOR CASO: entrada e stop na mesma barra => stop executado; stop e
    alvo na mesma barra => stop. Ordem do dia expira no fim do pregao.
  * Dois niveis de entrada tocados: vale o mais cedo (M1) ou, na mesma barra, o
    mais proximo da abertura (livro / especificacao).
  * Futuros: M1 ordena os eventos dentro do dia. Acao/ETF: 1 barra por dia.
  * Bailout so' na ABERTURA do pregao seguinte (nunca no dia da entrada).
  * Slippage em TICKS por entrada disparada (stop/mercado) e por saida a mercado
    (stop, fechamento, bailout, tempo, reversao); limite que repousa (alvo) nao paga.
    E' aplicado DEPOIS da simulacao dos niveis (sobre os precos), de modo que 0/1/2 ticks
    comparam o MESMO caminho de trades.

Tudo e' feito numa "vista longa": a venda e' simulada espelhando os precos (p -> -p,
H' = -L, L' = -H), entao existe UMA logica de saida, nao duas.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import numpy as np

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

from backtest.intraday.costs import (  # noqa: E402
    B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
    IntradayCostModel,
    apply_intraday_slippage,
    fees_round_trip_brl,
    gross_pnl_brl,
)
from backtest.intraday.profiles import FUTURES_FEE_ROUND_TRIP_BRL  # noqa: E402
from core.instruments import ACAO_B3_POINT_VALUE_BRL, FUTUROS  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    MARGIN_BUFFER_FUTUROS,
    RESERVA_CAIXA_SEGURANCA,
    capital_minimo_brl,
)

import lw_setups as S  # noqa: E402

MOTIVOS = ("STOP", "STOP_GAP", "FECHAMENTO", "BAILOUT", "TEMPO", "TEMPO_MAX", "REVERSAO",
           "ABERTURA_SEGUINTE", "ALVO", "OSC", "FIM_DADOS", "FLAT")
INF = 1e18


# ----------------------------------------------------------------------------
# Dados do ativo
# ----------------------------------------------------------------------------
class Vista:
    """Barras e dias de um ponto de vista (comprado = precos originais; vendido = espelho)."""

    def __init__(self, O, H, L, C, DO, DH, DL, DC, ini, fim, tick: float):
        self.O, self.H, self.L, self.C = O, H, L, C
        self.DO, self.DH, self.DL, self.DC = DO, DH, DL, DC
        self.ini, self.fim, self.tick = ini, fim, tick


@dataclass
class Ativo:
    nome: str
    classe: str                    # 'ACAO' | 'WIN' | 'WDO' | 'ETF_BTC'
    datas: np.ndarray              # datetime64[D], um por pregao
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    tick: float
    ponto: float                   # R$ por ponto de preco (acao: 1,0)
    fee_rt: float                  # taxa fixa por contrato/acao (ida e volta)
    taxa_pct: float                # taxa de bolsa por perna (fracao do notional)
    lote: int                      # quantidade por trade (100 acoes; 1 contrato/ETF)
    margem: float = 0.0            # margem crua por contrato (0 = nao e' futuro)
    barras: dict | None = None     # M1: O,H,L,C (np), minuto (np int), ini, fim (np int por dia)
    _vistas: dict = field(default_factory=dict, repr=False)
    _cal: dict = field(default_factory=dict, repr=False)
    _tfc: dict = field(default_factory=dict, repr=False)

    @property
    def futuro(self) -> bool:
        return self.margem > 0

    @property
    def n(self) -> int:
        return len(self.o)

    def calendario(self) -> dict:
        """dow (0=seg), mes, ano_mes e pregao-do-mes de cada dia."""
        if not self._cal:
            d = self.datas.astype("datetime64[D]")
            dow = ((d.astype("int64") + 3) % 7).astype(np.int64)   # 1970-01-01 = quinta(3)
            anos = d.astype("datetime64[Y]").astype(int) + 1970
            mes = d.astype("datetime64[M]").astype(int) % 12 + 1
            am = anos * 100 + mes
            self._cal = {"dow": dow, "mes": mes.astype(np.int64), "ano_mes": am,
                         "dom_pregao": S.dia_do_pregao_no_mes(am), "ano": anos}
        return self._cal

    def vista(self, lado: int) -> Vista:
        if lado in self._vistas:
            return self._vistas[lado]
        if self.barras is None:
            O, H, L, C = self.o, self.h, self.l, self.c
            ini = np.arange(self.n)
            fim = ini + 1
        else:
            b = self.barras
            O, H, L, C = b["O"], b["H"], b["L"], b["C"]
            ini, fim = b["ini"], b["fim"]
        if lado == 1:
            args = (O, H, L, C, self.o, self.h, self.l, self.c)
        else:
            args = (-O, -L, -H, -C, -self.o, -self.l, -self.h, -self.c)
        v = Vista(*[a.tolist() for a in args], ini.tolist(), fim.tolist(), self.tick)
        self._vistas[lado] = v
        return v


def criar_ativo(nome: str, classe: str, datas, o, h, l, c, barras: dict | None = None,
                lote: int | None = None) -> Ativo:
    """Monta o `Ativo` com a economia vinda do repo (nada de numero digitado a mao
    alem do lote: 100 acoes / 1 ETF-contrato)."""
    datas = np.asarray(datas, dtype="datetime64[D]")
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    if classe in ("WIN", "WDO"):
        eco = FUTUROS[f"{classe}@"]
        return Ativo(nome, classe, datas, o, h, l, c, tick=eco.price_tick_size,
                     ponto=eco.point_value_brl, fee_rt=FUTURES_FEE_ROUND_TRIP_BRL, taxa_pct=0.0,
                     lote=1, margem=eco.margin_per_contract_brl, barras=barras)
    lote = lote if lote is not None else (100 if classe == "ACAO" else 1)
    return Ativo(nome, classe, datas, o, h, l, c, tick=0.01, ponto=ACAO_B3_POINT_VALUE_BRL,
                 fee_rt=0.0, taxa_pct=B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG, lote=lote, barras=barras)


def capital_inicial(at: Ativo, preco_ref: float) -> float:
    """Capital = MINIMO REAL do instrumento (CLAUDE.md): acao `preco*lote*2`
    (`capital_minimo_brl`); futuro `margem * MARGIN_BUFFER * RESERVA` (WIN 250, WDO 375)."""
    if at.futuro:
        return at.margem * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA
    return capital_minimo_brl(preco_ref, shares_per_lot=at.lote)


# ----------------------------------------------------------------------------
# Configuracao de execucao
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigSim:
    lados: str = "CV"                  # 'C', 'V' ou 'CV'
    stop_modo: str = "frac"            # 'frac' (StopFrac*base) | 'abs' (extremo de S, senao frac) | 'sem'
    stop_frac: float = 0.5
    saida: str = "BAILOUT"             # BAILOUT|FECHAMENTO|TEMPO|REVERSAO|ABERTURA_SEGUINTE|RR|OSC
    bailout_dias: int = 0              # espera N pregoes apos a entrada antes de aceitar bailout
    tempo_dias: int = 3                # TEMPO: sai no fechamento de i+N
    rr: float = 2.0                    # RR: alvo = RR * distancia do stop
    max_dias: int = 20                 # teto de seguranca de permanencia [INTERP]


class Trade(NamedTuple):
    lado: int          # +1 compra, -1 venda
    dia_ent: int
    px_ent: float      # preco de execucao (sem slippage), orientacao original
    dia_sai: int
    px_sai: float
    motivo: str
    slip_ent: bool     # entrada paga slippage (stop/mercado)
    slip_sai: bool     # saida paga slippage (mercado)
    hora_ent: int      # minuto do dia da entrada (M1) ou -1


# ----------------------------------------------------------------------------
# Nucleo: entrada e vida da posicao (vista longa)
# ----------------------------------------------------------------------------
def tenta_entrada(V: Vista, i: int, tipo: int, nivel: float):
    """Procura a barra de entrada no dia i. Devolve (k, preco, taker) ou None.

    STOP (buy stop): primeira barra com H >= nivel; preco = max(nivel, abertura da barra) --
    gap acima do nivel executa na abertura (pior preco). LIMITE (buy limit): se a abertura ja'
    esta <= nivel executa na abertura (taker); senao so' se a minima ATRAVESSA o nivel (L < nivel,
    estrito: tocar nao e' preencher). MERCADO: abertura da 1a barra."""
    s, e = V.ini[i], V.fim[i]
    if tipo == S.MERCADO:
        return s, V.O[s], True
    if tipo == S.STOP:
        if V.DH[i] < nivel:
            return None
        for k in range(s, e):
            if V.H[k] >= nivel:
                return k, max(nivel, V.O[k]), True
        return None
    if V.O[s] <= nivel:
        return s, V.O[s], True
    if V.DL[i] >= nivel:
        return None
    for k in range(s, e):
        if V.L[k] < nivel:
            return k, nivel, False
    return None


def _saida_barras(V: Vista, j: int, eff: float, tgt: float | None):
    """Dia j com stop efetivo `eff` e alvo `tgt` ambos tocados: resolve pela ordem das barras
    (stop primeiro dentro da mesma barra). Devolve ('STOP'|'ALVO', preco)."""
    for k in range(V.ini[j], V.fim[j]):
        if V.L[k] <= eff:
            return "STOP", (V.O[k] if V.O[k] < eff else eff)
        if tgt is not None and V.H[k] > tgt:
            return "ALVO", max(tgt, V.O[k])
    return "STOP", eff


def vida_da_posicao(V: Vista, i: int, k: int, fill: float, tipo: int, S_px: float,
                    tgt: float | None, cfg: ConfigSim, opp: list | None, osc: list | None,
                    n_dias: int):
    """Acompanha a posicao COMPRADA (na vista) ate a saida.

    Devolve (dia_sai, preco_vista, motivo, paga_slippage, saiu_na_abertura)."""
    e = V.fim[i]
    # ---- dia da entrada: a partir da barra de entrada ----
    for kk in range(k, e):
        if V.L[kk] <= S_px:
            px = V.O[kk] if (kk > k and V.O[kk] < S_px) else S_px
            return i, px, "STOP", True, False
        if tgt is not None and V.H[kk] > tgt and (kk > k or tipo != S.LIMITE):
            return i, (max(tgt, V.O[kk]) if kk > k else tgt), "ALVO", False, False
    if cfg.saida == "FECHAMENTO" or (cfg.saida == "TEMPO" and cfg.tempo_dias == 0):
        return i, V.C[e - 1], "FECHAMENTO", True, False
    # ---- dias seguintes ----
    jmax = min(n_dias - 1, i + cfg.max_dias)
    for j in range(i + 1, jmax + 1):
        o = V.DO[j]
        if o <= S_px:
            return j, o, "STOP_GAP", True, True
        if tgt is not None and o > tgt:     # gap acima do alvo: a limite repousada executa na abertura
            return j, o, "ALVO", False, True
        if cfg.saida == "ABERTURA_SEGUINTE" and j == i + 1:
            return j, o, "ABERTURA_SEGUINTE", True, True
        if cfg.saida == "BAILOUT" and j >= i + 1 + cfg.bailout_dias and o >= fill + V.tick:
            return j, o, "BAILOUT", True, True
        if cfg.saida == "OSC" and osc is not None and osc[j]:
            return j, o, "OSC", True, True
        opp_j = opp[j] if (cfg.saida == "REVERSAO" and opp is not None) else float("nan")
        rev = opp_j == opp_j  # nao-NaN
        if rev and o <= opp_j:
            return j, o, "REVERSAO", True, True
        eff, mot = S_px, "STOP"
        if rev and opp_j > eff:
            eff, mot = opp_j, "REVERSAO"
        toca_stop = V.DL[j] <= eff
        toca_alvo = tgt is not None and V.DH[j] > tgt
        if toca_stop and toca_alvo and V.fim[j] - V.ini[j] > 1:
            quem, px = _saida_barras(V, j, eff, tgt)
            if quem == "ALVO":
                return j, px, "ALVO", False, False
            return j, px, mot, True, False
        if toca_stop:
            return j, eff, mot, True, False
        if toca_alvo:
            return j, tgt, "ALVO", False, False
        if cfg.saida == "TEMPO" and j == i + cfg.tempo_dias:
            return j, V.DC[j], "TEMPO", True, False
        if j == i + cfg.max_dias:
            return j, V.DC[j], "TEMPO_MAX", True, False
    ultimo = min(n_dias - 1, i + cfg.max_dias)
    return ultimo, V.DC[ultimo], "FIM_DADOS", True, False


def gerar_trades(at: Ativo, sin: S.Sinais, cfg: ConfigSim, i_ini: int = 0,
                 i_fim: int | None = None) -> list[Trade]:
    """Simula a janela [i_ini, i_fim) com UMA posicao por vez. Candidato so' e' tentado se o
    caixa de posicao estiver livre (saida na abertura libera o proprio dia; saida intradiaria
    libera so' o dia seguinte)."""
    n = at.n
    i_fim = n if i_fim is None else min(i_fim, n)
    nc = sin.nivel_c if "C" in cfg.lados else np.full(n, np.nan)
    nv = sin.nivel_v if "V" in cfg.lados else np.full(n, np.nan)
    ativo_dia = np.isfinite(nc) | np.isfinite(nv)
    cand = (np.flatnonzero(ativo_dia[i_ini:i_fim]) + i_ini).tolist()
    if not cand:
        return []
    vc, vv = at.vista(1), at.vista(-1)
    nc_l, nv_l, base_l, do_l = nc.tolist(), nv.tolist(), sin.base_stop.tolist(), at.o.tolist()
    sac = sin.stop_abs_c.tolist() if sin.stop_abs_c is not None else None
    sav = sin.stop_abs_v.tolist() if sin.stop_abs_v is not None else None
    osc_c = sin.saida_osc_c.tolist() if sin.saida_osc_c is not None else None
    osc_v = sin.saida_osc_v.tolist() if sin.saida_osc_v is not None else None
    # reversao: o oposto de quem esta comprado e' o nivel de venda (na vista longa) e vice-versa
    opp_c = nv_l
    opp_v = [-x for x in nc_l]
    minuto = at.barras["minuto"] if at.barras is not None else None
    trades: list[Trade] = []
    livre = i_ini
    for i in cand:
        if i < livre:
            continue
        opcoes = []
        if nc_l[i] == nc_l[i]:
            r = tenta_entrada(vc, i, sin.tipo_c, nc_l[i])
            if r:
                opcoes.append((r[0], abs(nc_l[i] - do_l[i]), 1, r[1], r[2]))
        if nv_l[i] == nv_l[i]:
            r = tenta_entrada(vv, i, sin.tipo_v, -nv_l[i])
            if r:
                opcoes.append((r[0], abs(nv_l[i] - do_l[i]), -1, r[1], r[2]))
        if not opcoes:
            continue
        k, _, lado, fill, taker = min(opcoes, key=lambda x: (x[0], x[1]))
        V = vc if lado == 1 else vv
        tipo = sin.tipo_c if lado == 1 else sin.tipo_v
        # ---- stop ----
        if cfg.stop_modo == "sem":
            S_px = -INF
        else:
            dist = cfg.stop_frac * base_l[i]
            S_px = fill - dist
            if cfg.stop_modo == "abs":
                ab = (sac if lado == 1 else sav)
                if ab is not None and ab[i] == ab[i]:
                    S_px = ab[i] if lado == 1 else -ab[i]
            if not (S_px < fill) or dist != dist:
                continue   # stop invalido (base NaN/0 ou stop acima da entrada)
        tgt = None
        if cfg.saida == "RR":
            if S_px <= -INF / 2:
                continue
            tgt = fill + cfg.rr * (fill - S_px)
        dia_sai, px, mot, slip_sai, na_abertura = vida_da_posicao(
            V, i, k, fill, tipo, S_px, tgt, cfg,
            opp_c if lado == 1 else opp_v, osc_c if lado == 1 else osc_v, n)
        trades.append(Trade(lado, i, lado * fill, dia_sai, lado * px, mot,
                            bool(taker), slip_sai, int(minuto[k]) if minuto is not None else -1))
        livre = dia_sai if (na_abertura or mot == "REVERSAO") else dia_sai + 1
    return trades


# ----------------------------------------------------------------------------
# TRES_BARRAS (intradiario, 100% limite na entrada e no alvo)
# ----------------------------------------------------------------------------
def _grupos_tf(at: Ativo, tf: int) -> dict:
    """Agrupa as M1 em barras de `tf` minutos DENTRO de cada pregao."""
    cache = at._tfc
    if tf in cache:
        return cache[tf]
    b = at.barras
    minuto = np.asarray(b["minuto"])
    dia_id = np.repeat(np.arange(at.n), np.asarray(b["fim"]) - np.asarray(b["ini"]))
    chave = dia_id * 10000 + (minuto - 540) // tf
    inicio = np.flatnonzero(np.r_[True, chave[1:] != chave[:-1]])
    gid = np.cumsum(np.r_[True, chave[1:] != chave[:-1]]) - 1
    out = {"inicio": inicio, "gid": gid.tolist(),
           "H": np.maximum.reduceat(b["H"], inicio), "L": np.minimum.reduceat(b["L"], inicio),
           "dia_do_grupo": dia_id[inicio]}
    cache[tf] = out
    return out


def gerar_trades_tres_barras(at: Ativo, tf: int, stop_frac: float, tend: np.ndarray,
                             i_ini: int = 0, i_fim: int | None = None,
                             hora_corte: int = 17 * 60) -> list[Trade]:
    """Three-Bar High/Low (M5/M15, so' WIN/WDO): ordem LIMITE de compra em SMA3(minimas)
    (so' com tendencia de ALTA), alvo LIMITE em SMA3(maximas), stop a mercado a
    `stop_frac*R1(D-1)`, zera no fim do pregao. Venda espelhada so' em tendencia de BAIXA.
    A ordem vale so' durante a barra do timeframe em que foi posta; nao se poe ordem apos
    `hora_corte` (minuto do dia) nem com menos de 3 barras no dia."""
    assert at.barras is not None, "TRES_BARRAS exige M1"
    n = at.n
    i_fim = n if i_fim is None else min(i_fim, n)
    g = _grupos_tf(at, tf)
    b = at.barras
    minuto = b["minuto"]
    r1 = S.range_ontem(at.h, at.l)
    trades: list[Trade] = []
    gid = g["gid"]
    dia_do_grupo = g["dia_do_grupo"]
    primeiro_grupo = np.searchsorted(dia_do_grupo, np.arange(n), side="left").tolist()
    for lado in (1, -1):
        V = at.vista(lado)
        Hg = g["H"] if lado == 1 else -g["L"]
        Lg = g["L"] if lado == 1 else -g["H"]
        sma_h, sma_l = S.sma3_extremos(Hg, Lg)
        sma_h, sma_l = sma_h.tolist(), sma_l.tolist()
        tick = at.tick
        for i in range(i_ini, i_fim):
            if (tend[i] > 0) != (lado == 1) or tend[i] == 0 or r1[i] != r1[i]:
                continue
            dist = stop_frac * r1[i]
            s, e = V.ini[i], V.fim[i]
            g0 = primeiro_grupo[i]
            pos = None
            g_atual = -1
            lvl = tgt_px = None
            k = s
            while k < e:
                gk = gid[k]
                if gk != g_atual:
                    g_atual = gk
                    lvl = tgt_px = None
                    if pos is None and gk - g0 >= 3 and minuto[k] < hora_corte:
                        a, bnd = sma_l[gk], sma_h[gk]
                        if a == a and bnd == bnd:
                            lv = np.floor(a / tick + 1e-9) * tick
                            tg = np.ceil(bnd / tick - 1e-9) * tick
                            if tg > lv + tick:
                                lvl, tgt_px = float(lv), float(tg)
                if pos is None:
                    if lvl is not None:
                        fill = None
                        if V.O[k] <= lvl:
                            fill, taker = V.O[k], True
                        elif V.L[k] < lvl:
                            fill, taker = lvl, False
                        if fill is not None:
                            pos = (fill, fill - dist, tgt_px, k, taker)
                            if V.L[k] <= pos[1]:      # entrada e stop na mesma barra => stop
                                trades.append(Trade(lado, i, lado * fill, i, lado * pos[1], "STOP",
                                                    taker, True, int(minuto[k])))
                                pos = None
                                lvl = tgt_px = None
                else:
                    fill, S_px, tg, k0, taker = pos
                    if V.L[k] <= S_px:
                        px = V.O[k] if V.O[k] < S_px else S_px
                        trades.append(Trade(lado, i, lado * fill, i, lado * px, "STOP", taker, True,
                                            int(minuto[k0])))
                        pos = None
                        lvl = tgt_px = None
                    elif V.H[k] > tg:
                        trades.append(Trade(lado, i, lado * fill, i, lado * tg, "ALVO", taker, False,
                                            int(minuto[k0])))
                        pos = None
                        lvl = tgt_px = None
                k += 1
            if pos is not None:
                fill, S_px, tg, k0, taker = pos
                trades.append(Trade(lado, i, lado * fill, i, lado * V.C[e - 1], "FLAT", taker, True,
                                    int(minuto[k0])))
    trades.sort(key=lambda t: (t.dia_ent, t.hora_ent))
    return trades


# ----------------------------------------------------------------------------
# Custos, caixa e estatisticas
# ----------------------------------------------------------------------------
def modelo_de_custo(at: Ativo, slip_ticks: float) -> IntradayCostModel:
    return IntradayCostModel(point_value_brl=at.ponto, tick_size=at.tick,
                             fee_round_trip_brl=at.fee_rt, slippage_ticks=float(slip_ticks),
                             exchange_fee_pct_per_leg=at.taxa_pct)


def pnl_dos_trades(at: Ativo, trades: list[Trade], slip_ticks: float) -> dict:
    """P&L por trade com custos do repo. Devolve arrays: pe, ps (precos apos slippage),
    pts, brl (liquido de taxas), taxa."""
    if not trades:
        z = np.zeros(0)
        return {"pe": z, "ps": z, "pts": z, "brl": z, "taxa": z}
    arr = np.array([(t.lado, t.px_ent, t.px_sai, t.slip_ent, t.slip_sai) for t in trades], dtype=float)
    lado, pe, ps, fe, fs = arr.T
    m = modelo_de_custo(at, slip_ticks)
    longo = lado > 0
    pe_s = np.where(longo, apply_intraday_slippage(pe, "buy", m), apply_intraday_slippage(pe, "sell", m))
    ps_s = np.where(longo, apply_intraday_slippage(ps, "sell", m), apply_intraday_slippage(ps, "buy", m))
    pe = np.where(fe > 0, pe_s, pe)
    ps = np.where(fs > 0, ps_s, ps)
    bruto = np.where(longo, gross_pnl_brl(pe, ps, at.lote, "long", m),
                     gross_pnl_brl(pe, ps, at.lote, "short", m))
    taxa = fees_round_trip_brl(at.lote, pe, ps, m)
    pts = np.where(longo, ps - pe, pe - ps)
    return {"pe": pe, "ps": ps, "pts": pts, "brl": bruto - taxa, "taxa": taxa}


def aplica_caixa(at: Ativo, trades: list[Trade], brl: np.ndarray, pe: np.ndarray,
                 capital: float):
    """Portao de caixa sequencial. Acao: precisa de `preco*lote`; futuro: so' a margem crua do
    1o contrato (CLAUDE.md: piso e' indicacao de PARTIDA, nao de continuidade).
    Devolve (executados: bool array, caixa_final, n_pulados, caixa_minimo)."""
    n = len(trades)
    if n == 0:
        return np.zeros(0, dtype=bool), capital, 0, capital
    exigido = np.full(n, at.margem) if at.futuro else pe * at.lote
    caixa_antes = capital + np.concatenate(([0.0], np.cumsum(brl)[:-1]))
    if np.all(caixa_antes >= exigido):                 # via rapida: nenhum trade barrado
        caixa = capital + np.cumsum(brl)
        return np.ones(n, dtype=bool), float(caixa[-1]), 0, float(min(capital, caixa.min()))
    ok = np.zeros(n, dtype=bool)
    caixa = capital
    minimo = capital
    for k in range(n):
        if caixa >= exigido[k]:
            ok[k] = True
            caixa += brl[k]
            minimo = min(minimo, caixa)
    return ok, float(caixa), int(n - ok.sum()), float(minimo)


def estatisticas(at: Ativo, trades: list[Trade], slip_ticks: float, capital: float,
                 pregoes: int, min_trades: int = 20, portao: bool = True, p: dict | None = None) -> dict:
    """Metricas de uma janela. `censurada` = caixa barrou trades, caixa final <= 0 ou poucos trades.

    `portao=False` mede o EDGE sem o portao de caixa (capital nocional): todos os trades entram.
    E' a leitura certa de 'a regra tem vantagem?'; a leitura de 'o dono consegue operar?' e'
    `portao=True` com o capital minimo real."""
    if p is None:
        p = pnl_dos_trades(at, trades, slip_ticks)
    if portao:
        ok, caixa_final, pulados, caixa_min = aplica_caixa(at, trades, p["brl"], p["pe"], capital)
    else:
        ok = np.ones(len(trades), dtype=bool)
        caixa_final = capital + float(p["brl"].sum())
        pulados, caixa_min = 0, capital
    brl = p["brl"][ok]
    pts = p["pts"][ok]
    pe = p["pe"][ok]
    n = int(len(brl))
    venc = brl > 0
    nv = int(venc.sum())
    ganho = float(brl[venc].mean()) if nv else 0.0
    perda = float(-brl[~venc].mean()) if n - nv else 0.0
    be = perda / (ganho + perda) if (ganho + perda) > 0 else float("nan")
    equity = capital + np.cumsum(brl) if n else np.zeros(0)
    pico = np.maximum.accumulate(np.r_[capital, equity]) if n else np.array([capital])
    dd = float((pico - np.r_[capital, equity]).max()) if n else 0.0
    notional = pe * at.lote * at.ponto
    ret_pct = brl / np.where(notional > 0, notional, np.nan) * 100.0 if n else np.zeros(0)
    ganho_pct = float(np.nanmean(ret_pct[venc])) if nv else 0.0
    perda_pct = float(-np.nanmean(ret_pct[~venc])) if n - nv else 0.0
    return {
        "n": n, "win_pct": 100.0 * nv / n if n else float("nan"),
        "be_emp_pct": 100.0 * be if be == be else float("nan"),
        "liquido": float(brl.sum()), "exp_brl": float(brl.mean()) if n else float("nan"),
        "exp_pts": float(pts.mean()) if n else float("nan"),
        "exp_pct": float(np.nanmean(ret_pct)) if n else float("nan"),
        "ganho_medio": ganho, "perda_media": perda, "ganho_pct": ganho_pct, "perda_pct": perda_pct,
        "maxdd_brl": dd, "maxdd_pct": 100.0 * dd / float(pico.max()) if n else 0.0,
        "capital": capital, "capital_final": caixa_final, "pulados": pulados,
        "caixa_min": caixa_min, "pregoes": pregoes,
        "trd_dia": n / pregoes if pregoes else float("nan"),
        "censurada": bool(pulados > 0 or caixa_final <= 0 or n < min_trades),
    }


#: Vocabulario de motivos do CSV (igual ao do EA, ver DECISOES_EA.md item 17).
MOTIVO_CSV = {"STOP": "stop", "STOP_GAP": "stop", "FECHAMENTO": "fechamento", "BAILOUT": "bailout",
              "TEMPO": "tempo", "TEMPO_MAX": "tempo", "REVERSAO": "reversao",
              "ABERTURA_SEGUINTE": "abertura_seguinte", "ALVO": "alvo", "OSC": "indicador",
              "FIM_DADOS": "fim_dados", "FLAT": "fim_pregao"}


def exporta_trades_csv(at: Ativo, trades: list[Trade], caminho, slip_ticks: float = 0.0) -> None:
    """CSV de referencia para comparar com o log do EA no Testador do MT5.

    Formato do EA: `data;lado;entrada;saida;motivo;pnl_pts`, `data` = dia da ENTRADA (AAAA-MM-DD),
    lado C/V, precos de execucao SEM slippage, `pnl_pts` = (saida - entrada) * lado em pontos
    (com `slip_ticks=0`, o padrao: sem custos nem slippage, como o log do EA)."""
    p = pnl_dos_trades(at, trades, slip_ticks)
    linhas = ["data;lado;entrada;saida;motivo;pnl_pts"]
    for t, pts in zip(trades, p["pts"]):
        linhas.append(f"{at.datas[t.dia_ent]};{'C' if t.lado == 1 else 'V'};{t.px_ent:.4f};{t.px_sai:.4f};"
                      f"{MOTIVO_CSV.get(t.motivo, t.motivo.lower())};{pts:.4f}")
    Path(caminho).write_text(chr(10).join(linhas) + chr(10), encoding="utf-8")
