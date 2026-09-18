# -*- coding: utf-8 -*-
"""WDO@: `wdo_retangulo` NATIVO -- calibracao do piso empirico de largura (IS)
e passada IS/OOS nas janelas oficiais congeladas do WDO, com o desenho de
execucao FECHADO e a fila REAL de `fidelidade.py`.

## O que este script faz

1. **Calibra** o piso EMPIRICO de largura (`largura_minima_pontos`) nos
   TERCIS da distribuicao de largura medida no WDO IS -- mesmo METODO do
   `win_retangulo` (que usou o terco superior da largura do W=20 medido NO
   IS do WIN, 328,0 pontos), numero PROPRIO do WDO (nao emprestado). O piso
   ESTRUTURAL (`wdo_retangulo.LARGURA_MINIMA_TICKS = 4,4 ticks`) ja' vem
   recalibrado dentro da propria classe -- ver a docstring dela para a
   formula (mesma do WIN, numeros do WDO).
2. **Roda IS e OOS** nas janelas OFICIAIS congeladas do WDO (as mesmas de
   `wdof1_deslize_alvo_is_oos_2026_09_08.py`/`ondas_wolfe_wdo_m1_is_
   completo_2026_09_11.py`: IS 2026-02-27..2026-06-12, 72 pregoes; OOS
   2026-06-15..2026-08-25, 51 pregoes), capital REAL R$375,00 (piso de
   PARTIDA do WDO@ com reserva -- nunca um capital de folga), fila REAL de
   `backtest.intraday.fidelidade` (329/494, Kaplan-Meier) e o desenho de
   execucao FECHADO (`EnterLimit`, alvo fatiado sem prazo, so' o stop a
   mercado) -- tudo via `config_for`, nenhum numero de fila digitado a mao.

## Base de dados: M1, nao tick

Medido em barra M1 canonica (`market_data_intraday.storage.load_m1("WDO@")`,
auditada e reparada em 2026-09-16 -- ver o commit
`data(intraday): audita a base M1 e repara 3 pregoes truncados`), e' o MESMO
desvio deliberado que `ondas_wolfe_wdo_m1_is_completo_2026_09_11.py` ja
declarou: o motor tick-a-tick processa ~1.800 ticks/s nesta maquina e o IS
congelado tem ~12M ticks -- mais de 1,5h de motor por variante. Em M1 o
mesmo IS tem ~41 mil barras.

**O CUSTO desta escolha, declarado, nao escondido:** `fidelidade.py` foi
calibrado TICK a TICK ("quanto volume negociou no nosso nivel ENTRE a ordem
entrar no livro e preencher/cancelar"). Aplicar o MESMO numero contra o
volume agregado de 1 minuto inteiro (`limit_fill_capped_by_volume`) e'
OTIMISTA -- a barra M1 contem o volume do minuto TODO, nao so' o que
aconteceu ate' o toque, entao a fila "e' vencida" mais facil do que na
realidade tick a tick. CONSEQUENCIA: um resultado POSITIVO aqui NAO e'
validacao final -- e' o teste RAPIDO que decide se vale a hora e meia de
motor tick-a-tick para confirmar. Um resultado NEGATIVO/CENSURADO aqui e'
informativo por si -- rodar em tick so' pode fazer a fidelidade PIORAR
(mais fila, menos fill), nunca melhorar o veredito.

## As 4 linhas de cada tabela

  1. CANDIDATO W20 (piso tercil)  -- W=20 (ponto de partida mais validado da
     linha WIN), filtro empirico de largura = terco superior medido no IS
     deste proprio W. E' a UNICA linha que conta como teste.
  2. W20 sem piso empirico        -- so' o piso ESTRUTURAL (4,4 ticks) filtra.
     Mede quanto o filtro empirico carrega.
  3. W30 (ref, piso tercil)       -- a janela do congelado ORIGINAL do WIN
     (antes de virar W20 em producao), com o piso tercil do PROPRIO W30.
  4. W20 SEM FILA (so' contexto)  -- reproduz o motor ATE 2026-09-08
     (`queue_ahead_qty=0`, `exit_queue_ahead_qty=0`), a mesma geometria da
     linha 1. NAO e' candidato: existe so' para mostrar o TAMANHO do que a
     fila real custa -- e' exatamente o eixo que apagou o edge do WDO F1
     maker e quase apagou o do `wdo_orb`.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/wdo_retangulo_calibracao_is_oos_2026_09_16.py`
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 500  # WDO@ tem ~570 barras/pregao (09:00-18:30 BRT)

# Janelas OFICIAIS congeladas do WDO (mesmas de wdof1_deslize_alvo_is_oos_
# 2026_09_08.py / ondas_wolfe_wdo_m1_is_completo_2026_09_11.py). Split
# INTACTO -- nao se mexe.
IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")   # exclusivo
OOS_INICIO = pd.Timestamp("2026-06-15", tz="UTC")
OOS_FIM = pd.Timestamp("2026-08-26", tz="UTC")  # exclusivo (25/08 incluso)

#: janelas de deteccao testadas -- W20 (ponto de partida mais validado na
#: linha WIN) e W30 (a janela do congelado ORIGINAL, antes de virar W20).
JANELAS_W = (20, 30)


def br(v, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int) -> tuple[float, float]:
    """Wilson score -- mesma formula usada em toda tabela de consistencia
    deste repo (ex.: `copawin_encerrar_mais_cedo_2026_09_14.ic95`)."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def consistencia(trades, dias_da_janela) -> dict:
    """Trades e pregoes-sem-trade ANTES do liquido (item 6.15 de
    `LICOES_DE_PRODUCAO.md`: janela onde o robo parou e' censurada), win%
    contra o breakeven EMPIRICO (nao so' o nominal), IC95 Wilson e veredito
    -- mesmo metodo de `copawin_encerrar_mais_cedo_2026_09_14.consistencia`,
    reduzido ao que esta rodada precisa (sem blocos/meses de constancia,
    fora do escopo desta calibracao)."""
    por_dia: dict = {}
    for t in trades:
        d = pd.Timestamp(t.exit_ts).date()
        por_dia[d] = por_dia.get(d, 0.0) + t.pnl_brl
    dias_com_trade = set(por_dia.keys())
    serie = pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela],
                       index=pd.to_datetime(dias_da_janela))

    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = (abs(sum(p) / len(p))) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if (be == be and n) else "--"

    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0

    return dict(
        liquido=float(serie.sum()), n=n, pregoes=len(dias_da_janela),
        sem_trade=len(dias_da_janela) - len(dias_com_trade),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi,
        veredito=ver, seq_neg=pior, ganho_medio=gm, perda_media=pm,
    )


