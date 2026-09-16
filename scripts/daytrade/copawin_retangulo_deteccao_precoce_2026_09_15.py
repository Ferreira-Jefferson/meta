# -*- coding: utf-8 -*-
"""WIN@ retangulo: da' para identificar o retangulo ANTES do W30, a partir do
W10? E qual e' a taxa de acerto?

Pedido do dono (2026-09-15): "quero que tente identificar o inicio do retangulo
antes do w30, a partir de w10 -- qual a sua taxa de acerto? Nao toque no OOS
ainda."

**ESTE SCRIPT RODA SO' NO IS (< 2026-06-13).** O OOS nao e' lido em lugar
nenhum. Ordem explicita do dono, e ela e' certa: um detector precoce e'
exatamente o tipo de coisa que se ajusta ate' funcionar, e gastar o OOS na
exploracao destroi a unica confirmacao que sobra.

## Por que isto importa

A identificacao consome quase toda a vida util do retangulo: no W=30 a latencia
mediana e' 35 min contra 61 min de duracao total -- so' **33% e' aproveitavel**.
Se um sinal em W=10 antecipar a confirmacao em ~20 barras, a fracao util
praticamente dobra. E' a maior alavanca disponivel nesta linha, maior que
qualquer ajuste de alvo ou stop.

## O que e' um ACERTO

Sinal precoce na barra `t`, com banda [piso_e, topo_e] e meio `meio_e`. E'
ACERTO se, dentro de `HORIZONTE` barras depois de `t`, o detector de W=30
confirmar um retangulo cujo meio esteja a no maximo `TOL_MEIO x L_e` do
`meio_e` -- ou seja, nao basta aparecer um retangulo qualquer depois; tem de
ser um retangulo NO MESMO LUGAR. Sem essa condicao de lugar, "acerto" viraria
"o mercado lateralizou em algum momento", que acontece o tempo todo.

## O NULO, sem o qual a precisao nao quer dizer nada

O W=30 confirma ~5,24 retangulos por pregao em ~500 barras uteis. A chance de
um retangulo W30 aparecer nos proximos `HORIZONTE` barras a partir de uma barra
QUALQUER ja e' alta por construcao. Por isso o script calcula a TAXA BASE
(mesma pergunta, feita em barras sorteadas em vez de nos sinais precoces) e
reporta o GANHO (precisao / taxa base). Precisao de 40% contra taxa base de
35% nao e' detector, e' relogio parado.

Tambem sai a COBERTURA (dos retangulos W30 confirmados, quantos tinham um
sinal precoce antes) e a ANTECEDENCIA em barras -- um detector preciso que
avisa 2 barras antes nao serve para nada.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_deteccao_precoce_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_pre")
_det = _carrega("copawin_retangulo_lateral_2026_09_15.py", "_det_pre")

CORTE_OOS = pd.Timestamp("2026-06-13").date()
TICK = 5.0
MARGEM_MORTE, BARRAS_MORTE = 0.25, 3
W_ALVO = 30                      # o detector "verdade"
W_PRECOCES = (10, 15, 20, 25)
HORIZONTE = 30                   # barras para o W30 confirmar depois do sinal
TOL_MEIO = 0.50                  # o meio do W30 tem de cair dentro disto x L_e
N_SORTEIOS = 40                  # barras sorteadas por pregao para a taxa base


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _confirmacoes(hi, lo, cl, W):
    """Lista de (barra, ret) das confirmacoes de retangulo com janela W, com a
    mesma supressao/morte do detector original."""
    n = len(cl)
    saida = []
    ret = None
    fora = 0
    for t in range(3 * W, n):
        if ret is not None:
            L = ret["largura"]
            if cl[t] > ret["topo"] + MARGEM_MORTE * L or cl[t] < ret["piso"] - MARGEM_MORTE * L:
                fora += 1
                if fora >= BARRAS_MORTE:
                    ret, fora = None, 0
            else:
                fora = 0
            continue
        range_antes = float(hi[t - 3 * W:t - W + 1].max() - lo[t - 3 * W:t - W + 1].min())
        cand = _det._avalia_janela(hi[t - W + 1:t + 1], lo[t - W + 1:t + 1],
                                   cl[t - W + 1:t + 1], range_antes)
        if cand is None or cand["largura"] < _det.LARGURA_MIN_TICKS * TICK:
            continue
        ret, fora = cand, 0
        saida.append((t, cand))
    return saida


def roda_dia(dia):
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if len(b) < 3 * W_ALVO + 40:
        return None
    hi = b["high"].to_numpy(float)
    lo = b["low"].to_numpy(float)
    cl = b["close"].to_numpy(float)
    n = len(cl)

    alvo = _confirmacoes(hi, lo, cl, W_ALVO)
    saida = {"dia": dia, "n_barras": n, "n_alvo": len(alvo), "precoces": {}}

    def casa(t, ret_e):
        """Existe confirmacao W30 em (t, t+HORIZONTE] no MESMO lugar?"""
        for t30, r30 in alvo:
            if t < t30 <= t + HORIZONTE:
                if abs(r30["meio"] - ret_e["meio"]) <= TOL_MEIO * ret_e["largura"]:
                    return t30 - t
        return None

    for W in W_PRECOCES:
        sinais = _confirmacoes(hi, lo, cl, W)
        acertos, antec = 0, []
        for t, ret_e in sinais:
            d = casa(t, ret_e)
            if d is not None:
                acertos += 1
                antec.append(d)
        # cobertura: dos W30 confirmados, quantos tinham sinal precoce antes
        cobertos = 0
        for t30, r30 in alvo:
            for t, ret_e in sinais:
                if t < t30 <= t + HORIZONTE and abs(r30["meio"] - ret_e["meio"]) <= TOL_MEIO * ret_e["largura"]:
                    cobertos += 1
                    break
        # taxa base: barras sorteadas, mesma pergunta, usando a banda LOCAL
        rng = np.random.default_rng(abs(hash((str(dia), W))) % (2 ** 32))
        base_hit = 0
        cand_base = rng.integers(3 * W_ALVO, n - 1, size=min(N_SORTEIOS, max(1, n - 3 * W_ALVO - 1)))
        for t in cand_base:
            t = int(t)
            topo = float(np.quantile(hi[max(0, t - W + 1):t + 1], 0.90))
            piso = float(np.quantile(lo[max(0, t - W + 1):t + 1], 0.10))
            fake = dict(meio=(topo + piso) / 2.0, largura=max(topo - piso, 1e-9))
            if casa(t, fake) is not None:
                base_hit += 1
        saida["precoces"][W] = dict(
            n_sinais=len(sinais), acertos=acertos, antec=antec,
            cobertos=cobertos, base_hit=base_hit, base_n=len(cand_base))
    return saida


def main():
    df, dias_todos = _base._df()
    dias = [d for d in dias_todos if d < CORTE_OOS]
    print("=" * 112)
    print("WIN@ -- DETECCAO PRECOCE do retangulo (W10..W25 antecipando o W30)")
    print("=" * 112)
    print(f"*** SOMENTE IS: {len(dias)} pregoes (< {CORTE_OOS}). O OOS NAO e' lido. ***")
    print(f"acerto = confirmacao W30 em ate {HORIZONTE} barras depois do sinal, com o meio")
    print(f"         a no maximo {br(TOL_MEIO,2)}x a largura do sinal precoce (mesmo LUGAR)")
    print(f"motivo: a latencia do W30 come 2/3 da vida do retangulo (35 min de 61)\n", flush=True)

    linhas = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(roda_dia, d): d for d in dias}
        feitos = 0
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                linhas.append(r)
            feitos += 1
            if feitos % 30 == 0:
                print(f"  ... {feitos}/{len(dias)}", flush=True)

    n_alvo = sum(r["n_alvo"] for r in linhas)
    print(f"\n{len(linhas)} pregoes | {n_alvo} retangulos W30 confirmados "
          f"({br(n_alvo/len(linhas),2)}/pregao)\n")

    print("=" * 112)
    print("TAXA DE ACERTO DO SINAL PRECOCE")
    print("=" * 112)
    hdr = (f"  {'W':<5}{'sinais':>9}{'sinais/dia':>12}{'ACERTO':>9}{'taxa base':>11}"
           f"{'GANHO':>8}{'cobertura':>11}{'antec. mediana':>16}{'p25':>6}{'p75':>6}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in W_PRECOCES:
        ns = sum(r["precoces"][W]["n_sinais"] for r in linhas)
        ac = sum(r["precoces"][W]["acertos"] for r in linhas)
        cob = sum(r["precoces"][W]["cobertos"] for r in linhas)
        bh = sum(r["precoces"][W]["base_hit"] for r in linhas)
        bn = sum(r["precoces"][W]["base_n"] for r in linhas)
        antec = np.array([a for r in linhas for a in r["precoces"][W]["antec"]], dtype=float)
        prec = ac / ns if ns else float("nan")
        base = bh / bn if bn else float("nan")
        print(f"  {W:<5}{ns:>9}{br(ns/len(linhas),2):>12}"
              f"{(br(100*prec,1) + '%'):>9}{(br(100*base,1) + '%'):>11}"
              f"{br(prec/base,2) + 'x':>8}"
              f"{(br(100*cob/n_alvo,1) + '%'):>11}"
              f"{br(np.median(antec),1) if len(antec) else '—':>16}"
              f"{br(np.quantile(antec,.25),0) if len(antec) else '—':>6}"
              f"{br(np.quantile(antec,.75),0) if len(antec) else '—':>6}")

    print("\n  ACERTO    = dos sinais precoces, quantos viraram retangulo W30 no mesmo lugar")
    print("  taxa base = a MESMA pergunta feita em barras sorteadas (o nulo)")
    print("  GANHO     = acerto / taxa base. Perto de 1,0x o detector precoce nao informa nada")
    print("              alem do que ja se sabe por o mercado lateralizar com frequencia.")
    print("  cobertura = dos retangulos W30, quantos tiveram aviso precoce antes")
    print("  antec.    = quantas BARRAS antes o aviso veio (e o que se ganharia de vida util)")
    print("\n*** OOS intocado. Qualquer confirmacao desta medicao tem de ser feita la', uma vez so'.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
