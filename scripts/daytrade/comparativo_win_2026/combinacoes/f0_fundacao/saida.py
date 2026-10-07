"""Simulador de saida generico sobre os ticks de `dados.ticks()`, com as regras do Testador (docstring de dados.py):

  - stop: dispara quando o `last` toca/atravessa o nivel (compra: last <= nivel) e executa no `last` desse tick
    (gap -> sai pior que o nivel);
  - alvo com `alvo_limite=True`: ordem-limite, enche quando o `last` toca o nivel e executa NO PRECO DO LIMITE;
    com `alvo_limite=False`: gatilho a mercado, executa no `last` do tick que tocou;
  - zeragem a mercado no `last` do 1o tick com horario >= hora_zera (o stop/alvo e' checado ate' o tick ANTERIOR,
    como no port do WinDeslocamentoMatinal); sem tick >= hora_zera no dia -> sai no ultimo tick ('fim_dados').
  - por padrao stop/alvo valem a partir do tick SEGUINTE ao da entrada (o EA arma no OnTick do tick do fill);
    `inclui_tick_entrada=True` checa ja' o proprio tick (caso do WinDeslocamentoMatinal, cujo stop e' do EA).
    Ticks com o MESMO ms sao indistinguiveis: "seguinte" = 1o tick com t > t_entrada.
stop_pts / alvo_pts = None (ou NaN, ou <= 0) desligam o respectivo nivel.

Uso: from saida import simula_saida, simula_saida_lote
     python saida.py valida   -> reproduz as saidas do WinDeslocamentoMatinal com o mesmo stop
"""
from __future__ import annotations

import sys
import types
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]
sys.path.insert(0, str(BASE))
import dados as D  # noqa: E402

DIA_MS = 86_400_000


@lru_cache(maxsize=16)
def _ticks(dia: date):
    t, p, _v, _r = D.ticks(dia)
    return np.asarray(t, np.int64), np.asarray(p, float)


def _hz_ms(hora_zera: str) -> int:
    h, m = hora_zera.split(":")
    return (int(h) * 60 + int(m)) * 60000


def _ativo(x) -> bool:
    return x is not None and np.isfinite(x) and x > 0


def _um(t, p, i0, iz, lado, pe, stop_pts, alvo_pts, alvo_limite):
    """Nucleo: ticks [i0, iz) para stop/alvo; zera em iz. Devolve (indice, preco, motivo)."""
    n = len(t)
    fim = min(iz, n)
    ks = ka = None
    if i0 < fim:
        seg = p[i0:fim]
        if _ativo(stop_pts):
            nv = pe - lado * stop_pts
            m = seg <= nv if lado > 0 else seg >= nv
            k = int(np.argmax(m))
            ks = k if m[k] else None
        if _ativo(alvo_pts):
            nv = pe + lado * alvo_pts
            m = seg >= nv if lado > 0 else seg <= nv
            k = int(np.argmax(m))
            ka = k if m[k] else None
    if ks is not None and (ka is None or ks <= ka):
        return i0 + ks, float(p[i0 + ks]), "stop"
    if ka is not None:
        k = i0 + ka
        return k, (pe + lado * alvo_pts) if alvo_limite else float(p[k]), "alvo"
    if iz < n:
        k = max(iz, min(i0, n - 1))
        return k, float(p[k]), "zera"
    return n - 1, float(p[-1]), "fim_dados"


def simula_saida(t_entrada_ms: int, lado: int, preco_entrada: float, stop_pts, alvo_pts, hora_zera: str = "17:50",
                 alvo_limite: bool = True, inclui_tick_entrada: bool = False):
    """-> (t_saida_ms, preco_saida, motivo). motivo em {stop, alvo, zera, fim_dados}."""
    t_entrada_ms = int(t_entrada_ms)
    d0 = t_entrada_ms // DIA_MS * DIA_MS
    dia = pd.Timestamp(d0, unit="ms").date()
    t, p = _ticks(dia)
    i0 = int(np.searchsorted(t, t_entrada_ms, "left" if inclui_tick_entrada else "right"))
    iz = int(np.searchsorted(t, d0 + _hz_ms(hora_zera), "left"))
    k, px, mot = _um(t, p, i0, iz, int(lado), float(preco_entrada), stop_pts, alvo_pts, alvo_limite)
    return int(t[k]), px, mot