# ---------------------------------------------------------------------------
# 1) dados: M1 canonico, filtrado por janela + completude
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def _bars_e_dias():
    if "df" not in _CACHE:
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        if df.empty:
            raise SystemExit(
                f"[wdo_retangulo_calibracao] base M1 vazia para {SYMBOL} -- "
                f"rode o fetch antes (ver dev.bat / market_data_intraday)."
            )
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        df = df[[d in completos for d in df.index.date]]
        _CACHE["df"] = df
        _CACHE["completos"] = completos
    return _CACHE["df"], _CACHE["completos"]


def _dias_da_janela(inicio: pd.Timestamp, fim: pd.Timestamp) -> tuple[pd.DataFrame, list]:
    df, completos = _bars_e_dias()
    bars = df[(df.index >= inicio) & (df.index < fim)]
    dias = sorted({d for d in bars.index.date if d in completos})
    bars = bars[[d in set(dias) for d in bars.index.date]]
    return bars, dias


# ---------------------------------------------------------------------------
# 2) calibracao do piso EMPIRICO de largura, nos TERCIS do WDO IS
# ---------------------------------------------------------------------------

def _larguras_do_dia(bars_dia: pd.DataFrame, W: int, detecta_retangulo,
                      margem_morte: float, barras_morte: int, tol: float) -> list[float]:
    """Replica a CADENCIA de deteccao real do robo dentro de um pregao:
    detecta, vive ate' morrer (criterio TOLERANTE), so' volta a varrer depois
    da morte -- exatamente como `WdoRetangulo._tenta_detectar`/`_morreu`
    fariam, mas sem I/O de ordem nenhuma (so' a largura de cada retangulo
    QUALIFICADO interessa aqui). Ignora os pisos de largura (estrutural e
    empirico) de proposito: e' a distribuicao ANTES do filtro que decide
    onde o filtro deve cortar."""
    high = bars_dia["high"].to_numpy(float)
    low = bars_dia["low"].to_numpy(float)
    close = bars_dia["close"].to_numpy(float)
    n = len(close)
    minimo_barras = 3 * W
    if n < minimo_barras:
        return []
    larguras: list[float] = []
    ret: dict | None = None
    fora_seguidas = 0
    t = minimo_barras - 1
    while t < n:
        if ret is None:
            ini = t - W + 1
            ant_ini = t - 3 * W + 1
            amp_ant = (float(high[ant_ini:ini].max() - low[ant_ini:ini].min())
                       if ant_ini >= 0 else None)
            r = detecta_retangulo(high[ini:t + 1], low[ini:t + 1], close[ini:t + 1],
                                  amp_ant, tolerancia=tol)
            if r is not None:
                larguras.append(r["largura"])
                ret = r
                fora_seguidas = 0
            t += 1
        else:
            margem = margem_morte * ret["largura"]
            c = close[t]
            if c > ret["topo"] + margem or c < ret["piso"] - margem:
                fora_seguidas += 1
                if fora_seguidas >= barras_morte:
                    ret = None
                    fora_seguidas = 0
            else:
                fora_seguidas = 0
            t += 1
    return larguras


