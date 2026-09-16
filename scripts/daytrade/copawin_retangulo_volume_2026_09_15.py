# -*- coding: utf-8 -*-
"""WIN@ retangulo: o VOLUME confirma a zona de lateralizacao?

Pedido do dono (2026-09-15): "outra coisa que pode ser usada para confirmar se
e' uma zona de lateralizacao talvez seja o volume, pode ser que ele de sinais,
verifique."

**SO' IS (< 2026-06-13). O OOS nao e' lido.** Mesma disciplina das duas
medicoes anteriores: escolher features gasta janela.

## A tese classica, e por que ela merece teste e nao fe

Manual de analise tecnica diz que consolidacao vem com volume MINGUANDO e o
rompimento vem com volume EXPLODINDO. Se isso for verdade no WIN M1, o volume
serve para duas coisas diferentes, e o script separa as duas:

  A) CONFIRMAR o retangulo -- o volume distingue um retangulo que vai vingar de
     um sinal falso? (mede-se contra o sinal precoce: o W=20 acerta 42,7% das
     vezes; o volume sobe isso?)

  B) SELECIONAR o retangulo que PAGA -- de todos os retangulos detectados,
     aqueles com assinatura de volume X rendem mais? E' a pergunta que muda a
     estrategia, e e' diferente de (A): um retangulo pode ser "de verdade" e
     ainda assim nao pagar.

## As features (todas causais, so' barras ate a confirmacao)

    contracao_vol  = volume medio da janela W / volume medio das 2W barras
                     ANTERIORES a ela. < 1 = volume minguou formando a zona.
    razao_dia      = volume medio da janela / volume medio do pregao ate' aqui.
    tendencia_vol  = volume medio do ULTIMO terco da janela / do PRIMEIRO terco.
                     < 1 = secando ate' o fim da formacao.
    vol_por_ponto  = volume medio da janela / largura da banda. Muito volume
                     para pouco deslocamento e' a definicao microestrutural de
                     absorcao -- e' a feature que mais se parece com "briga de
                     forcas dentro da faixa".

`load_m1` devolve `real_volume`/`tick_volume` (MT5), nao `volume`: a regra e' a
mesma de `backtest.intraday.engine._bar_volume` -- prefere `real_volume` quando
> 0, senao `tick_volume`. Replicada aqui para as contas externas.

## O desfecho medido

Para cada retangulo W=20 detectado, simula-se a entrada candidata (limite no
CENTRO do lado que descansa, alvo 0,8xL, stop 0,5xL, prazo 10 barras) e
registra-se o resultado liquido em pontos (custo de 7,5 ja descontado, empate
alvo/stop na mesma barra conta como STOP).

Tercos de cada feature e resultado por terco. Uma feature que nao separa e'
feature morta -- e a maioria vai ser.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_volume_2026_09_15.py`
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


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_vol")
_det = _carrega("copawin_retangulo_lateral_2026_09_15.py", "_det_vol")
_pre = _carrega("copawin_retangulo_deteccao_precoce_2026_09_15.py", "_pre_vol")

CORTE_OOS = pd.Timestamp("2026-06-13").date()
TICK, CUSTO = 5.0, 7.5
W = 20
W30 = 30
HORIZONTE, TOL_MEIO = 30, 0.50
ALVO_L, STOP_L = 0.80, 0.50
TTL = 10
MARGEM_MORTE, BARRAS_MORTE = 0.25, 3
FEATURES = ("contracao_vol", "razao_dia", "tendencia_vol", "vol_por_ponto")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _volume(b: pd.DataFrame) -> np.ndarray:
    real = b["real_volume"].fillna(0.0).to_numpy(float) if "real_volume" in b.columns \
        else np.zeros(len(b))
    tickv = b["tick_volume"].fillna(0.0).to_numpy(float) if "tick_volume" in b.columns \
        else np.zeros(len(b))
    return np.where(real > 0, real, tickv)


def roda_dia(dia):
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if len(b) < 3 * W30 + 40:
        return []
    hi, lo, cl = (b["high"].to_numpy(float), b["low"].to_numpy(float),
                  b["close"].to_numpy(float))
    vol = _volume(b)
    n = len(cl)

    conf30 = _pre._confirmacoes(hi, lo, cl, W30)
    sinais = _pre._confirmacoes(hi, lo, cl, W)

    saida = []
    for t, ret in sinais:
        L, meio, topo, piso = ret["largura"], ret["meio"], ret["topo"], ret["piso"]
        a, z = t - W + 1, t + 1
        v_jan = float(vol[a:z].mean())
        v_antes = float(vol[max(0, t - 3 * W):a].mean()) if a > 0 else float("nan")
        v_dia = float(vol[:z].mean())
        terco = max(1, W // 3)
        v_ini = float(vol[a:a + terco].mean())
        v_fim = float(vol[z - terco:z].mean())

        # (A) virou retangulo W30 no mesmo lugar?
        virou = 0
        for t30, r30 in conf30:
            if t < t30 <= t + HORIZONTE and abs(r30["meio"] - meio) <= TOL_MEIO * L:
                virou = 1
                break

        # (B) desfecho da entrada candidata
        lado = -1 if cl[t] < meio else (1 if cl[t] > meio else 0)
        pnl = float("nan")
        if lado != 0 and ((lado < 0 and meio > cl[t]) or (lado > 0 and meio < cl[t])):
            fill = None
            for j in range(t + 1, min(t + 1 + TTL, n)):
                if (lado < 0 and hi[j] >= meio) or (lado > 0 and lo[j] <= meio):
                    fill = j
                    break
            if fill is not None:
                alvo_p = meio + lado * ALVO_L * L
                stop_p = meio - lado * STOP_L * L
                pnl = float("nan")
                for j in range(fill + 1, n):
                    bate_stop = (lo[j] <= stop_p) if lado > 0 else (hi[j] >= stop_p)
                    bate_alvo = (hi[j] >= alvo_p) if lado > 0 else (lo[j] <= alvo_p)
                    if bate_stop:
                        pnl = -STOP_L * L - CUSTO
                        break
                    if bate_alvo:
                        pnl = ALVO_L * L - CUSTO
                        break
                if pnl != pnl:
                    pnl = (cl[n - 1] - meio) * lado - CUSTO

        saida.append(dict(
            data=dia, largura=L, virou=virou, pnl=pnl,
            contracao_vol=(v_jan / v_antes) if v_antes and v_antes == v_antes else float("nan"),
            razao_dia=(v_jan / v_dia) if v_dia else float("nan"),
            tendencia_vol=(v_fim / v_ini) if v_ini else float("nan"),
            vol_por_ponto=(v_jan / L) if L > 0 else float("nan")))
    return saida


def _tabela(d, col, rot, valor, nome_valor):
    v = d[col].replace([np.inf, -np.inf], np.nan).dropna()
    if len(v) < 60:
        return
    c1, c2 = float(v.quantile(1 / 3)), float(v.quantile(2 / 3))
    d = d.copy()
    d["b"] = pd.cut(d[col], [-np.inf, c1, c2, np.inf], labels=["1-baixo", "2-medio", "3-alto"])
    print(f"\n  --- {rot}  (cortes {br(c1,3)} / {br(c2,3)}) ---")
    print(f"  {'faixa':<10}{'n':>7}{nome_valor:>16}{'desvio':>11}")
    for nome, g in d.groupby("b", observed=True):
        s = g[valor].dropna()
        if len(s) == 0:
            continue
        print(f"  {str(nome):<10}{len(s):>7}{br(s.mean(), 3):>16}"
              f"{br(s.std(ddof=1), 2) if len(s) > 1 else '—':>11}")


def main():
    df, dias_todos = _base._df()
    dias = [d for d in dias_todos if d < CORTE_OOS]
    print("=" * 104)
    print("WIN@ retangulo -- o VOLUME confirma a zona de lateralizacao?")
    print("=" * 104)
    print(f"*** SOMENTE IS: {len(dias)} pregoes (< {CORTE_OOS}). O OOS NAO e' lido. ***")
    print(f"deteccao em W={W} (a escolha do dono) | entrada candidata: limite no centro,")
    print(f"alvo {br(ALVO_L,2)}xL, stop {br(STOP_L,2)}xL, custo {br(CUSTO,1)} pontos descontado\n",
          flush=True)

    linhas = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(roda_dia, d): d for d in dias}
        feitos = 0
        for fut in as_completed(futs):
            linhas.extend(fut.result())
            feitos += 1
            if feitos % 30 == 0:
                print(f"  ... {feitos}/{len(dias)}", flush=True)

    d = pd.DataFrame(linhas)
    d.to_csv(ROOT / "scratch" / "copawin_retangulo_volume_is.csv", index=False, encoding="utf-8")
    com_trade = d["pnl"].notna().sum()
    print(f"\n{len(d)} retangulos W={W} no IS | {com_trade} com entrada preenchida "
          f"| {100*d['virou'].mean():.1f}% viraram retangulo W30 no mesmo lugar\n")

    print("=" * 104)
    print("DESCRITIVO -- como o volume se comporta na formacao da zona")
    print("=" * 104)
    print(f"  {'feature':<18}{'p10':>10}{'p25':>10}{'mediana':>10}{'p75':>10}{'p90':>10}")
    for f in FEATURES:
        v = d[f].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"  {f:<18}{br(v.quantile(.10),3):>10}{br(v.quantile(.25),3):>10}"
              f"{br(v.median(),3):>10}{br(v.quantile(.75),3):>10}{br(v.quantile(.90),3):>10}")
    print("\n  contracao_vol < 1 = o volume MINGUOU formando a zona (a tese classica).")

    print("\n" + "=" * 104)
    print("(A) O VOLUME CONFIRMA? -- fracao que virou retangulo W30 no mesmo lugar, por terco")
    print("    (a taxa media do W=20 e' o numero a bater; sem separacao, feature morta)")
    print("=" * 104)
    for f in FEATURES:
        _tabela(d, f, f, "virou", "fracao que virou")

    print("\n" + "=" * 104)
    print("(B) O VOLUME SELECIONA O QUE PAGA? -- pontos liquidos por operacao, por terco")
    print("=" * 104)
    for f in FEATURES:
        _tabela(d[d["pnl"].notna()], f, f, "pnl", "pontos liq./op")

    print("\n*** OOS intocado. ***")
    print("\nFIM.")


if __name__ == "__main__":
    main()