def simula_saida_lote(t_entrada_ms, lado, preco_entrada, stop_pts, alvo_pts, hora_zera: str = "17:50",
                      alvo_limite: bool = True, inclui_tick_entrada: bool = False) -> pd.DataFrame:
    """Versao em lote: arrays (ou escalares para stop/alvo). Agrupa por pregao, carrega os ticks uma vez, acha os
    indices de inicio/zeragem de todas as entradas com um searchsorted e cada saida com argmax numa fatia (nada de
    loop por tick). -> DataFrame(t_saida_ms, preco_saida, motivo, pontos), na ordem da entrada."""
    te = np.asarray(t_entrada_ms, np.int64)
    m = len(te)
    ld = np.broadcast_to(np.asarray(lado, int), (m,))
    pe = np.broadcast_to(np.asarray(preco_entrada, float), (m,))
    sp = np.broadcast_to(np.asarray(np.nan if stop_pts is None else stop_pts, float), (m,))
    ap = np.broadcast_to(np.asarray(np.nan if alvo_pts is None else alvo_pts, float), (m,))
    ts_out = np.zeros(m, np.int64); px_out = np.zeros(m); mot = np.empty(m, object)
    d0 = te // DIA_MS * DIA_MS
    hz = _hz_ms(hora_zera)
    for dd in np.unique(d0):
        sel = np.flatnonzero(d0 == dd)
        t, p = _ticks(pd.Timestamp(int(dd), unit="ms").date())
        i0s = np.searchsorted(t, te[sel], "left" if inclui_tick_entrada else "right")
        iz = int(np.searchsorted(t, dd + hz, "left"))
        for q, i in enumerate(sel):
            k, px, mo = _um(t, p, int(i0s[q]), iz, int(ld[i]), float(pe[i]), sp[i], ap[i], alvo_limite)
            ts_out[i], px_out[i], mot[i] = t[k], px, mo
    return pd.DataFrame(dict(t_saida_ms=ts_out, preco_saida=px_out, motivo=mot, pontos=ld * (px_out - pe)))


# --------------------------------------------------------------------------- validacao no WinDeslocamentoMatinal
def _deslocamento_com_stop():
    """Roda o port do WinDeslocamentoMatinal capturando o NIVEL do stop de cada operacao (o ultimo NoTick antes de
    fechar e' o do stop). Nao altera o port: so' embrulha `nt` e `dados.trade` no namespace dele."""
    import port_deslocamento as PD
    ult = {}
    nt0 = PD.nt

    def nt(v):
        r = nt0(v); ult["v"] = r; return r

    def trade(*a, **k):
        r = D.trade(*a, **k); r["_stop"] = ult.get("v"); return r
    shim = types.SimpleNamespace(**{k: getattr(D, k) for k in dir(D) if not k.startswith("__")})
    shim.trade = trade
    PD.nt, PD.dados = nt, shim
    try:
        def gt(d):
            t, p, _v, _r = D.ticks(d)
            return t, p
        tr, _s, _q, _dg = PD.rodar(D.dias(), D.m1(), gt, log=lambda *a, **k: None)
    finally:
        PD.nt, PD.dados = nt0, D
    return pd.DataFrame(tr)