def calibra_pisos_de_largura(bars_is: pd.DataFrame, dias_is: list) -> dict[int, dict]:
    """Para cada W em `JANELAS_W`: distribuicao de largura (pontos/ticks) no
    WDO IS, tercis (q33/q67) e frequencia -- mesma tabela que o detector do
    WIN imprimiu antes de qualquer estrategia (`copawin_retangulo_lateral_
    2026_09_15.py`, secao 1)."""
    from strategy.daytrade.lab.wdo_retangulo import (
        BARRAS_MORTE, LARGURA_MINIMA_TICKS, MARGEM_MORTE, TOLERANCIA_BORDA,
        detecta_retangulo,
    )
    from core.instruments import economics_for

    tick = economics_for(SYMBOL).price_tick_size
    out: dict[int, dict] = {}
    for W in JANELAS_W:
        todas: list[float] = []
        pregoes_com = 0
        for d in dias_is:
            bd = bars_is[bars_is.index.date == d]
            ls = _larguras_do_dia(bd, W, detecta_retangulo, MARGEM_MORTE,
                                  BARRAS_MORTE, TOLERANCIA_BORDA)
            if ls:
                pregoes_com += 1
            todas.extend(ls)
        arr = np.array(todas, dtype=float)
        q33 = float(np.quantile(arr, 1 / 3)) if len(arr) else float("nan")
        q67 = float(np.quantile(arr, 2 / 3)) if len(arr) else float("nan")
        out[W] = dict(
            n=len(arr), pregoes_com=pregoes_com,
            mediana_pts=float(np.median(arr)) if len(arr) else float("nan"),
            mediana_ticks=float(np.median(arr) / tick) if len(arr) else float("nan"),
            q33_pts=q33, q67_pts=q67, q67_ticks=q67 / tick if q67 == q67 else float("nan"),
            piso_estrutural_ticks=LARGURA_MINIMA_TICKS,
            piso_estrutural_pts=LARGURA_MINIMA_TICKS * tick,
        )
    return out


# ---------------------------------------------------------------------------
# 3) backtest: desenho de execucao FECHADO, fila REAL, capital REAL
# ---------------------------------------------------------------------------

def _roda(dias: list, kwargs_estrategia: dict, sem_fila: bool = False):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_retangulo import WdoRetangulo

    df, _ = _bars_e_dias()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]

    strat = WdoRetangulo(**kwargs_estrategia)
    profile = profile_for(SYMBOL)
    extra = dict(queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
                 target_slippage_ticks=0.0) if sem_fila else {}
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        **extra,
    )
    return run_intraday_backtest(bars, strat, cfg)


def _unidade(args):
    janela_nome, dias, rotulo, kwargs_estrategia, sem_fila = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, kwargs_estrategia, sem_fila=sem_fila)
    c = consistencia(list(res.trades), dias)
    return dict(janela=janela_nome, rotulo=rotulo, res=res, c=c)


