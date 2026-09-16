# -*- coding: utf-8 -*-
"""ROMPIMENTO: quantas DEFINIÇÕES existem, e qual troca CONTAGEM por ATRASO?

Script irmão de `lateralizacao_catalogo_definicoes_2026_09_16.py` (que cataloga
definições de LATERALIZAÇÃO). Este cobre o território de DEFINIÇÃO do
ROMPIMENTO: fixada a lateralização de referência (o retângulo de produção,
já validado e em operação), quantas maneiras existem de dizer "isto rompeu",
e o que cada uma custa em atraso de detecção e em falso alarme?

## O que este script NÃO responde (territórios de outros agentes)

- Anatomia pós-rompimento (MFE/MAE, reteste, corrida alvo×stop) — isso é
  `rompimento_retangulo_fenomeno_2026_09_16.py`, que já mediu 417
  rompimentos pela regra de morte de PRODUÇÃO (k=0,25, N=3 nesta notação).
  Este script não repete aquelas perguntas — ele varia o PARÂMETRO da
  definição de rompimento e mede count×atraso×falso-alarme, o que aquele
  script não fez.
- Executabilidade / fila — não medido aqui.
- Qual geometria de entrada paga o rompimento — não é esta rodada.

## A população de referência

Retângulos detectados por `detecta_retangulo` (produção), W=20, tolerância
0,20, largura mínima 328 pontos — IDÊNTICA à população do script de anatomia
e do `win_retangulo`. O que muda entre variantes é só a regra que decide
"este retângulo rompeu aqui".

## As famílias de definição de rompimento

| família | regra | grade |
|---|---|---|
| fechamento+margem | fechamento além da borda + k×largura, por N barras CONSECUTIVAS | k∈{0; 0,10; 0,25; 0,50} × N∈{1,2,3} — a de k=0,25/N=3 é a regra de morte de PRODUÇÃO |
| extremo+margem | MÁXIMA/MÍNIMA (não fechamento) além da borda + k×largura, 1 barra | k∈{0; 0,10; 0,25} |
| múltiplo de ATR | fechamento além da borda + m×ATR14 (ATR congelado no nascimento do retângulo), 1 barra | m∈{0; 0,5; 1,0; 2,0} |
| volume | fechamento além da borda (k=0) E volume da barra ≥ percentil P do volume causal (janela 60) | P∈{75; 90} |

21 variantes ao todo. Para cada uma: quantos retângulos disparam dentro de um
horizonte de 200 barras, o ATRASO no instante do disparo (pontos além da
borda CRUA — não da borda+margem, para que k e N apareçam no próprio atraso
em vez de ficarem escondidos atrás dele) e a taxa de FALSO ALARME
("desrompimento": o preço volta para dentro do retângulo em K barras).

## O nulo de cada coluna

- Contagem: nulo é o total de retângulos da população (mesmo denominador
  para todas as variantes) — reporta-se `n disparou / total` para toda
  variante, nunca `n` isolado.
- Atraso: nulo é a variante MAIS eager desta grade (fechamento, k=0, N=1) —
  toda variante mais estrita é comparada contra o atraso DELA.
- Falso alarme: nulo é 0% de desrompimento; toda taxa >0% é o preço da
  definição, e correlaciona com quão CEDO ela detecta (ver Q6 do pedido).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/lateralizacao_rompimento_definicoes_2026_09_16.py`
"""
from __future__ import annotations

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

from core.indicators import atr  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import detecta_retangulo  # noqa: E402

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA_PRODUCAO = 0.20  # a que o robô OPERA — ver nota em CLAUDE.md/win_retangulo
LARGURA_MINIMA_PRODUCAO = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
HORIZONTE_MAX = 200  # barras à frente do nascimento em que se procura o disparo
JANELA_VOLUME_PCTL = 60
LIMIARES_DESROMPIMENTO = (5, 10, 20)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return "—" if x != x else br(100 * x, 1) + "%"


