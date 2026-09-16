# -*- coding: utf-8 -*-
"""WIN@ retangulo (D1/centro) -- qual CRITERIO de forma carrega peso, e da'
para recuperar a lacuna de frequencia (403 op. do detector x 373 do placebo,
medida em `copawin_retangulo_fechar_abertos_2026_09_15.py`) afrouxando UM
criterio de cada vez, em vez de tirar todos (o placebo) ou nenhum (o
candidato congelado)?

## Contexto -- o que ja esta' fechado e nao e' remedido aqui

O detector (`copawin_retangulo_lateral_2026_09_15.py`, funcao `_avalia_janela`)
exige, TODOS obrigatorios: >=2 toques por borda, >=2 VISITAS por borda
(barras seguidas colapsam), >=2 trocas de lado, >=3 cruzamentos do meio,
contencao >=95%, contracao <=55% da amplitude anterior, deriva <=25% da
largura, espalhamento dos toques >= W/3 barras, largura >= 328 pontos (terco
superior no IS), tolerancia de borda 8% da largura.

O CONTROLE (placebo = banda q90/q10 crua, SEM nenhum destes testes de forma,
so' o piso de largura) ja mostrou: IS -2.315,60 mas OOS +1.306,70 com 373
operacoes -- MAIS dinheiro em R$ que o detector completo (IS 2.834,10, OOS
737,70, 403+101=504 operacoes no total). Por OPERACAO o detector paga muito
melhor (35,16 vs -12,29 pts/op no IS), mas isso e' exatamente o intervalo
entre "0 criterios" (placebo) e "todos os criterios" (candidato) que nunca
foi mapeado -- este script mapeia.

## O que este script faz (SO' NO IS -- OOS e' caro, ver CLAUDE.md)

FASE 1: ladder de sensibilidade. Baseline = todos os criterios no valor
congelado (reproduz o candidato). Para cada criterio, RELAXA SO' ELE para um
valor permissivo (essencialmente desligado) e mede o efeito isolado. Tambem
varia a TOLERANCIA de borda (o parametro que define a zona de toque) e o
PISO DE LARGURA (328 -> valores menores), que e' a sugestao explicita do
dono no briefing.

FASE 2: com o que a FASE 1 mostrar carregar MENOS peso (maior ganho de
frequencia por menor perda de qualidade), testa COMBINACOES dos 2-3
relaxamentos mais promissores, sozinhos e cruzados com um piso de largura
mais baixo.

Motor, custo e execucao: os MESMOS do candidato congelado --
`target_fills_as_maker=True`, `anchor_exits_at_fill=True`, entrada por
`EnterLimit` com `ttl_bars=10`, alvo/stop como ordem-limite/mercado do
`RetanguloLab` ja existente (D1 puro, sem mudar geometria alvo/stop: alvo
0,80xL do centro, stop 0,50xL). SO' o detector varia.

Capital: R$650 (piso medido: MaxDD R$525,60 IS + margem R$100 -- ordem do
dono, "sempre o minimo real", nunca o R$3.000 usado nos scripts anteriores
desta linha). WIN@ nao tem fila calibrada -- `queue_ahead_qty=0`,
`exit_queue_ahead_qty=0`, preenchimento no TOQUE, igual a toda a linha do
retangulo ate aqui (premissa OTIMISTA, declarada).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_criterios_2026_09_15.py`
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


_estr = _carrega("copawin_retangulo_estrategias_2026_09_15.py", "estr_crit")
_det = _estr._det
_base = _estr._base
SYMBOL = _estr.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()

CAPITAL = 650.0  # piso medido (MaxDD R$525,60 IS + margem R$100) -- nunca R$3.000
LARGURA_328 = 328.0

# geometria congelada (D1), NAO mexida aqui -- so' o detector varia
GEO_BASE = dict(modo="centro", alvo_frac=1.6, stop_frac=0.5, max_barras_apos=None,
                uma_por_retangulo=False, barras_extra_apos_morte=0, W=20)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _avalia_flex(high, low, close, range_antes, *, tol, toques_min, visitas_min,
                  trocas_min, cruzamentos_min, contencao_min, contracao_max,
                  deriva_max, espalhamento_min):
    """Copia parametrizada de `_det._avalia_janela` -- MESMA logica, cada
    limiar vira argumento em vez de constante de modulo, para poder desligar
    UM de cada vez (valor permissivo = 0 ou infinito conforme o sentido do
    teste)."""
    topo = float(np.quantile(high, 0.90))
    piso = float(np.quantile(low, 0.10))
    L = topo - piso
    if L <= 0:
        return None
    meio = (topo + piso) / 2.0
    zona = tol * L

    lados, pos_topo, pos_piso = [], [], []
    for i, (h, lo) in enumerate(zip(high, low)):
        if h >= topo - zona:
            lados.append(1)
            pos_topo.append(i)
        elif lo <= piso + zona:
            lados.append(-1)
            pos_piso.append(i)
    n_topo, n_piso = len(pos_topo), len(pos_piso)
    if n_topo < toques_min or n_piso < toques_min:
        return None

    def _visitas(pos):
        return 1 + sum(1 for a, b in zip(pos, pos[1:]) if b - a > 1)

    v_topo, v_piso = _visitas(pos_topo), _visitas(pos_piso)
    if v_topo < visitas_min or v_piso < visitas_min:
        return None
    minimo = espalhamento_min * len(close)
    if pos_topo and pos_piso:
        if (pos_topo[-1] - pos_topo[0]) < minimo or (pos_piso[-1] - pos_piso[0]) < minimo:
            return None

    trocas = sum(1 for a, b in zip(lados, lados[1:]) if a != b)
    if trocas < trocas_min:
        return None

    acima = close > meio
    cruz = int(np.sum(acima[1:] != acima[:-1]))
    if cruz < cruzamentos_min:
        return None

    contencao = float(np.mean((close >= piso) & (close <= topo)))
    if contencao < contencao_min:
        return None

    n = len(close)
    t1 = float(np.mean(close[: n // 3]))
    t3 = float(np.mean(close[-(n // 3):]))
    if abs(t3 - t1) > deriva_max * L:
        return None

    contraiu = float("nan")
    if range_antes is not None and range_antes > 0:
        contraiu = L / range_antes
        if contraiu > contracao_max:
            return None

    return dict(topo=topo, piso=piso, largura=L, meio=meio, contracao=contraiu,
                visitas_topo=v_topo, visitas_piso=v_piso,
                toques_topo=n_topo, toques_piso=n_piso, trocas=trocas,
                cruzamentos=cruz, contencao=contencao,
                deriva_frac=abs(t3 - t1) / L)


@dataclass
class RetanguloFlex(_estr.RetanguloLab):
    """RetanguloLab com o detector PARAMETRIZADO -- cada limiar de forma vira
    campo, default = valor congelado (reproduz o candidato exatamente)."""

    name: str = "retangulo_flex"
    tol: float = _det.TOL
    toques_min: int = _det.TOQUES_MIN
    visitas_min: int = _det.VISITAS_MIN
    trocas_min: int = 2  # hardcoded no detector original
    cruzamentos_min: int = _det.CRUZAMENTOS_MIN
    contencao_min: float = _det.CONTENCAO_MIN
    contracao_max: float = _det.CONTRACAO_MAX
    deriva_max: float = _det.DERIVA_MAX
    espalhamento_min: float = _det.ESPALHAMENTO_MIN

    def _tenta_detectar(self):
        if len(self._hist) < 3 * self.W:
            return
        hi, lo, cl = self._arrays(self.W)
        hi2, lo2, _ = self._arrays(3 * self.W)
        range_antes = float(hi2[:2 * self.W].max() - lo2[:2 * self.W].min())
        ret = _avalia_flex(
            hi, lo, cl, range_antes, tol=self.tol, toques_min=self.toques_min,
            visitas_min=self.visitas_min, trocas_min=self.trocas_min,
            cruzamentos_min=self.cruzamentos_min, contencao_min=self.contencao_min,
            contracao_max=self.contracao_max, deriva_max=self.deriva_max,
            espalhamento_min=self.espalhamento_min)
        if ret is None or ret["largura"] < _det.LARGURA_MIN_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_min_pontos:
            return
        self._ret = ret
        self._barras_desde_conf = 0
        self._fora_seguidas = 0
        self._ja_operou = False
        self._morto_ha = 0


# ---------------------------------------------------------------------------

def _roda(dias, kw):
    from backtest.intraday.engine import run_intraday_backtest

    strat = RetanguloFlex(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg, _corte = _base._cfg_com_folga(_estr.FOLGA_PRODUCAO, CAPITAL, strat)
    return run_intraday_backtest(bars, strat, cfg)


def _maxdd(serie: pd.Series) -> float:
    if len(serie) == 0:
        return float("nan")
    eq = serie.cumsum()
    return float((eq.cummax() - eq).max())


def _unidade(args):
    fase, rot, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, kw)
    c = _base.consistencia(list(res.trades), dias)
    c["maxdd"] = _maxdd(c["serie"])
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c.pop("serie", None)
    print(f"  [{fase}] {rot:<42} liquido={br(c['liquido']).rjust(11)}  trades={c['n']:>5}  "
          f"win={br(100*c['win'],1) if c['n'] else '--':>5}%  be={br(100*c['be'],1) if c['be']==c['be'] else '--':>5}%  "
          f"pts/op={br(c['pts'],1) if c['pts']==c['pts'] else '--':>7}  sem_tr={c['sem_trade']:>3}/{c['pregoes']}",
          flush=True)
    return dict(fase=fase, rotulo=rot, c=c)


def _pc(x):
    return (br(100 * x, 1) + "%") if x == x else "--"


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]
    print("=" * 130)
    print("WIN@ retangulo D1 -- SENSIBILIDADE AOS CRITERIOS DE FORMA (SO' NO IS -- OOS fica intocado)")
    print("=" * 130)
    print(f"  IS: {len(IS)} pregoes ({IS[0]} a {IS[-1]}) | capital R$ {br(CAPITAL,0)} (piso real, nao R$3.000)")
    print("  geometria congelada (D1): alvo 0,80xL do centro, stop 0,50xL, re-arma enquanto vive, 1 contrato")
    print("  WIN@ sem fila calibrada: queue_ahead_qty=0 nas duas pontas (preenchimento no TOQUE)\n", flush=True)

    # ---------------- FASE 1: ladder de sensibilidade -----------------------
    tarefas = []
    tarefas.append(("1", "baseline (candidato, todos os criterios)",
                    IS, dict(GEO_BASE, largura_min_pontos=LARGURA_328)))
    relaxamentos = {
        "sem toques_min (2->0)": dict(toques_min=0),
        "sem visitas_min (2->0)": dict(visitas_min=0),
        "sem trocas_min (2->0)": dict(trocas_min=0),
        "sem cruzamentos_min (3->0)": dict(cruzamentos_min=0),
        "sem contencao_min (95%->0%)": dict(contencao_min=0.0),
        "sem contracao_max (55%->inf)": dict(contracao_max=float("inf")),
        "sem deriva_max (25%->inf)": dict(deriva_max=float("inf")),
        "sem espalhamento_min (W/3->0)": dict(espalhamento_min=0.0),
        "tol 8%->15%": dict(tol=0.15),
        "tol 8%->20%": dict(tol=0.20),
    }
    for rot, over in relaxamentos.items():
        tarefas.append(("1", rot, IS, dict(GEO_BASE, largura_min_pontos=LARGURA_328, **over)))

    pisos_largura = (150.0, 200.0, 250.0, 275.0, 300.0, 328.0)
    for L in pisos_largura:
        tarefas.append(("1w", f"piso largura {br(L,0)} pts (todos criterios)",
                        IS, dict(GEO_BASE, largura_min_pontos=L)))

    tarefas.append(("1", "PLACEBO (banda crua, referencia)", IS,
                    dict(GEO_BASE, largura_min_pontos=LARGURA_328,
                         toques_min=0, visitas_min=0, trocas_min=0, cruzamentos_min=0,
                         contencao_min=0.0, contracao_max=float("inf"),
                         deriva_max=float("inf"), espalhamento_min=0.0)))

    print(f"FASE 1: {len(tarefas)} rodadas (ladder + piso de largura)...\n", flush=True)
    fase1: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            fase1[(r["fase"], r["rotulo"])] = r["c"]

    base_c = fase1[("1", "baseline (candidato, todos os criterios)")]
    print("\n" + "=" * 130)
    print("FASE 1 -- TABELA (IS), ordenada por GANHO DE TRADES sobre o baseline")
    print("=" * 130)
    hdr = (f"  {'variante':<42}{'liquido':>11}{'trades':>8}{'d_trades':>10}{'win%':>7}"
           f"{'be%':>7}{'pts/op':>9}{'MaxDD':>10}{'sem_tr':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    linhas_singles = [(rot, fase1[("1", rot)]) for rot in
                       ["baseline (candidato, todos os criterios)"] + list(relaxamentos.keys())
                       + ["PLACEBO (banda crua, referencia)"]]
    linhas_singles_ordenadas = sorted(
        linhas_singles[1:-1], key=lambda kv: kv[1]["n"] - base_c["n"], reverse=True)
    for rot, c in [linhas_singles[0]] + linhas_singles_ordenadas + [linhas_singles[-1]]:
        print(f"  {rot:<42}{br(c['liquido']):>11}{c['n']:>8}{c['n']-base_c['n']:>+10}"
              f"{_pc(c['win']):>7}{_pc(c['be']):>7}{br(c['pts'],1):>9}{br(c['maxdd']):>10}"
              f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    print("\n  --- piso de largura (todos os criterios ligados) ---")
    hdr2 = (f"  {'piso (pts)':<14}{'liquido':>11}{'trades':>8}{'win%':>7}{'be%':>7}"
            f"{'pts/op':>9}{'MaxDD':>10}{'sem_tr':>9}")
    print(hdr2)
    for L in pisos_largura:
        c = fase1[("1w", f"piso largura {br(L,0)} pts (todos criterios)")]
        print(f"  {br(L,0):<14}{br(c['liquido']):>11}{c['n']:>8}{_pc(c['win']):>7}{_pc(c['be']):>7}"
              f"{br(c['pts'],1):>9}{br(c['maxdd']):>10}{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    # escolhe os 3 relaxamentos com maior ganho de trades E win% acima do
    # breakeven empirico (edge preservado, nao so' volume)
    candidatos_fase2 = [
        (rot, c) for rot, c in linhas_singles_ordenadas
        if c["n"] > base_c["n"] and c["be"] == c["be"] and c["win"] > c["be"]
    ]
    top3 = candidatos_fase2[:3]

    print("\n" + "=" * 130)
    print("FASE 2 -- combinacoes dos relaxamentos mais promissores (mais trades, win% > breakeven)")
    print("=" * 130)
    if not top3:
        print("  Nenhum relaxamento isolado aumentou trades mantendo win% acima do breakeven empirico.")
        print("  FASE 2 pulada -- nao ha' insumo que valha combinar.")
        print("\nFIM.")
        return

    print(f"  entrando na FASE 2: {[r for r, _ in top3]}\n", flush=True)
    mapa_over = dict(relaxamentos)
    tarefas2 = []
    # cada um sozinho ja' esta' na fase 1; aqui so' os PARES e o TRIO, e cada
    # um cruzado com o melhor piso de largura reduzido encontrado na fase 1w
    melhor_piso = min(pisos_largura, key=lambda L: 0)  # placeholder, substituido abaixo
    # piso mais baixo testado que ainda produziu win% > be (senao usa 328)
    pisos_ok = [L for L in pisos_largura
                if fase1[("1w", f"piso largura {br(L,0)} pts (todos criterios)")]["be"] ==
                fase1[("1w", f"piso largura {br(L,0)} pts (todos criterios)")]["be"]
                and fase1[("1w", f"piso largura {br(L,0)} pts (todos criterios)")]["win"] >
                fase1[("1w", f"piso largura {br(L,0)} pts (todos criterios)")]["be"]]
    melhor_piso = min(pisos_ok) if pisos_ok else LARGURA_328

    from itertools import combinations
    for k in (2, 3):
        for combo in combinations(top3, k):
            rot = " + ".join(r for r, _ in combo)
            over = {}
            for _, c_over in [(r, mapa_over[r]) for r, _ in combo]:
                over.update(c_over)
            tarefas2.append(("2", rot, IS, dict(GEO_BASE, largura_min_pontos=LARGURA_328, **over)))
            tarefas2.append(("2", rot + f" + piso {br(melhor_piso,0)}", IS,
                             dict(GEO_BASE, largura_min_pontos=melhor_piso, **over)))

    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas2]
        fase2 = {}
        for fut in as_completed(futs):
            r = fut.result()
            fase2[r["rotulo"]] = r["c"]

    print("\n" + "=" * 130)
    print("FASE 2 -- TABELA (IS)")
    print("=" * 130)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    print(f"  {'baseline (candidato)':<42}{br(base_c['liquido']):>11}{base_c['n']:>8}{0:>+10}"
          f"{_pc(base_c['win']):>7}{_pc(base_c['be']):>7}{br(base_c['pts'],1):>9}"
          f"{br(base_c['maxdd']):>10}{str(base_c['sem_trade'])+'/'+str(base_c['pregoes']):>9}")
    for rot, _ in [t[:2] for t in tarefas2]:
        pass
    vistos = set()
    for _, rot, _, _ in tarefas2:
        if rot in vistos:
            continue
        vistos.add(rot)
        c = fase2[rot]
        print(f"  {rot:<42}{br(c['liquido']):>11}{c['n']:>8}{c['n']-base_c['n']:>+10}"
              f"{_pc(c['win']):>7}{_pc(c['be']):>7}{br(c['pts'],1):>9}{br(c['maxdd']):>10}"
              f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