def main() -> None:
    print("=" * 130)
    print("WDO@ -- `wdo_retangulo` NATIVO: calibracao do piso de largura (IS) + passada IS/OOS")
    print("=" * 130)

    bars_is, dias_is = _dias_da_janela(IS_INICIO, IS_FIM)
    bars_oos, dias_oos = _dias_da_janela(OOS_INICIO, OOS_FIM)
    print(f"IS  : {len(dias_is)} pregoes ({dias_is[0]} a {dias_is[-1]})")
    print(f"OOS : {len(dias_oos)} pregoes ({dias_oos[0]} a {dias_oos[-1]})")
    if len(dias_is) < 60 or len(dias_oos) < 40:
        print("  AVISO: contagem de pregoes fora do esperado (72 IS / 51 OOS) -- "
              "conferir completude da base M1 antes de seguir.")
    print(f"capital real R$ {br(CAPITAL_REAL_BRL,0)} | fila REAL de fidelidade.py | "
          f"desenho de execucao FECHADO (EnterLimit, alvo fatiado sem prazo)\n", flush=True)

    print("-" * 130)
    print("1) CALIBRACAO -- distribuicao de largura no WDO IS, por janela W (antes de QUALQUER filtro)")
    print("-" * 130)
    pisos = calibra_pisos_de_largura(bars_is, dias_is)
    hdr = (f"  {'W':<5}{'retangulos':>11}{'pregoes com':>13}{'mediana pts':>13}"
           f"{'mediana tk':>11}{'q33 pts':>10}{'q67 pts (piso)':>16}{'q67 ticks':>11}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W, d in pisos.items():
        cobertura = f"{d['pregoes_com']}/{len(dias_is)}"
        print(f"  {W:<5}{d['n']:>11}{cobertura:>13}"
              f"{br(d['mediana_pts'],1):>13}{br(d['mediana_ticks'],1):>11}"
              f"{br(d['q33_pts'],1):>10}{br(d['q67_pts'],1):>16}{br(d['q67_ticks'],1):>11}")
    print(f"\n  piso ESTRUTURAL (formula de pedagio x4, ver wdo_retangulo.LARGURA_MINIMA_TICKS): "
          f"{br(pisos[JANELAS_W[0]]['piso_estrutural_ticks'],1)} ticks "
          f"({br(pisos[JANELAS_W[0]]['piso_estrutural_pts'],2)} pontos)")
    print("  piso EMPIRICO adotado no candidato = q67 (terco SUPERIOR) do PROPRIO W, no IS --")
    print("  mesmo metodo do win_retangulo (328,0 pontos no W20 do WIN); numero aqui e' proprio do WDO.\n")

    piso_w20 = pisos[20]["q67_pts"]
    piso_w30 = pisos[30]["q67_pts"] if 30 in pisos else float("nan")

    VARIANTES = [
        ("1 CANDIDATO W20 (piso tercil)", dict(janela_barras=20, largura_minima_pontos=piso_w20), False),
        ("2 W20 sem piso empirico", dict(janela_barras=20, largura_minima_pontos=0.0), False),
        ("3 W30 (ref, piso tercil)", dict(janela_barras=30, largura_minima_pontos=piso_w30), False),
        ("4 W20 SEM FILA (so' contexto)", dict(janela_barras=20, largura_minima_pontos=piso_w20), True),
    ]

    janelas = {"IS": dias_is, "OOS": dias_oos}
    tarefas = [(jn, dj, rot, kw, sf) for jn, dj in janelas.items() for rot, kw, sf in VARIANTES]

    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["janela"], {})[r["rotulo"]] = r
            c = r["c"]
            print(f"  ok {r['janela']:<5}{r['rotulo']:<32} liquido={br(c['liquido']).rjust(12)}  "
                  f"trades={c['n']:>5}  win={ (br(100*c['win'],1)+'%') if c['n'] else '--':>7}  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}", flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela

    EXTRAS = ("BEemp%", "IC95 win%", "veredito", "sem_tr", "seq-")
    for jn in ("IS", "OOS"):
        dj = janelas[jn]
        print(f"\n\n{'='*130}\nWDO@ wdo_retangulo -- {jn} ({len(dj)} pregoes), capital R$ {br(CAPITAL_REAL_BRL,0)}\n{'='*130}")
        linhas = []
        for rot, _kw, _sf in VARIANTES:
            r = out[jn][rot]
            c = r["c"]
            extras = {
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "IC95 win%": (f"[{br(100*c['lo'],1)};{br(100*c['hi'],1)}]" if c["n"] else "--"),
                "veredito": c["veredito"],
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
                "seq-": str(c["seq_neg"]),
            }
            linhas.append(linha_de_resultado(rot, r["res"], CAPITAL_REAL_BRL, extras=extras))
        print(tabela(linhas, extras=EXTRAS, largura_extra=14))

    print(f"\n\n{'='*130}\nIS x OOS -- replica ou inverte?\n{'='*130}")
    hdr2 = f"  {'variante':<32}{'liq IS':>13}{'liq OOS':>13}{'win IS':>9}{'win OOS':>9}{'BE IS':>8}{'BE OOS':>8}{'sinal':>12}"
    print(hdr2)
    print("  " + "-" * (len(hdr2) - 2))
    for rot, _kw, _sf in VARIANTES:
        a, b = out["IS"][rot]["c"], out["OOS"][rot]["c"]
        if a["liquido"] > 0 and b["liquido"] > 0:
            sinal = "replica +"
        elif a["liquido"] < 0 and b["liquido"] < 0:
            sinal = "replica -"
        else:
            sinal = "INVERTE"
        pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
        print(f"  {rot:<32}{br(a['liquido']):>13}{br(b['liquido']):>13}"
              f"{pc(a['win']):>9}{pc(b['win']):>9}{pc(a['be']):>8}{pc(b['be']):>8}{sinal:>12}")

    print("\n  veredito = IC95 do win% contra o breakeven EMPIRICO: POSITIVO so' se o "
          "intervalo INTEIRO fica acima do breakeven.")
    print("  'sem_tr' = pregoes sem NENHUM trade -- uma linha com sem_tr alto e' CENSURADA: "
          "o liquido mede o portao que parou o robo, nao a estrategia (item 6.15 de LICOES_DE_PRODUCAO.md).")
    print("\nFIM.")


if __name__ == "__main__":
    main()