def valida():
    ref = pd.read_csv(BASE / "resultados" / "WinDeslocamentoMatinal.csv")
    rr = _deslocamento_com_stop()
    same = len(rr) == len(ref) and (rr[["entrada", "saida", "preco_saida"]].values == ref[["entrada", "saida", "preco_saida"]].values).all()
    print(f"re-rodada do port com captura do stop: {len(rr)} ops, identica ao CSV: {same}", flush=True)
    te = np.array([D.ms(x) for x in rr.entrada])
    stop_pts = np.abs(rr.preco_entrada - rr._stop).to_numpy()
    sim = simula_saida_lote(te, rr.lado.to_numpy(), rr.preco_entrada.to_numpy(), stop_pts, None,
                            hora_zera="18:20", inclui_tick_entrada=True)
    sx = np.array([D.ms(x) for x in rr.saida])
    mot_ref = rr.motivo.replace({"zera": "zera", "stop": "stop"}).to_numpy()
    ok_t = sim.t_saida_ms.to_numpy() == sx
    ok_p = np.isclose(sim.preco_saida.to_numpy(), rr.preco_saida.to_numpy())
    ok_m = sim.motivo.to_numpy() == mot_ref
    ok = ok_t & ok_p & ok_m
    print(f"simulador reproduz a saida (horario, preco e motivo): {int(ok.sum())} de {len(ok)}", flush=True)
    print(f"  so' preco: {int(ok_p.sum())} | so' horario: {int(ok_t.sum())} | motivos ref {pd.Series(mot_ref).value_counts().to_dict()}", flush=True)
    # mesma conferencia com a funcao escalar (amostra)
    n_esc = 0
    for i in range(0, len(rr), 7):
        r = simula_saida(te[i], rr.lado[i], rr.preco_entrada[i], stop_pts[i], None, "18:20", True, True)
        n_esc += (r[0] == sx[i]) and np.isclose(r[1], rr.preco_saida[i])
    print(f"  funcao escalar (amostra a cada 7): {n_esc} de {len(range(0, len(rr), 7))}", flush=True)
    for i in np.flatnonzero(~ok):
        print(f"  DIFERE {rr.entrada[i]} lado {rr.lado[i]} ref {rr.saida[i]} {rr.preco_saida[i]} {rr.motivo[i]} | sim "
              f"{D.ts(sim.t_saida_ms[i])} {sim.preco_saida[i]} {sim.motivo[i]}", flush=True)
    return int(ok.sum()), len(ok)


def valida_wdo():
    """Segunda conferencia (caminho do ALVO limite): WdoRetangulo, stop e alvo fixos capturados no fill, zera 18:20."""
    import port_wdo_retangulo as P
    orig = P.EA._fecha

    def _fecha(self, t_ms, px, motivo):
        ps = self.pos; orig(self, t_ms, px, motivo)
        self.trades[-1]["_stop"], self.trades[-1]["_alvo"] = ps["stop"], ps["alvo"]
    P.EA._fecha = _fecha
    try:
        ea = P.roda("WdoRetangulo", P.Cfg(tick=0.5), D.INICIO, D.FIM, verbose=False)
    finally:
        P.EA._fecha = orig
    rr = pd.DataFrame(ea.trades)
    te = np.array([D.ms(x) for x in rr.entrada]); pe = rr.preco_entrada.to_numpy()
    sp = np.abs(pe - rr._stop.astype(float).to_numpy()); ap = np.abs(pe - rr._alvo.astype(float).to_numpy())
    s = simula_saida_lote(te, rr.lado.to_numpy(), pe, sp, ap, hora_zera="18:20", alvo_limite=True)
    ok = ((s.t_saida_ms.to_numpy() == np.array([D.ms(x) for x in rr.saida]))
          & np.isclose(s.preco_saida.to_numpy(), rr.preco_saida.to_numpy())
          & (s.motivo.to_numpy() == rr.motivo.replace({"zeragem": "zera"}).to_numpy()))
    print(f"WdoRetangulo (stop+alvo limite, motivos {rr.motivo.value_counts().to_dict()}): {int(ok.sum())} de {len(ok)}", flush=True)
    return int(ok.sum()), len(ok)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "valida":
        valida()
        valida_wdo()
