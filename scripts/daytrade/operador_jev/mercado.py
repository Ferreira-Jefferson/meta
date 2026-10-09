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


def derivados_calc(o, h, l, c, v, vprev, ont, atrd, atr15) -> dict:
    """Numeros DERIVADOS do pacote na vela k (funcao pura; arrays de HOJE ate a vela k fechada, indice <= k).

    o,h,l,c,v: velas M15 de hoje (1a ... k). vprev: volumes das velas M15 anteriores a de hoje (>= 20 se houver).
    ont = (max, min, fech) de ontem ou None. atrd/atr15: ATR diario (ate ontem) e ATR M15 (so passado).
    So usa dados com indice <= k: nao ha como enxergar o futuro por construcao.
    """
    n = len(c)
    ab, last = float(o[0]), float(c[-1])
    d: dict = dict(n=n, ab=ab, last=last)
    desl = last - ab
    soma = float((h - l).sum())
    amp = float(h.max() - l.min())
    d.update(desl=desl, desl_atrd=desl / atrd if atrd else float("nan"), er=abs(desl) / soma if soma > 0 else 0.0,
             desl_amp=abs(desl) / amp if amp > 0 else 0.0, amp=amp, amp_atrd=amp / atrd if atrd else float("nan"),
             pct_acima_ab=float((c > ab).mean() * 100))
    # volume da ultima vela contra as 10/20 anteriores (inclui velas de ontem no inicio do dia)
    vv = np.concatenate([np.asarray(vprev, float), np.asarray(v, float)])
    vl = vv[-1]
    for m in (10, 20):
        ref = vv[-1 - m:-1]
        d[f"vol_r{m}"] = float(vl / ref.mean()) if len(ref) and ref.mean() > 0 else float("nan")
    # extremos do dia e idade (velas desde a ultima vez em que o extremo foi tocado)
    hi, lo = float(h.max()), float(l.min())
    d.update(hi=hi, lo=lo, vel_hi=int(np.argmax(h[::-1])), vel_lo=int(np.argmin(l[::-1])))
    d["rompeu_dia"] = ("alta" if n > 1 and last > h[:-1].max() else "baixa" if n > 1 and last < l[:-1].min() else "nenhum")
    # devolucao do deslocamento maximo do dia
    up, dn = hi - ab, ab - lo
    if up >= dn and up > 0:
        d.update(dev_lado="alta", dev=(hi - last) / up)
    elif dn > 0:
        d.update(dev_lado="baixa", dev=(last - lo) / dn)
    else:
        d.update(dev_lado="nenhum", dev=0.0)
    # ontem
    if ont is not None:
        oh, ol, oc = ont
        d.update(ont_h=oh, ont_l=ol, ont_c=oc, hoje_rompeu_ont_h=bool(hi > oh), hoje_rompeu_ont_l=bool(lo < ol))
        d["pos_ont"] = "acima" if last > oh else "abaixo" if last < ol else "dentro"
        d["dist_ont_h"] = last - oh
        d["dist_ont_l"] = last - ol
        d["pos_faixa_ont"] = (last - ol) / (oh - ol) if oh > ol else float("nan")
        gap = ab - oc
        d.update(gap=gap, gap_atrd=gap / atrd if atrd else float("nan"))
        if gap != 0:
            d["gap_preenchido"] = (ab - last) / gap          # 0 = na abertura; 1 = fechou o gap; <0 = ampliou
            d["gap_max_preenchido"] = ((ab - lo) / gap) if gap > 0 else ((hi - ab) / -gap)
        else:
            d["gap_preenchido"] = d["gap_max_preenchido"] = None
    else:
        d.update(ont_h=None)
    # faixa das 12 velas anteriores a ultima e a vela atual
    if n >= 13:
        fh, fl = float(h[-13:-1].max()), float(l[-13:-1].min())
        d.update(faixa12=fh - fl, faixa12_atrd=(fh - fl) / atrd if atrd else float("nan"),
                 f12_pos="acima" if last > fh else "abaixo" if last < fl else "dentro",
                 ult_amp=float(h[-1] - l[-1]), ult_amp_atr=float((h[-1] - l[-1]) / atr15) if atr15 else float("nan"))
    # ultimas 8 velas: faixa e volume
    if n >= 8:
        f8 = float(h[-8:].max() - l[-8:].min())
        d.update(faixa8=f8, faixa8_atrd=f8 / atrd if atrd else float("nan"),
                 vol8_rel=float(np.mean(v[-8:]) / np.mean(v)) if np.mean(v) > 0 else float("nan"))
    # ultimo topo / fundo de swing de HOJE: fractal de 2 velas de cada lado, ja confirmado (indice <= k-2)
    topo = fundo = None
    for i in range(n - 3, 1, -1):
        if topo is None and h[i] > max(h[i - 1], h[i - 2], h[i + 1], h[i + 2]):
            topo = (i, float(h[i]))
        if fundo is None and l[i] < min(l[i - 1], l[i - 2], l[i + 1], l[i + 2]):
            fundo = (i, float(l[i]))
        if topo and fundo:
            break
    d.update(swing_topo=topo, swing_fundo=fundo)
    return d


