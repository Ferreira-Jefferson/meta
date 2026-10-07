"""Varredura de TODAS as paridades dos setups de Larry Williams, por ativo.

Unidade de trabalho = (setup, ativo). Cada unidade percorre a grade INTEIRA do setup
(parametros x saida x stop x lados x filtro de tendencia x filtro de dia da semana) e,
para cada celula, mede IS e OOS com slippage 0/1/2 ticks. O resultado de cada unidade vai
para `_resultados/<SETUP>/<ATIVO>.npz`; a escolha (so' no IS) e o relatorio ficam em
`lw_relatorio.py`.

Paralelismo (AGENTS.md): ProcessPoolExecutor com submit/as_completed (nunca pool.map),
`redirect_stdout` por unidade, `flush=True`, cada unidade imprime a linha dela ao terminar.
Workers limitados (padrao 4; memoria medida no smoke: ver --smoke).

Uso:
    python lw_sweep.py --smoke                 # 3 acoes + WIN, grade subamostrada, mede tempo e RSS
    python lw_sweep.py --full --workers 4      # varredura cheia
    python lw_sweep.py --full --setups VB,OOPS # so' alguns setups
"""
from __future__ import annotations

import argparse
import functools
import io
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import lw_dados as D  # noqa: E402
import lw_setups as S  # noqa: E402
import lw_sim as M  # noqa: E402
from backtest.intraday.report import LinhaResultado, tabela  # noqa: E402

SAIDA_DIR = AQUI / "_resultados"
SLIPS = (0.0, 1.0, 2.0)
JANELAS = ("IS", "OOS")
#: Colunas gravadas por (celula, slip, janela). Sufixo g = COM portao de caixa (capital minimo real);
#: sem sufixo = EDGE (capital nocional: todos os trades entram).
COLS = ("n", "win", "ganho_pct", "perda_pct", "ganho_brl", "perda_brl", "exp_pct", "exp_brl",
        "liquido", "maxdd_brl", "n_g", "cap_final_g", "pulados_g", "cens_g")
NC = len(COLS)

DIAS_TDW = {"todos": None, "sem_seg": (1, 2, 3, 4), "sem_ter": (0, 2, 3, 4), "sem_qua": (0, 1, 3, 4),
            "sem_qui": (0, 1, 2, 4), "sem_sex": (0, 1, 2, 3)}
TDW_TODOS = tuple(DIAS_TDW)
TEND = ("NENHUM", "SWING", "SMA50")
STOP_FRAC = (("frac", 0.5), ("frac", 1.0), ("sem", 0.0))
LADOS3 = ("CV", "C", "V")


# ----------------------------------------------------------------------------
# Definicao da grade
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class DefSetup:
    nome: str
    classes: tuple[str, ...]
    eixos: dict            # nome do eixo -> lista de valores (ordem = vizinhanca)
    construtor: object     # (at, params:dict) -> Sinais   (None p/ TRES_BARRAS)

    @property
    def nomes_eixos(self) -> list[str]:
        return list(self.eixos)

    def celulas(self) -> list[dict]:
        nomes = self.nomes_eixos
        return [dict(zip(nomes, v)) for v in itertools.product(*[self.eixos[n] for n in nomes])]

    def indices(self) -> list[tuple[int, ...]]:
        return list(itertools.product(*[range(len(self.eixos[n])) for n in self.nomes_eixos]))


def _cal(at):
    return at.calendario()


def _b_vb(at, p):
    return S.setup_vb(at.o, at.h, at.l, at.c, *p["k"])


def _b_oops(at, p):
    return S.setup_oops(at.o, at.h, at.l, at.c, p["gap_min"])


def _b_smash(at, p):
    return S.setup_smash(at.o, at.h, at.l, at.c, p["n"], p["excl_out"])


def _b_hsmash(at, p):
    return S.setup_hsmash(at.o, at.h, at.l, at.c, p["zona"], p["close_contra"])


def _b_outside(at, p):
    return S.setup_outside(at.o, at.h, at.l, at.c, p["modo"], p["venda"])


