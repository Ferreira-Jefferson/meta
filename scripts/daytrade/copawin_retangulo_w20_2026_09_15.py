# -*- coding: utf-8 -*-
"""WIN@ retangulo: a estrategia candidata operando o detector de W=20.

Escolha do dono (2026-09-15): "vamos entao testar com W20, que nos da uma
margem maior e diminui um pouco as ocorrencias de sinais falsos."

E' o ponto intermediario da medicao de deteccao precoce (SO' IS, 129 pregoes):

    W   acerto  taxa base  ganho  cobertura  antecedencia
    10   25,8%     24,7%   1,04x     41,2%      13 barras
    15   36,6%     25,9%   1,41x     55,9%      11 barras
    20   42,7%     24,0%   1,78x     63,1%       8 barras   <- escolhido
    25   54,5%     24,2%   2,25x     65,5%       4 barras

**ESTE SCRIPT TAMBEM RODA SO' NO IS.** O OOS continua intocado -- escolher a
janela de deteccao e' exploracao, e exploracao gasta janela. A confirmacao no
OOS e' uma passada so', depois que o desenho estiver congelado.

## O que muda ao operar W=20 em vez de W=30

Duas coisas ao mesmo tempo, e elas puxam em sentidos opostos:

  (+) a identificacao custa ~20 barras em vez de ~35, entao sobra MAIS vida
      util do retangulo para operar
  (-) o retangulo de W=20 e' menos exigente (menos barras para acumular
      visitas e cruzamentos), entao mais sinais sao falsos

O liquido decide qual das duas pesa mais. Nenhuma das duas e' previsivel de
antemao a partir das tabelas anteriores.

## O piso de largura

O corte de largura foi o unico filtro que manteve sinal e magnitude nas duas
janelas no W=30, entao ele entra aqui tambem. Mas o limiar NAO e' o do W=30
(401 pontos): retangulo de janela menor e' naturalmente mais estreito, entao o
script MEDE a distribuicao de largura do W=20 no IS e usa o proprio terco
superior dela. Reaproveitar o numero do W=30 selecionaria uma fatia diferente
da distribuicao e a comparacao entre janelas deixaria de ser justa.

## A grade

Geometria FIXA no candidato (modo centro, alvo 0,8xL, stop 0,5xL) -- ela nao
e' re-otimizada aqui, senao cada mudanca de janela viraria uma busca nova.
Variam so' os eixos da politica de re-armar, mais o piso de largura.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_w20_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
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

_spec = importlib.util.spec_from_file_location(
    "estr_w20", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_w20"] = _estr
_spec.loader.exec_module(_estr)

_pre = importlib.util.spec_from_file_location(
    "pre_w20", Path(__file__).with_name("copawin_retangulo_deteccao_precoce_2026_09_15.py"))
_precoce = importlib.util.module_from_spec(_pre)
_pre.loader.exec_module(_precoce)

_base = _estr._base
CAPITAL = _estr.CAPITAL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
GEO = dict(modo="centro", alvo_frac=1.6, stop_frac=0.5)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _larguras_do_dia(args):
    dia, W = args
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if len(b) < 3 * W + 10:
        return []
    hi = b["high"].to_numpy(float)
    lo = b["low"].to_numpy(float)
    cl = b["close"].to_numpy(float)
    return [r["largura"] for _t, r in _precoce._confirmacoes(hi, lo, cl, W)]


def _unidade(args):
    rotulo, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _estr._roda(dias, **kw)
    c = _base.consistencia(list(res.trades), dias)
    pts = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    return dict(rotulo=rotulo, c=c, pts=pts)


def main():
    df, dias_todos = _base._df()
    dias = [d for d in dias_todos if d < CORTE_OOS]

    print("=" * 118)
    print("WIN@ retangulo -- a estrategia candidata com deteccao em W=20")
    print("=" * 118)
    print(f"*** SOMENTE IS: {len(dias)} pregoes (< {CORTE_OOS}). O OOS NAO e' lido. ***")
    print(f"geometria FIXA no candidato: modo centro, alvo 0,8xL, stop 0,5xL, 1 contrato, "
          f"capital R$ {br(CAPITAL,0)}\n", flush=True)

    print("medindo a distribuicao de largura do W=20 no IS (para o piso ser o terco")
    print("superior DELE, nao o do W=30)...", flush=True)
    larg = []
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_larguras_do_dia, (d, 20)) for d in dias]
        for fut in as_completed(futs):
            larg.extend(fut.result())
    larg = np.array(larg, dtype=float)
    q33, q67 = float(np.quantile(larg, 1 / 3)), float(np.quantile(larg, 2 / 3))
    print(f"  {len(larg)} retangulos W=20 no IS | largura: p33 {br(q33,0)} · "
          f"mediana {br(float(np.median(larg)),0)} · p67 {br(q67,0)} pontos")
    print(f"  (no W=30 o terco superior comecava em 401 pontos)\n", flush=True)

    variantes = []
    for lmin, tag_l in ((0.0, "todos"), (q67, "largos")):
        for uma, tag_u in ((False, "repete"), (True, "1 por ret.")):
            for mb in (30, 50, None):
                for ex in (0, 10):
                    variantes.append((
                        f"W20 {tag_l:<6} {tag_u:<10} ate {str(mb):<4} +{ex:>2}b",
                        dict(**GEO, W=20, max_barras_apos=mb, uma_por_retangulo=uma,
                             barras_extra_apos_morte=ex, largura_min_pontos=lmin)))
    # referencia: o candidato em W=30, mesmas politicas de destaque
    for lmin, tag in ((0.0, "todos"), (401.0, "largos")):
        variantes.append((f"W30 {tag:<6} repete     ate 50   +10b (ref)",
                          dict(**GEO, W=30, max_barras_apos=50, uma_por_retangulo=False,
                               barras_extra_apos_morte=10, largura_min_pontos=lmin)))

    print(f"{len(variantes)} variantes, IS apenas...\n", flush=True)
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, (rot, dias, kw)): rot for rot, kw in variantes}
        feitos = 0
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            feitos += 1
            if feitos % 8 == 0:
                print(f"  ... {feitos}/{len(variantes)}", flush=True)

    print("\n" + "=" * 118)
    print("RESULTADO NO IS -- W=20 contra a referencia W=30")
    print("=" * 118)
    hdr = (f"  {'variante':<42}{'liquido':>11}{'trades':>8}{'trd/dia':>9}{'win%':>7}"
           f"{'pts/op':>9}{'preg+':>7}{'bl20+':>7}{'top5':>7}{'BEemp%':>9}{'sem_tr':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for rot, _kw in variantes:
        c = out[rot]["c"]
        f = lambda x: 100 * x if x == x else float("nan")
        sem_tr = f"{c['sem_trade']}/{c['pregoes']}"
        print(f"  {rot:<42}{br(c['liquido']):>11}{c['n']:>8}"
              f"{br(c['n']/c['pregoes'],2):>9}"
              f"{(br(f(c['win']),1) if c['n'] else '--'):>7}{br(out[rot]['pts'],2):>9}"
              f"{(br(f(c['frac_preg']),0)+'%'):>7}{(br(f(c['frac_bl']),0)+'%'):>7}"
              f"{(br(f(c['top5']),0)+'%') if c['top5']==c['top5'] else '--':>7}"
              f"{(br(f(c['be']),1)+'%') if c['be']==c['be'] else '--':>9}"
              f"{sem_tr:>10}")

    print("\n*** OOS intocado. ***")
    print("\nFIM.")


if __name__ == "__main__":
    main()