def linhas_derivadas(mk: "Mercado", dia: DiaMkt, k: int) -> list[str]:
    """Linhas de texto DERIVADAS (ja calculadas) para o pacote da vela k fechada. So velas <= k e dias anteriores."""
    b = mk.m15
    data = dia.data
    hoje = b[b.dia == data].iloc[: k + 1]
    ant = b[b.dia < data]
    dias_ant = [x for x in mk.dias if x < data]
    ontem = mk.diario.loc[dias_ant[-1]] if dias_ant else None
    atrd = float(mk.diario.loc[dias_ant[-1], "atr_d"]) if dias_ant else float("nan")
    atr15 = float(hoje.atr_m15.iloc[-1])
    ont = (float(ontem.high), float(ontem.low), float(ontem.close)) if ontem is not None else None
    d = derivados_calc(hoje.open.to_numpy(float), hoje.high.to_numpy(float), hoje.low.to_numpy(float), hoje.close.to_numpy(float),
                       hoje.real_volume.to_numpy(float), ant.real_volume.to_numpy(float)[-20:], ont, atrd, atr15)
    return formata_derivados(d)


def _f2(x):
    return "n/d" if x is None or x != x else f"{x:.2f}"


def formata_derivados(d: dict) -> list[str]:
    f1 = _f2
    L = ["DERIVADOS (calculados so com velas fechadas; ATRd = ATR diario ate ontem):"]
    L.append(f"  Deslocamento desde a abertura: {d['desl']:+.0f} pts = {f1(d['desl_atrd'])} ATRd | amplitude do dia {d['amp']:.0f} pts = {f1(d['amp_atrd'])} ATRd")
    L.append(f"  Eficiencia direcional do dia: |fech-abertura| / soma das amplitudes das {d['n']} velas = {f1(d['er'])} | |deslocamento| / amplitude do dia = {f1(d['desl_amp'])} | fechamentos acima da abertura: {d['pct_acima_ab']:.0f}% das velas")
    L.append(f"  Volume da ultima vela / media das 10 anteriores = {f1(d['vol_r10'])} | / media das 20 anteriores = {f1(d['vol_r20'])} (as anteriores incluem velas de ontem no inicio do dia)")
    L.append(f"  Maxima do dia {d['hi']:.0f} (ha {d['vel_hi']} velas desde que foi tocada) | minima do dia {d['lo']:.0f} (ha {d['vel_lo']} velas) | ultima vela fechou alem da max/min do dia ate a vela anterior: {d['rompeu_dia']}")
    L.append(f"  Deslocamento maximo do dia a partir da abertura foi para {d['dev_lado']}; o preco devolveu {d['dev'] * 100:.0f}% dele")
    if d.get("ont_h") is not None:
        L.append(f"  Ontem: max {d['ont_h']:.0f} min {d['ont_l']:.0f} | ultimo fechamento esta {d['pos_ont']} da faixa de ontem ({d['dist_ont_h']:+.0f} pts da max de ontem, {d['dist_ont_l']:+.0f} pts da min; posicao {f1(d['pos_faixa_ont'])} da faixa) | hoje ja passou a max de ontem: {'sim' if d['hoje_rompeu_ont_h'] else 'nao'}, a min de ontem: {'sim' if d['hoje_rompeu_ont_l'] else 'nao'}")
        if d["gap_preenchido"] is None:
            L.append("  Gap: nenhum")
        elif abs(d["gap_atrd"]) < 0.15:
            L.append(f"  Gap: {d['gap']:+.0f} pts = {f1(d['gap_atrd'])} ATRd (irrelevante: menor que 0,15 ATRd; sem fracao de preenchimento)")
        else:
            L.append(f"  Gap: {d['gap']:+.0f} pts = {f1(d['gap_atrd'])} ATRd | agora {d['gap_preenchido'] * 100:.0f}% preenchido (negativo = gap ampliando; 100% = voltou ao fechamento de ontem) | maximo ja preenchido hoje {d['gap_max_preenchido'] * 100:.0f}%")
    if "faixa12" in d:
        L.append(f"  Faixa das 12 velas anteriores a ultima: {d['faixa12']:.0f} pts = {f1(d['faixa12_atrd'])} ATRd | ultima vela fechou {d['f12_pos']} dessa faixa | amplitude da ultima vela {d['ult_amp']:.0f} pts = {f1(d['ult_amp_atr'])} ATR M15")
    if "faixa8" in d:
        L.append(f"  Ultimas 8 velas: faixa {d['faixa8']:.0f} pts = {f1(d['faixa8_atrd'])} ATRd | volume medio dessas 8 / volume medio das velas de hoje = {f1(d['vol8_rel'])}")
    t, f = d["swing_topo"], d["swing_fundo"]
    L.append("  Ultimo topo de swing M15 de hoje (confirmado): " + (f"{t[1]:.0f} (ha {d['n'] - 1 - t[0]} velas; ultimo fechamento {d['last'] - t[1]:+.0f} pts dele)" if t else "nenhum")
             + " | ultimo fundo de swing: " + (f"{f[1]:.0f} (ha {d['n'] - 1 - f[0]} velas; ultimo fechamento {d['last'] - f[1]:+.0f} pts dele)" if f else "nenhum"))
    return L