def _rolling_pct_rank_last(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        janela = x[i - window + 1 : i + 1]
        val = janela[-1]
        if np.isnan(val) or np.isnan(janela).any():
            continue
        out[i] = float(np.mean(janela <= val))
    return out


# --------------------------------------------------------------------------
# população de referência: retângulos de produção (nascimento + geometria)
# --------------------------------------------------------------------------

def detecta_retangulos_do_dia(g: pd.DataFrame) -> list[dict]:
    """Máquina de estado idêntica à do robô: rearma só depois da MORTE de
    produção (25% da largura, 3 barras). O que sai daqui é a POPULAÇÃO —
    a definição de rompimento propriamente dita é testada DEPOIS, por cada
    variante, independente de quando a morte de produção teria disparado."""
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    n = len(g)
    rects: list[dict] = []
    ret = None
    fora = 0
    nascimento = 0
    i = 3 * JANELA
    while i < n:
        if ret is None:
            anterior = float(h[i - 3 * JANELA : i - JANELA].max()
                             - l[i - 3 * JANELA : i - JANELA].min())
            r = detecta_retangulo(h[i - JANELA:i], l[i - JANELA:i], c[i - JANELA:i],
                                  anterior, tolerancia=TOLERANCIA_PRODUCAO)
            if r is not None and r["largura"] >= LARGURA_MINIMA_PRODUCAO:
                ret, fora, nascimento = r, 0, i
                rects.append(dict(nascimento=i, topo=r["topo"], piso=r["piso"],
                                  meio=r["meio"], largura=r["largura"]))
            i += 1
            continue
        margem = 0.25 * ret["largura"]
        fora_da_banda = c[i] > ret["topo"] + margem or c[i] < ret["piso"] - margem
        if fora_da_banda:
            fora += 1
            if fora >= 3:
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    return rects


# --------------------------------------------------------------------------
# variantes de disparo de rompimento
# --------------------------------------------------------------------------

def _fim(inicio: int, tamanho: int) -> int:
    return min(inicio + HORIZONTE_MAX, tamanho)


def dispara_fechamento(day: dict, rect: dict, k: float, nbarras: int) -> dict | None:
    close = day["close"]
    topo, piso, largura = rect["topo"], rect["piso"], rect["largura"]
    margem = k * largura
    start = rect["nascimento"] + 1
    end = _fim(start, len(close))
    fora = 0
    for i in range(start, end):
        acima = close[i] > topo + margem
        abaixo = close[i] < piso - margem
        if acima or abaixo:
            fora += 1
            if fora >= nbarras:
                lado = "alta" if acima else "baixa"
                borda = topo if lado == "alta" else piso
                atraso = abs(close[i] - borda)
                return dict(idx=i, lado=lado, atraso=atraso, atraso_frac=atraso / largura)
        else:
            fora = 0
    return None


def dispara_extremo(day: dict, rect: dict, k: float) -> dict | None:
    high, low = day["high"], day["low"]
    topo, piso, largura = rect["topo"], rect["piso"], rect["largura"]
    margem = k * largura
    start = rect["nascimento"] + 1
    end = _fim(start, len(high))
    for i in range(start, end):
        acima = high[i] > topo + margem
        abaixo = low[i] < piso - margem
        if acima or abaixo:
            lado = "alta" if acima else "baixa"
            borda = topo if lado == "alta" else piso
            preco = high[i] if lado == "alta" else low[i]
            atraso = abs(preco - borda)
            return dict(idx=i, lado=lado, atraso=atraso, atraso_frac=atraso / largura)
    return None


def dispara_atr(day: dict, rect: dict, m: float) -> dict | None:
    close, atr14 = day["close"], day["atr14"]
    topo, piso, largura = rect["topo"], rect["piso"], rect["largura"]
    ref_idx = rect["nascimento"] - 1
    atr_ref = float(atr14[ref_idx]) if ref_idx >= 0 and not np.isnan(atr14[ref_idx]) else np.nan
    if np.isnan(atr_ref):
        return None
    margem = m * atr_ref
    start = rect["nascimento"] + 1
    end = _fim(start, len(close))
    for i in range(start, end):
        acima = close[i] > topo + margem
        abaixo = close[i] < piso - margem
        if acima or abaixo:
            lado = "alta" if acima else "baixa"
            borda = topo if lado == "alta" else piso
            atraso = abs(close[i] - borda)
            return dict(idx=i, lado=lado, atraso=atraso, atraso_frac=atraso / largura)
    return None


def dispara_volume(day: dict, rect: dict, p: float) -> dict | None:
    close, volpct = day["close"], day["volpct"]
    topo, piso, largura = rect["topo"], rect["piso"], rect["largura"]
    start = rect["nascimento"] + 1
    end = _fim(start, len(close))
    limiar = p / 100.0
    for i in range(start, end):
        acima = close[i] > topo
        abaixo = close[i] < piso
        if (acima or abaixo) and not np.isnan(volpct[i]) and volpct[i] >= limiar:
            lado = "alta" if acima else "baixa"
            borda = topo if lado == "alta" else piso
            atraso = abs(close[i] - borda)
            return dict(idx=i, lado=lado, atraso=atraso, atraso_frac=atraso / largura)
    return None


def desrompeu(day: dict, idx_disparo: int, topo: float, piso: float, k: int) -> float:
    close = day["close"]
    fim = min(idx_disparo + 1 + k, len(close))
    seg = close[idx_disparo + 1 : fim]
    if len(seg) == 0:
        return float("nan")
    return float(np.any((seg >= piso) & (seg <= topo)))


VARIANTES = (
    [(f"fechamento k={k:.2f} N={n}", "fechamento", dict(k=k, nbarras=n))
     for k in (0.0, 0.10, 0.25, 0.50) for n in (1, 2, 3)]
    + [(f"extremo k={k:.2f}", "extremo", dict(k=k)) for k in (0.0, 0.10, 0.25)]
    + [(f"atr m={m:.1f}", "atr", dict(m=m)) for m in (0.0, 0.5, 1.0, 2.0)]
    + [(f"volume p={p:.0f}", "volume", dict(p=p)) for p in (75.0, 90.0)]
)


def processa_variante(nome: str, tipo: str, params: dict, dados_por_dia: dict,
                      rects: list[dict]) -> dict:
    buf = StringIO()
    with redirect_stdout(buf):
        resultados = []
        for rect in rects:
            day = dados_por_dia[rect["dia"]]
            if tipo == "fechamento":
                r = dispara_fechamento(day, rect, **params)
            elif tipo == "extremo":
                r = dispara_extremo(day, rect, **params)
            elif tipo == "atr":
                r = dispara_atr(day, rect, **params)
            else:
                r = dispara_volume(day, rect, **params)
            if r is None:
                resultados.append(dict(disparou=False))
                continue
            fa = {k: desrompeu(day, r["idx"], rect["topo"], rect["piso"], k)
                  for k in LIMIARES_DESROMPIMENTO}
            resultados.append(dict(disparou=True, atraso=r["atraso"],
                                   atraso_frac=r["atraso_frac"], **{f"fa{k}": v
                                   for k, v in fa.items()}))
    print(buf.getvalue(), end="", flush=True)
    return dict(nome=nome, tipo=tipo, params=params, resultados=resultados)


def linha_resumo(nome: str, resultados: list[dict], total: int) -> str:
    disp = [r for r in resultados if r["disparou"]]
    n = len(disp)
    if n == 0:
        return f"  {nome:<24} 0/{total} nunca disparou dentro de {HORIZONTE_MAX} barras"
    atraso = np.array([r["atraso"] for r in disp], float)
    frac = np.array([r["atraso_frac"] for r in disp], float)
    fa10 = np.array([r["fa10"] for r in disp], float)
    fa10 = fa10[~np.isnan(fa10)]
    return (f"  {nome:<24} {n:>4}/{total} ({_pct(n/total):>6})  "
            f"atraso med {br(float(np.median(atraso)),0):>5}pts "
            f"({_pct(float(np.median(frac))):>6} da largura)  "
            f"desrompe(K=10) {_pct(float(fa10.mean())) if len(fa10) else '—':>6}")


def main():
    df = load_m1(SIMBOLO).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, c in cont.items() if c >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    dados_por_dia: dict = {}
    rects: list[dict] = []
    for d in dias:
        g = df[df.index.date == d]
        if len(g) < 3 * JANELA + 5:
            continue
        close = g["close"].to_numpy(float)
        high = g["high"].to_numpy(float)
        low = g["low"].to_numpy(float)
        vol = g["tick_volume"].to_numpy(float)
        atr14 = atr(g["high"], g["low"], g["close"], window=14).to_numpy(float)
        volpct = _rolling_pct_rank_last(vol, JANELA_VOLUME_PCTL)
        dados_por_dia[d] = dict(close=close, high=high, low=low, vol=vol,
                                atr14=atr14, volpct=volpct)
        for r in detecta_retangulos_do_dia(g):
            r["dia"] = d
            rects.append(r)

    total = len(rects)
    print("=" * 140)
    print("ROMPIMENTO: CATÁLOGO DE DEFINIÇÕES — WIN@ M1, IS apenas")
    print("=" * 140)
    print(f"  {len(dados_por_dia)} pregões | {dias[0]} a {dias[-1]}")
    print(f"  população: {total} retângulos de produção ({br(total/len(dados_por_dia),2)}/pregão) "
          f"— W={JANELA}, tol={TOLERANCIA_PRODUCAO}, largura mín={br(LARGURA_MINIMA_PRODUCAO,0)}")
    print(f"  horizonte de busca do disparo: {HORIZONTE_MAX} barras à frente do nascimento")
    print(f"  {len(VARIANTES)} variantes de rompimento testadas\n", flush=True)

    print("-" * 140)
    print("CONTAGEM × ATRASO × FALSO ALARME (cada linha sai assim que a unidade termina)")
    print("-" * 140)
    resultados_por_variante: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=min(8, len(VARIANTES))) as ex:
        futs = {ex.submit(processa_variante, nome, tipo, params, dados_por_dia, rects): nome
                for nome, tipo, params in VARIANTES}
        for fut in as_completed(futs):
            r = fut.result()
            resultados_por_variante[r["nome"]] = r
            print(linha_resumo(r["nome"], r["resultados"], total), flush=True)

    print("\n" + "=" * 140)
    print("TABELA ORDENADA (pela família, na ordem declarada) — contagem × atraso × falso alarme")
    print("=" * 140)
    print(f"  {'variante':<24}{'n/total':>14}{'atraso pts':>12}{'atraso %larg':>14}"
          f"{'desr. K=5':>11}{'desr. K=10':>12}{'desr. K=20':>12}")
    for nome, tipo, params in VARIANTES:
        r = resultados_por_variante[nome]
        disp = [x for x in r["resultados"] if x["disparou"]]
        n = len(disp)
        if n == 0:
            print(f"  {nome:<24}{'0/' + str(total):>14}{'—':>12}{'—':>14}{'—':>11}{'—':>12}{'—':>12}")
            continue
        atraso = float(np.median([x["atraso"] for x in disp]))
        frac = float(np.median([x["atraso_frac"] for x in disp]))
        fas = {}
        for k in LIMIARES_DESROMPIMENTO:
            vals = np.array([x[f"fa{k}"] for x in disp], float)
            vals = vals[~np.isnan(vals)]
            fas[k] = float(vals.mean()) if len(vals) else float("nan")
        print(f"  {nome:<24}{f'{n}/{total}':>14}{br(atraso,0):>12}{_pct(frac):>14}"
              f"{_pct(fas[5]):>11}{_pct(fas[10]):>12}{_pct(fas[20]):>12}")

    print("\n" + "=" * 140)
    print("COMO LER")
    print("=" * 140)
    print("  * A POPULAÇÃO (retângulos) é sempre a mesma — só a regra de disparo muda entre linhas.")
    print("  * 'atraso' é medido da BORDA CRUA (não da borda+margem): k e N aparecem no próprio")
    print("    número, e por isso é comparável entre TODAS as famílias, inclusive ATR e volume.")
    print("  * 'desrompe' é a fração de disparos em que o preço volta para DENTRO do retângulo em")
    print("    K barras — é o falso-alarme: detectar cedo demais e o preço nunca ir embora de verdade.")
    print("  * fechamento k=0,25/N=3 é a regra de PRODUÇÃO (win_retangulo) — use-a como referência,")
    print("    não como nulo: o nulo de atraso é a linha MAIS eager (fechamento k=0/N=1).")
    print("  * Só o IS. A janela cega fica intacta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
