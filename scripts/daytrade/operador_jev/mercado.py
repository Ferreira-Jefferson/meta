"""Dados do WIN por dia (M15 + M1) e o 'pacote de mercado' textual que o operador recebe.

Regra de ouro: o pacote da vela k so usa dados com indice <= k (velas FECHADAS) e dias anteriores.
Datas reais nunca entram no pacote (anonimizacao); precos reais sim.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "daytrade" / "topos_fundos"))

DIAS_PT = ["segunda-feira", "terca-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sabado", "domingo"]
MIN_FLAT_ANTES_FIM = 5


@dataclass
class DiaMkt:
    data: pd.Timestamp
    m15_t: np.ndarray          # inicio de cada vela M15 (datetime64)
    m15: np.ndarray            # (n,5) open high low close volume
    m1_t: np.ndarray
    m1: np.ndarray             # (m,4) open high low close
    m1_ini: np.ndarray         # indice do 1o M1 de cada M15
    m1_fim: np.ndarray         # indice exclusivo
    flat_i: int                # indice do M1 em que se zera (fim do pregao - 5 min)
    dia_n: int = 1
    venc_semana: bool = False
    venc_dia: bool = False


class Mercado:
    """Historico completo (varios dias) para montar contexto sem olhar o futuro."""

    def __init__(self, m15: pd.DataFrame, m1: pd.DataFrame, vencimentos=None):
        m15 = m15.sort_index().copy()
        pc = m15.close.shift(1).where(m15.dia == m15.dia.shift(1))
        tr = pd.concat([m15.high - m15.low, (m15.high - pc).abs(), (m15.low - pc).abs()], axis=1).max(axis=1)
        # ATR M15 INCLUINDO a vela fechada atual (so passado)
        m15["atr_m15"] = tr.rolling(14, min_periods=5).mean()
        self.m15 = m15
        self.m1 = m1.sort_index()
        g = m15.groupby("dia")
        d = pd.DataFrame(dict(open=g.open.first(), high=g.high.max(), low=g.low.min(), close=g.close.last(),
                              vol=g.real_volume.sum()))
        pcd = d.close.shift(1)
        trd = pd.concat([d.high - d.low, (d.high - pcd).abs(), (d.low - pcd).abs()], axis=1).max(axis=1)
        d["atr_d"] = trd.rolling(14, min_periods=5).mean()  # usado so de dias ja FECHADOS
        self.diario = d
        self.dias = list(d.index)
        self.venc = [pd.Timestamp(v) for v in (vencimentos if vencimentos is not None else [])]

    @classmethod
    def carregar(cls):
        import dados
        frames = [dados.m15(p) for p in ("virgem", "IS", "OOS")]
        m15 = pd.concat(frames).sort_index()
        m15 = m15[~m15.index.duplicated()]
        m1s = []
        for p in ("virgem", "IS", "OOS"):
            arq, ini, fim = dados.PERIODOS[p]
            m = pd.read_parquet(dados.RAIZ / arq, columns=["open", "high", "low", "close", "ultima_continua"])
            m1s.append(m[(m.index >= ini) & (m.index < fim)])
        m1 = pd.concat(m1s).sort_index()
        m1 = m1[~m1.index.duplicated()]
        return cls(m15, m1, dados.vencimentos())

    def dias_do_periodo(self, periodo):
        import dados
        _, ini, fim = dados.PERIODOS[periodo]
        return [d for d in self.dias if pd.Timestamp(ini) <= d < pd.Timestamp(fim)]

    def dia(self, data, dia_n=1) -> DiaMkt:
        data = pd.Timestamp(data).normalize()
        b = self.m15[self.m15.dia == data]
        m1 = self.m1[(self.m1.index >= data) & (self.m1.index < data + pd.Timedelta(days=1))]
        t15 = b.index.values
        t1 = m1.index.values
        ini = np.searchsorted(t1, t15)
        fim = np.searchsorted(t1, t15 + np.timedelta64(15, "m"))
        ult = t1[-1]
        if "ultima_continua" in m1 and m1.ultima_continua.any():
            ult = m1.index[m1.ultima_continua.values][-1].to_datetime64()
        flat_i = int(np.searchsorted(t1, ult - np.timedelta64(MIN_FLAT_ANTES_FIM, "m"), side="right") - 1)
        semana = data.isocalendar()[:2]
        vs = any(tuple(v.isocalendar()[:2]) == tuple(semana) for v in self.venc)
        vd = any(v == data for v in self.venc)
        return DiaMkt(data, t15, b[["open", "high", "low", "close", "real_volume"]].to_numpy(float),
                      t1, m1[["open", "high", "low", "close"]].to_numpy(float), ini, fim, flat_i, dia_n, vs, vd)


def _hm(t):
    return str(np.datetime64(t, "m"))[11:16]


def _f(x):
    return f"{x:.0f}"


def montar_pacote(mk: Mercado, dia: DiaMkt, k: int, estado: dict, eventos_dia: list, decisoes_dia: list,
                  n_velas=40) -> str:
    """Pacote textual na vela M15 `k` JA FECHADA. So usa indices <= k e dias anteriores."""
    data = dia.data
    b = mk.m15
    hoje = b[b.dia == data].iloc[: k + 1]
    ant = b[b.dia < data]
    dias_ant = [d for d in mk.dias if d < data]
    ontem = mk.diario.loc[dias_ant[-1]] if dias_ant else None
    hora_fech = np.datetime64(hoje.index[-1], "m") + np.timedelta64(15, "m")
    L = []
    L.append(f"SIMULACAO dia {dia.dia_n} | {DIAS_PT[data.weekday()]} | semana de vencimento de opcoes/contrato: "
             f"{'sim' if dia.venc_semana else 'nao'}{' (HOJE e o vencimento)' if dia.venc_dia else ''}")
    flat_h = _hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m"))
    L.append(f"Hora atual (fechamento da vela M15): {str(hora_fech)[11:16]} | o motor zera tudo as {flat_h}")
    ab = hoje.open.iloc[0]
    L.append(f"Abertura do dia: {_f(ab)}")
    if ontem is not None:
        gap = ab - ontem.close
        L.append(f"Gap vs fechamento anterior: {gap:+.0f} pts ({gap / ontem.close * 100:+.2f}%) | ontem: max {_f(ontem.high)} min {_f(ontem.low)} fech {_f(ontem.close)}")
    L.append(f"Hoje ate agora: max {_f(hoje.high.max())} min {_f(hoje.low.min())} amplitude {_f(hoje.high.max() - hoje.low.min())} | ultimo fechamento {_f(hoje.close.iloc[-1])}")
    atr15 = hoje.atr_m15.iloc[-1]
    atrd = mk.diario.loc[dias_ant[-1], "atr_d"] if dias_ant else float("nan")
    L.append(f"ATR M15 (14): {atr15:.0f} pts | ATR diario (14, ate ontem): {atrd:.0f} pts")
    L.append("")
    L.append("DIARIO (ultimos 10 dias fechados, mais antigo primeiro; d-1 = ontem): O H L C Volume")
    ult10 = dias_ant[-10:]
    for i, d in enumerate(ult10):
        r = mk.diario.loc[d]
        L.append(f"d-{len(ult10) - i} {_f(r.open)} {_f(r.high)} {_f(r.low)} {_f(r.close)} {r.vol:.0f}")
    L.append("")
    L.append("H1 (hoje e 2 dias anteriores; 'parcial' = hora ainda nao completa): hora O H L C Volume")
    for off, d in ((2, dias_ant[-2] if len(dias_ant) >= 2 else None), (1, dias_ant[-1] if dias_ant else None), (0, data)):
        if d is None:
            continue
        x = hoje if off == 0 else b[b.dia == d]
        h = x.groupby(x.index.floor("h")).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"),
                                              c=("close", "last"), v=("real_volume", "sum"), n=("close", "size"))
        for ti, r in h.iterrows():
            parc = " parcial" if (off == 0 and r.n < 4) else ""
            L.append(f"d-{off} {ti.strftime('%H:%M')} {_f(r.o)} {_f(r.h)} {_f(r.l)} {_f(r.c)} {r.v:.0f}{parc}")
    L.append("")
    L.append(f"M15 (ultimas {n_velas} velas fechadas; a ultima e a vela que acabou de fechar): hora O H L C Volume")
    ult = pd.concat([ant.iloc[-n_velas:], hoje]).iloc[-n_velas:]
    marcado = False
    for ti, r in ult.iterrows():
        if ti.normalize() == data and not marcado:
            L.append("--- hoje ---")
            marcado = True
        pre = "" if ti.normalize() == data else "ontem "
        L.append(f"{pre}{ti.strftime('%H:%M')} {_f(r.open)} {_f(r.high)} {_f(r.low)} {_f(r.close)} {r.real_volume:.0f}")
    L.append("")
    p = estado.get("pos")
    last = hoje.close.iloc[-1]
    if p:
        aberto = (last - p["preco"]) * p["dir"]
        L.append(f"POSICAO: {p['lado']} {p['n']} contrato(s) a {_f(p['preco'])} | stop {_f(p['stop'])} | alvo {_f(p['alvo']) if p['alvo'] else 'sem alvo'} | resultado aberto {aberto:+.0f} pts/contrato")
    else:
        L.append("POSICAO: nenhuma")
    o = estado.get("pend")
    if o:
        ate = _hm(dia.m15_t[min(o["last_k"], len(dia.m15_t) - 1)] + np.timedelta64(15, "m"))
        L.append(f"ORDEM PENDENTE: {o['lado']} limite {_f(o['preco'])} x{o['n']} | stop {_f(o['stop'])} | alvo {_f(o['alvo']) if o['alvo'] else 'sem alvo'} | valida ate {ate}")
    else:
        L.append("ORDEM PENDENTE: nenhuma")
    L.append(f"RESULTADO DO DIA (liquido de custo): {estado.get('pts', 0):+.0f} pts-contrato = R$ {estado.get('brl', 0):+.2f} em {estado.get('ntrades', 0)} operacao(oes)")
    L.append("")
    L.append("EVENTOS DE EXECUCAO DE HOJE:")
    L.extend(["  " + e for e in eventos_dia] or ["  (nenhum)"])
    L.append("")
    L.append("SUAS DECISOES ANTERIORES HOJE:")
    L.extend(["  " + d for d in decisoes_dia] or ["  (esta e a primeira decisao do dia)"])
    L.append("")
    L.append("Decida agora (responda so o JSON).")
    return "\n".join(L)