def montar_pacote(mk: Mercado, dia: DiaMkt, k: int, estado: dict, eventos_dia: list, decisoes_dia: list,
                  n_velas=40, derivados=False) -> str:
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
    if derivados:
        L.extend(linhas_derivadas(mk, dia, k))
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


PREAMBULO = ("Mini-indice Bovespa (WIN), pontos; 1 ponto = R$ 0,20 por contrato; tick = 5 pontos. "
             "Abaixo, o estado do mercado na vela M15 que acabou de fechar (so velas fechadas; a data real e omitida). "
             "ATR M15 = media de 14 amplitudes verdadeiras; ATR diario = media de 14 amplitudes diarias ate ontem.")


def montar_estado(mk: Mercado, dia: DiaMkt, k: int, pos=None, derivados=False) -> str:
    """Estado textual para o endpoint de decisoes: so mercado (sem posicao/ordens/resultado do dia) -> as respostas
    nao dependem da trajetoria da simulacao. Com `pos`, acrescenta a linha POSICAO (chamada de gestao)."""
    est = dict(pos=pos, pend=None, pts=0, brl=0, ntrades=0)
    txt = montar_pacote(mk, dia, k, est, [], [], derivados=derivados)
    cab = txt.split("\nPOSICAO:")[0]
    if pos:
        linha = [x for x in txt.split("\n") if x.startswith("POSICAO:")][0]
        cab += "\n" + linha + f" | entrada na vela {_hm(dia.m15_t[pos['k_ent']])}"
    return PREAMBULO + "\n" + cab
