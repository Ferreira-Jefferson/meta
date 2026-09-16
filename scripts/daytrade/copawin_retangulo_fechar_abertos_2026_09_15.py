# -*- coding: utf-8 -*-
"""WIN@ retangulo -- FECHA OS TRES PONTOS QUE FICARAM ABERTOS apos a passada OOS.

Pedido do dono (2026-09-15): "faca os testes para fechar o que esta em aberto".

A passada congelada (`copawin_retangulo_oos_congelado_2026_09_15.py`) mostrou
4/4 variantes replicando o sinal no OOS, com a versao SEM filtro de volume
mantendo 35,16 -> 36,52 pts/op. Tres coisas ficaram sem resposta, e cada uma
delas e' capaz de derrubar o resultado sozinha:

  (A) CONTROLE SEM DETECTOR NO OOS. No IS o controle dava -2.949,40, o que
      fazia o detector parecer load-bearing. Ninguem rodou o controle no OOS.
      Se o placebo tambem ganhar la', o que paga nao e' o retangulo -- e' a
      geometria alvo/stop aplicada a qualquer banda.

  (B) A GEOMETRIA FOI ESCOLHIDA OLHANDO AS DUAS JANELAS. alvo 0,80xL e stop
      0,50xL sairam da matriz de trajetoria, que rodou em IS E OOS. Isso e'
      contaminacao: o OOS ja tinha opinado sobre a geometria antes de ser
      usado para confirma-la. A correcao possivel agora nao e' apagar o que
      foi visto -- e' medir SE ISSO IMPORTA, de duas formas:
        1. re-derivar o otimo usando SO' o IS. Se o IS sozinho aponta para o
           mesmo canto da grade, a contaminacao nao mudou a escolha.
        2. olhar o FORMATO da superficie. Um plato largo significa que
           qualquer celula vizinha serviria e a escolha exata nao carrega
           peso; um pico isolado significa que a celula foi garimpada.

  (C) WIN@ NAO TEM FILA CALIBRADA. `fidelidade.py` so' tem WDO@, entao tudo
      rodou com `queue_ahead_qty=0` nas duas pontas: **toda limite preenche no
      TOQUE**. Essa e' a premissa que ja inverteu o sinal do WDO F1 maker
      (+R$3,82/op previsto contra -R$3,00 realizado). Nao da' para calibrar
      WIN@ sem operacao real, mas da' para responder a pergunta que decide:
      **ate' quanta fila o desenho sobrevive?** Se ele morre com pouca fila,
      o numero da passada OOS nao descreve futuro nenhum.

      A referencia transplantada (declarada como transplante, NAO como
      calibracao): no WDO@ a fila medida e' 438 na entrada e 489 na saida,
      contra volume mediano de 2.928 contratos por barra M1 -- 15,0% e 16,7%
      de uma barra. O WIN@ negocia 24.956 contratos medianos por barra M1;
      a MESMA FRACAO daria ~3.733 / ~4.167. E' chute com metodo, e entra na
      varredura como uma linha entre outras.

## O desenho sob teste (congelado, os numeros vem do IS)

    W=20 | modo centro | alvo 0,80xL | stop 0,50xL | re-arma enquanto vive |
    largura minima 328 pts | SEM filtro de volume (refutado no OOS)
    1 contrato | capital R$ 3.000 | custo ida-e-volta 7,5 pontos

## O placebo de (A), e por que ele e' o controle CERTO

Mesmo motor, mesma geometria, mesmo piso de largura, mesma politica de
re-armar, mesmo criterio de morte. A UNICA coisa removida sao os testes de
FORMA do detector: visitas em cada borda, cruzamentos da linha do meio,
contencao, contracao contra as 2W barras anteriores, deriva e espalhamento.
A banda vira o q90/q10 cru das ultimas W barras -- ou seja, "uma faixa larga
qualquer", que e' exatamente a hipotese nula do dono: *o que paga e' o
RETANGULO, ou so' a largura?*

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_fechar_abertos_2026_09_15.py`
"""
from __future__ import annotations

import dataclasses
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