def _b_gsv(at, p):
    kc, kv = p["k"]
    return S.setup_gsv(at.o, at.h, at.l, at.c, p["n"], kc, kv)


def _b_wr(at, p):
    return S.setup_wr(at.o, at.h, at.l, at.c, p["n"], p["espera"], p["gatilho"], p["modo"], p["toque"])


def _b_uo(at, p):
    return S.setup_uo(at.o, at.h, at.l, at.c, p["compra_max"], p["venda_min"], p["validade"], p["modo"])


def _b_tdm(at, p):
    cal = _cal(at)
    return S.setup_tdm(at.o, at.h, at.l, at.c, cal["dom_pregao"], cal["mes"], p["dias"], p["meses"])


def _b_tdw(at, p):
    cal = _cal(at)
    return S.setup_tdw(at.o, at.h, at.l, at.c, cal["dow"], (p["dia"],), (p["dia"],))


TODAS = ("ACAO", "WIN", "WDO", "ETF_BTC")
MODOS = ("A_MERCADO_NA_ABERTURA", "LIMITE_NO_FECHAMENTO_S")
SAIDAS_COMUNS = (("BAILOUT", 0), ("FECHAMENTO", 0), ("TEMPO", 3))


def definicoes() -> dict[str, DefSetup]:
    d = {}
    d["VB"] = DefSetup("VB", TODAS, {
        "p_k": [(0.3, 0.3), (0.5, 0.5), (1.0, 1.0), (0.4, 2.0)],
        "stop": list(STOP_FRAC),
        "saida": [("BAILOUT", 0), ("BAILOUT", 1), ("FECHAMENTO", 0), ("TEMPO", 3), ("REVERSAO", 0)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_vb)
    d["OOPS"] = DefSetup("OOPS", TODAS, {
        "p_gap_min": [0.0, 0.1, 0.25],
        "stop": list(STOP_FRAC),
        "saida": [("ABERTURA_SEGUINTE", 0), ("BAILOUT", 0), ("FECHAMENTO", 0), ("TEMPO", 3)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_oops)
    d["SMASH"] = DefSetup("SMASH", TODAS, {
        "p_n": [1, 3, 5, 8], "p_excl_out": [False, True],
        "stop": [("abs", 0.5), ("frac", 0.5), ("frac", 1.0)],
        "saida": [("BAILOUT", 0), ("TEMPO", 3), ("RR", 2.0), ("FECHAMENTO", 0)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_smash)
    d["HSMASH"] = DefSetup("HSMASH", TODAS, {
        "p_zona": [0.15, 0.25], "p_close_contra": [False, True],
        "stop": [("abs", 0.5), ("frac", 0.5), ("frac", 1.0)],
        "saida": [("BAILOUT", 0), ("TEMPO", 3), ("RR", 2.0), ("FECHAMENTO", 0)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_hsmash)
    d["OUTSIDE"] = DefSetup("OUTSIDE", TODAS, {
        "p_modo": list(MODOS), "p_venda": [False, True],
        "stop": list(STOP_FRAC),
        "saida": list(SAIDAS_COMUNS),
        "lados": ["CV"], "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_outside)
    d["GSV"] = DefSetup("GSV", TODAS, {
        "p_n": [1, 2, 4], "p_k": [(0.8, 1.2), (0.5, 0.5), (1.0, 1.0)],
        "stop": list(STOP_FRAC),
        "saida": list(SAIDAS_COMUNS),
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_gsv)
    d["WR"] = DefSetup("WR", TODAS, {
        "p_n": [10, 14], "p_espera": [5], "p_gatilho": [95.0, 85.0], "p_toque": [100.0, 95.0],
        "p_modo": list(MODOS),
        "stop": list(STOP_FRAC),
        "saida": [("BAILOUT", 0), ("TEMPO", 5), ("OSC", 0)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_wr)
    d["UO"] = DefSetup("UO", TODAS, {
        "p_compra_max": [30.0, 35.0], "p_venda_min": [50.0, 70.0], "p_validade": [10],
        "p_modo": list(MODOS),
        "stop": list(STOP_FRAC),
        "saida": [("OSC", 0), ("BAILOUT", 0), ("TEMPO", 5)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_uo)
    d["TDM"] = DefSetup("TDM", TODAS, {
        "p_dias": [(1,), (2,), (5,), (10,), (15,), (20,), (1, 2, 3)],
        "p_meses": [(), (1, 2, 10)],
        "stop": list(STOP_FRAC),
        "saida": [("TEMPO", 3), ("BAILOUT", 0), ("FECHAMENTO", 0)],
        "lados": ["C"], "tend": list(TEND), "tdw": list(TDW_TODOS)}, _b_tdm)
    d["TDW"] = DefSetup("TDW", TODAS, {
        "p_dia": [0, 1, 2, 3, 4],
        "stop": list(STOP_FRAC),
        "saida": [("FECHAMENTO", 0)],
        "lados": list(LADOS3), "tend": list(TEND), "tdw": ["todos"]}, _b_tdw)
    d["TRES_BARRAS"] = DefSetup("TRES_BARRAS", ("WIN", "WDO"), {
        "tf": [5, 15], "stop": [("frac", 0.5), ("frac", 1.0), ("frac", 2.0)],
        "tend": ["SWING", "SMA50"]}, None)
    return d


# ----------------------------------------------------------------------------
# Execucao de uma celula
# ----------------------------------------------------------------------------
def monta_cfg(cel: dict) -> M.ConfigSim:
    saida, arg = cel["saida"]
    modo, frac = cel["stop"]
    return M.ConfigSim(lados=cel["lados"], stop_modo=modo, stop_frac=frac, saida=saida,
                       bailout_dias=int(arg) if saida == "BAILOUT" else 0,
                       tempo_dias=int(arg) if saida == "TEMPO" else 3,
                       rr=float(arg) if saida == "RR" else 2.0)


def tendencias_do_ativo(at) -> dict[str, np.ndarray]:
    return {"NENHUM": S.tendencia(at.h, at.l, at.c, "NENHUM"),
            "SWING": S.tendencia(at.h, at.l, at.c, "SWING"),
            "SMA50": S.tendencia(at.h, at.l, at.c, "SMA", 50)}


def _stats_janela(at, trades, capital, pregoes, slip, min_trades) -> np.ndarray:
    p = M.pnl_dos_trades(at, trades, slip)
    e = M.estatisticas(at, trades, slip, capital, pregoes, min_trades, portao=False, p=p)
    g = M.estatisticas(at, trades, slip, capital, pregoes, min_trades, portao=True, p=p)
    return np.array([e["n"], e["win_pct"], e["ganho_pct"], e["perda_pct"], e["ganho_medio"], e["perda_media"],
                     e["exp_pct"], e["exp_brl"], e["liquido"], e["maxdd_brl"], g["n"], g["capital_final"],
                     g["pulados"], float(g["censurada"])], dtype=np.float32)


def stats_da_celula(at, tr_is, tr_oos, jan, semestres, capitais, out_cel, blk_cel) -> None:
    """Preenche out_cel[slip, janela, :] e (futuros) blk_cel[bloco, 2] (n, exp_brl a 1 tick)."""
    for si, slip in enumerate(SLIPS):
        for ji, (trades, nome) in enumerate(((tr_is, "IS"), (tr_oos, "OOS"))):
            i0, i1 = jan[nome]
            out_cel[si, ji, :] = _stats_janela(at, trades, capitais[nome], i1 - i0, slip, 20)
    if blk_cel is not None:
        for bi, (b0, b1) in enumerate(semestres):
            sub = [t for t in tr_is if b0 <= t.dia_ent < b1]
            if sub:
                p = M.pnl_dos_trades(at, sub, 1.0)
                blk_cel[bi] = (len(sub), float(p["brl"].mean()))
            else:
                blk_cel[bi] = (0, np.nan)


def executa_unidade(setup: str, nome: str, saida_dir: str, passo: int = 1) -> dict:
    """Roda a grade inteira de `setup` no ativo `nome` e grava o npz. `passo>1` subamostra
    as celulas (so' smoke)."""
    t0 = time.time()
    saida_dir = Path(saida_dir)
    defn = definicoes()[setup]
    at = D.carregar(nome)
    jan = D.janelas(at)
    semestres = D.semestres_is(at) if at.futuro else []
    capitais = {j: M.capital_inicial(at, float(at.c[jan[j][0]])) for j in JANELAS}
    tends = tendencias_do_ativo(at)
    nomes = defn.nomes_eixos
    cels = defn.celulas()
    idxs = defn.indices()
    sel = list(range(0, len(cels), passo))
    out = np.full((len(cels), len(SLIPS), len(JANELAS), NC), np.nan, dtype=np.float32)
    blk = np.full((len(cels), len(semestres), 2), np.nan, dtype=np.float32) if semestres else None
    i0_is, i1_is = jan["IS"]
    i0_oos, i1_oos = jan["OOS"]

    if setup == "TRES_BARRAS":
        for ci in sel:
            cel = cels[ci]
            _, frac = cel["stop"]
            tend = tends[cel["tend"]]
            tr_is = M.gerar_trades_tres_barras(at, cel["tf"], frac, tend, i0_is, i1_is)
            tr_oos = M.gerar_trades_tres_barras(at, cel["tf"], frac, tend, i0_oos, i1_oos)
            stats_da_celula(at, tr_is, tr_oos, jan, semestres, capitais, out[ci], blk[ci] if blk is not None else None)
    else:
        eixos_p = [n for n in nomes if n.startswith("p_")]
        cache_sin = {}
        for ci in sel:
            cel = cels[ci]
            chave_p = tuple(cel[n] for n in eixos_p)
            sin = cache_sin.get(chave_p)
            if sin is None:
                if len(cache_sin) > 64:
                    cache_sin.clear()
                sin = defn.construtor(at, {n[2:]: cel[n] for n in eixos_p})
                cache_sin[chave_p] = sin
            dias = DIAS_TDW[cel["tdw"]]
            cal = at.calendario()
            sin_f = S.aplicar_filtros(sin, cal["dow"], cal["mes"], tends[cel["tend"]],
                                      dias_c=dias, dias_v=dias, usar_tendencia=cel["tend"] != "NENHUM")
            cfg = monta_cfg(cel)
            tr_is = M.gerar_trades(at, sin_f, cfg, i0_is, i1_is)
            tr_oos = M.gerar_trades(at, sin_f, cfg, i0_oos, i1_oos)
            stats_da_celula(at, tr_is, tr_oos, jan, semestres, capitais, out[ci], blk[ci] if blk is not None else None)
    (saida_dir / setup).mkdir(parents=True, exist_ok=True)
    arq = saida_dir / setup / f"{nome}.npz"
    extra = {"blk": blk} if blk is not None else {}
    np.savez_compressed(arq, out=out, feitas=np.array(sel), **extra)
    dt = time.time() - t0
    return {"setup": setup, "ativo": nome, "celulas": len(sel), "seg": dt, "rss_mb": rss_mb(),
            "linha": linha_melhor_is(at, out, cels, sel, capitais, jan, nomes), "arquivo": str(arq)}


def linha_melhor_is(at, out, cels, sel, capitais, jan, nomes) -> str:
    """Tabela padrao (12 colunas + extras) da melhor celula do ATIVO no IS (slip 1, edge), so' para
    o progresso: a ESCOLHA oficial e' entre ativos e mora em lw_relatorio.py."""
    melhor, ci_m = -np.inf, None
    for ci in sel:
        n = out[ci, 1, 0, 0]
        v = out[ci, 1, 0, 6] if at.classe == "ACAO" or at.classe == "ETF_BTC" else out[ci, 1, 0, 7]
        if n >= 20 and v == v and v > melhor:
            melhor, ci_m = v, ci
    if ci_m is None:
        return f"  {at.nome}: nenhuma celula com >=20 trades no IS"
    r = out[ci_m, 1, 0]
    capital = capitais["IS"]
    linha = LinhaResultado(
        variante=f"{at.nome} c{ci_m}", liquido_brl=float(r[8]), maxdd_brl=float(r[9]),
        win_rate_pct=float(r[1]), trades=int(r[0]), pregoes=jan["IS"][1] - jan["IS"][0],
        retorno_pct=None, maxdd_pct=None, capital_final=None,   # capital NOCIONAL: apaga as 3 colunas (report.py)
        extras={"BE emp%": f"{100.0 * r[5] / (r[4] + r[5]):.1f}".replace(".", ",") if r[4] + r[5] > 0 else "-",
                "cap.min": f"{capital:.0f}".replace(".", ",")},
        aviso="(IS, 1 tick, edge sem portao; capital nocional)")
    return tabela([linha], extras=("BE emp%", "cap.min"), largura_extra=9)


def rss_mb() -> float:
    """Memoria residente deste processo (MB), via Windows API (sem psutil)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32, ps = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        ps.GetProcessMemoryInfo.restype = wintypes.BOOL
        ok = ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1e6 if ok else float("nan")
    except Exception:
        return float("nan")


def _roda(args):
    """Wrapper de processo: captura o stdout da unidade (redirect_stdout) e devolve junto."""
    setup, nome, saida_dir, passo = args
    buf = io.StringIO()
    with redirect_stdout(buf):
        res = executa_unidade(setup, nome, saida_dir, passo)
        print(f"[{res['setup']:<11} {res['ativo']:<7}] {res['celulas']:>5} celulas  {res['seg']:7.1f}s  "
              f"pico RSS {res['rss_mb']:.0f} MB", flush=True)
        print(res["linha"], flush=True)
    return res, buf.getvalue()


@functools.lru_cache(maxsize=1)
def universo() -> dict[str, list[str]]:
    acoes, _ = D.universo_acoes()
    btc = [s for s in D.VEICULOS_BTC if D.carregar_btc(s)[0] is not None]
    return {"ACAO": acoes, "WIN": ["WIN"], "WDO": ["WDO"], "ETF_BTC": btc}


def tarefas(setups, passo=1, so_ativos=None) -> list[tuple]:
    defs = definicoes()
    uni = universo()
    out = []
    for s in setups:
        for cl in defs[s].classes:
            for a in uni[cl]:
                if so_ativos and a not in so_ativos:
                    continue
                out.append((s, a, str(SAIDA_DIR), passo))
    # futuros (M1, pesados) primeiro: terminam em paralelo com as acoes
    out.sort(key=lambda t: (t[1] not in ("WIN", "WDO"), t[0]))
    return out


def principal() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--setups", default="")
    ap.add_argument("--ativos", default="")
    ap.add_argument("--passo", type=int, default=1)
    a = ap.parse_args()
    defs = definicoes()
    setups = a.setups.split(",") if a.setups else list(defs)
    if a.smoke:
        lista = tarefas(setups, passo=max(a.passo, 25), so_ativos={"PETR4", "VALE3", "BOVA11", "WIN"})
    else:
        lista = tarefas(setups, passo=a.passo, so_ativos=set(a.ativos.split(",")) if a.ativos else None)
    workers = min(a.workers, 4) if a.smoke else a.workers
    print(f"{len(lista)} unidades, {workers} workers", flush=True)
    t0 = time.time()
    feitas = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_roda, t): t for t in lista}
        for f in as_completed(futs):
            try:
                res, texto = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[FALHOU {futs[f][:2]}] {type(e).__name__}: {e}", flush=True)
                continue
            feitas += 1
            print(texto, end="", flush=True)
            print(f"   ({feitas}/{len(lista)}, {time.time() - t0:.0f}s decorridos)", flush=True)
    print(f"fim: {feitas}/{len(lista)} unidades em {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    principal()