_spec = importlib.util.spec_from_file_location(
    "estr_fecha", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_fecha"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
_det = _estr._det
CAPITAL = _estr.CAPITAL
SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()

LARGURA_IS_Q67 = 328.0
GEO = dict(modo="centro", alvo_frac=1.6, stop_frac=0.5, max_barras_apos=None,
           uma_por_retangulo=False, barras_extra_apos_morte=0,
           largura_min_pontos=LARGURA_IS_Q67)

# (C) -- a varredura de fila. Q_ent = Q_sai em cada linha, exceto a do
# transplante do WDO@, que respeita a assimetria medida la' (438/489).
FILAS = [
    ("0 (toque) — o que a passada OOS usou", 0.0, 0.0),
    ("250", 250.0, 250.0),
    ("500", 500.0, 500.0),
    ("1.000", 1000.0, 1000.0),
    ("2.000", 2000.0, 2000.0),
    ("3.733 / 4.167 (transplante WDO@)", 3733.0, 4167.0),
    ("6.000", 6000.0, 6000.0),
    ("10.000", 10000.0, 10000.0),
    ("15.000", 15000.0, 15000.0),
    ("25.000 (~1 barra mediana)", 25000.0, 25000.0),
]

ALVOS = (0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0)
STOPS = (0.25, 0.375, 0.50, 0.625, 0.75, 1.00)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class PlaceboBanda(_estr.RetanguloLab):
    """Controle: banda q90/q10 CRUA, sem nenhum teste de forma do retangulo."""

    name: str = "placebo_banda"

    def _tenta_detectar(self):
        if len(self._hist) < 3 * self.W:
            return
        hi, lo, cl = self._arrays(self.W)
        topo = float(np.quantile(hi, 0.90))
        piso = float(np.quantile(lo, 0.10))
        L = topo - piso
        if L < _det.LARGURA_MIN_TICKS * self.tick_size or L < self.largura_min_pontos:
            return
        self._ret = dict(topo=topo, piso=piso, largura=L, meio=(topo + piso) / 2.0,
                         visitas=0, toques=0, cruzamentos=0, contencao=1.0,
                         deriva_frac=0.0, contracao=1.0)
        self._barras_desde_conf = 0
        self._fora_seguidas = 0
        self._ja_operou = False
        self._morto_ha = 0


def _cfg(strat, q_ent, q_sai):
    from backtest.intraday.profiles import _recua, config_for, profile_for

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=q_ent, exit_queue_ahead_qty=q_sai,
    )
    return dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, 5))


def _maxdd(serie: pd.Series) -> float:
    if len(serie) == 0:
        return float("nan")
    eq = serie.cumsum()
    return float((eq.cummax() - eq).max())


def _unidade(args):
    """(bloco, janela, rotulo, dias, classe, kw, q_ent, q_sai) -> metricas."""
    from backtest.intraday.engine import run_intraday_backtest

    bloco, janela, rotulo, dias, classe, kw, q_ent, q_sai = args
    cls = PlaceboBanda if classe == "placebo" else _estr.RetanguloLab
    strat = cls(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, _cfg(strat, q_ent, q_sai))
    c = _base.consistencia(list(res.trades), dias)
    c["maxdd"] = _maxdd(c["serie"])
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c["lucro_dd"] = (c["liquido"] / c["maxdd"]) if c["maxdd"] and c["maxdd"] > 0 else float("nan")
    c.pop("serie", None)
    return dict(bloco=bloco, janela=janela, rotulo=rotulo, c=c)


def _pc(x):
    return (br(100 * x, 1) + "%") if x == x else "--"


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]
    OOS = [d for d in dias_todos if d >= CORTE_OOS]
    JAN = {"IS": IS, "OOS": OOS}

    print("=" * 126)
    print("WIN@ retangulo -- FECHANDO OS TRES PONTOS ABERTOS")
    print("=" * 126)
    print(f"  IS {len(IS)} pregoes ({IS[0]} a {IS[-1]}) | OOS {len(OOS)} pregoes "
          f"({OOS[0]} a {OOS[-1]})")
    print(f"  desenho: W=20 centro, alvo 0,80xL, stop 0,50xL, largura >= {br(LARGURA_IS_Q67,0)} pts,")
    print(f"           re-arma enquanto vive, 1 contrato, capital R$ {br(CAPITAL,0)}")
    print("  (A) controle sem detector no OOS  (B) geometria re-derivada so' no IS  "
          "(C) sensibilidade a fila\n", flush=True)

    tarefas = []
    # (A) controle
    for jn, dd in JAN.items():
        tarefas.append(("A", jn, "candidato (detector completo)", dd, "real",
                        dict(GEO, W=20), 0.0, 0.0))
        tarefas.append(("A", jn, "PLACEBO (banda q90/q10 crua)", dd, "placebo",
                        dict(GEO, W=20), 0.0, 0.0))
    # (B) geometria
    for jn, dd in JAN.items():
        for a in ALVOS:
            for s in STOPS:
                tarefas.append(("B", jn, f"{a:.2f}|{s:.3f}", dd, "real",
                                dict(GEO, W=20, alvo_frac=a, stop_frac=s), 0.0, 0.0))
    # (C) fila
    for jn, dd in JAN.items():
        for rot, qe, qs in FILAS:
            tarefas.append(("C", jn, rot, dd, "real", dict(GEO, W=20), qe, qs))

    print(f"{len(tarefas)} rodadas de motor...\n", flush=True)
    out = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["bloco"], r["janela"], r["rotulo"])] = r["c"]
            feitos += 1
            if feitos % 20 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    # ---------------------------------------------------------------- (A)
    print("\n" + "=" * 126)
    print("(A) O DETECTOR E' LOAD-BEARING? -- candidato contra o placebo de banda crua")
    print("=" * 126)
    hdr = (f"  {'janela':<6}{'variante':<32}{'liquido':>11}{'trades':>8}{'win%':>7}"
           f"{'BEemp%':>9}{'veredito':>12}{'pts/op':>9}{'MaxDD':>10}{'luc/DD':>9}"
           f"{'preg+':>7}{'sem_tr':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for jn in JAN:
        for rot in ("candidato (detector completo)", "PLACEBO (banda q90/q10 crua)"):
            c = out[("A", jn, rot)]
            print(f"  {jn:<6}{rot:<32}{br(c['liquido']):>11}{c['n']:>8}{_pc(c['win']):>7}"
                  f"{_pc(c['be']):>9}{c['veredito']:>12}{br(c['pts'],2):>9}"
                  f"{br(c['maxdd']):>10}{br(c['lucro_dd'],2):>9}{_pc(c['frac_preg']):>7}"
                  f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")
        print()

    # ---------------------------------------------------------------- (B)
    print("=" * 126)
    print("(B) GEOMETRIA -- superficie alvo x stop, o IS DECIDE e o OOS so' mostra o formato")
    print("=" * 126)
    for jn in JAN:
        for metrica, rot_m in (("pts", "pontos liquidos por operacao"),
                               ("liquido", "liquido R$")):
            print(f"\n  --- {jn}: {rot_m} ---")
            print("  " + f"{'alvo\\stop':<11}" + "".join(f"{s:>10.3f}" for s in STOPS))
            for a in ALVOS:
                linha = f"  {a:<11.2f}"
                for s in STOPS:
                    c = out[("B", jn, f"{a:.2f}|{s:.3f}")]
                    v = c[metrica]
                    linha += f"{br(v, 1 if metrica=='pts' else 0):>10}"
                print(linha)

    print("\n  --- onde cada janela coloca o otimo, e quanto vale o congelado ---")
    for jn in JAN:
        cells = [(a, s, out[("B", jn, f"{a:.2f}|{s:.3f}")]) for a in ALVOS for s in STOPS]
        pos = [c for c in cells if c[2]["liquido"] > 0]
        melhor_l = max(cells, key=lambda c: c[2]["liquido"])
        melhor_p = max(cells, key=lambda c: c[2]["pts"] if c[2]["pts"] == c[2]["pts"] else -1e9)
        cong = out[("B", jn, "1.60|0.500")]
        rank = 1 + sum(1 for c in cells if c[2]["liquido"] > cong["liquido"])
        print(f"  {jn}: {len(pos)}/{len(cells)} celulas com liquido > 0 | "
              f"melhor liquido alvo {br(melhor_l[0],2)} stop {br(melhor_l[1],3)} "
              f"({br(melhor_l[2]['liquido'])}) | melhor pts/op alvo {br(melhor_p[0],2)} "
              f"stop {br(melhor_p[1],3)} ({br(melhor_p[2]['pts'],1)})")
        print(f"        congelado (1,60 | 0,500): liquido {br(cong['liquido'])}, "
              f"posto {rank} de {len(cells)}, pts/op {br(cong['pts'],1)}")

    print("\n  --- as celulas POSITIVAS NAS DUAS janelas (o que sobra sem garimpo) ---")
    ambas = [(a, s) for a in ALVOS for s in STOPS
             if out[("B", "IS", f"{a:.2f}|{s:.3f}")]["liquido"] > 0
             and out[("B", "OOS", f"{a:.2f}|{s:.3f}")]["liquido"] > 0]
    print(f"  {len(ambas)} de {len(ALVOS)*len(STOPS)}:")
    for a, s in ambas:
        ci, co = out[("B", "IS", f"{a:.2f}|{s:.3f}")], out[("B", "OOS", f"{a:.2f}|{s:.3f}")]
        marca = "  <== congelado" if (a, s) == (1.6, 0.50) else ""
        print(f"    alvo {br(a,2)} stop {br(s,3)}: IS {br(ci['liquido']):>10} "
              f"({ci['n']:>4} trd, {br(ci['pts'],1):>6} pts/op) | "
              f"OOS {br(co['liquido']):>9} ({co['n']:>4} trd, {br(co['pts'],1):>6} pts/op){marca}")

    # ---------------------------------------------------------------- (C)
    print("\n" + "=" * 126)
    print("(C) SENSIBILIDADE A FILA -- quanta fila o desenho aguenta antes de morrer")
    print("=" * 126)
    print("    WIN@ NAO tem fila calibrada em fidelidade.py. Isto e' SENSIBILIDADE,")
    print("    nao calibracao: a unica forma de fechar de verdade e' operar e medir.")
    hdr = (f"  {'fila (contratos na frente)':<36}{'liq IS':>11}{'trd IS':>8}{'win IS':>8}"
           f"{'pts IS':>8}{'liq OOS':>11}{'trd OOS':>9}{'win OOS':>9}{'pts OOS':>9}"
           f"{'sem_tr OOS':>12}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for rot, _qe, _qs in FILAS:
        a, b = out[("C", "IS", rot)], out[("C", "OOS", rot)]
        print(f"  {rot:<36}{br(a['liquido']):>11}{a['n']:>8}{_pc(a['win']):>8}"
              f"{br(a['pts'],1):>8}{br(b['liquido']):>11}{b['n']:>9}{_pc(b['win']):>9}"
              f"{br(b['pts'],1):>9}"
              f"{str(b['sem_trade'])+'/'+str(b['pregoes']):>12}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
