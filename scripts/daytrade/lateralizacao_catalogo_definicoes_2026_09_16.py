# -*- coding: utf-8 -*-
"""LATERALIZAÇÃO: quantas DEFINIÇÕES existem, e elas descrevem o mesmo fenômeno?

Pedido do dono (2026-09-16): repetir para ROMPIMENTO o mesmo caminho que
produziu o `win_retangulo` — perguntar, medir, guardar, só depois desenhar.
Este script cobre o território de DEFINIÇÃO da lateralização (o rompimento
tem script irmão: `lateralizacao_rompimento_definicoes_2026_09_16.py`).

## O que este script responde

1. `detecta_retangulo` (produção) é UMA definição de lateralização. Quantas
   outras definições, medidas com o mesmo rigor (mesma janela W=20 onde faz
   sentido, mesmo IS, mesmo piso de 400 barras/pregão), produzem quantos
   eventos por pregão, de que duração, de que largura, em que hora do dia?
2. Elas descrevem o MESMO fenômeno? Matriz de concordância: quando o
   retângulo de produção está ATIVO numa barra, qual fração das barras as
   outras 6 definições também marcam como lateral (e vice-versa)?

## O que este script NÃO responde (territórios de outros agentes)

- Anatomia do que acontece DEPOIS do rompimento (MFE/MAE, reteste, corrida
  alvo×stop) — isso é `rompimento_retangulo_fenomeno_2026_09_16.py`.
- Executabilidade (fila, deslize) — não medido aqui.
- Qual definição de ROMPIMENTO é melhor — script irmão.

## Definições catalogadas (todas CAUSAIS — só olham para trás)

| # | nome | ideia | limiar (documentado, não calibrado) |
|---|---|---|---|
| 1 | `retangulo_producao` | `detecta_retangulo` do robô, W=20, tol 0,20, largura mín. 328 | os do robô |
| 2 | `atr_compressao` | ATR14 atual / ATR14 de 40 barras atrás | ≤ 0,60 |
| 3 | `bollinger_squeeze` | largura de banda (20,2) no percentil dos últimos 120 min | ≤ percentil 20 |
| 4 | `razao_amplitude_atr` | amplitude das últimas 20 barras / (ATR14 × √20) | ≤ 1,20 |
| 5 | `nr7_cluster` | fração de barras NR7 (menor amplitude das últimas 7) numa janela de 20 | ≥ 30% |
| 6 | `inside_bar_seq` | fração de barras "inside" (dentro da anterior) numa janela de 20 | ≥ 30% |
| 7 | `volume_secando` | volume médio das últimas 20 barras / volume médio de 40 barras atrás | ≤ 0,70 |

Os limiares de 2-7 são ESCOLHAS, não medições — o objetivo desta rodada é
catalogar e comparar, não otimizar. Ficam registrados aqui para que a
PRÓXIMA rodada possa variá-los sabendo de onde partiu.

Cada definição produz uma bandeira booleana por barra. Bandeiras viram
EVENTOS por sequências de barras contíguas com bandeira=True e duração
mínima de 10 barras (metade de W=20 — "por vários minutos", não 1-2 barras
de ruído). `retangulo_producao` usa a MÁQUINA DE ESTADO do robô (nasce na
detecção, morre na regra de morte já em produção — MARGEM_MORTE=0,25 por
BARRAS_MORTE=3), não o filtro de duração genérico, porque ela já tem morte
própria.

## Regras de medição respeitadas

- Só IS (< 2026-06-13), pregões com ≥400 barras M1 do WIN@.
- `detecta_retangulo` importado de produção, nunca reimplementado.
- ProcessPoolExecutor por DEFINIÇÃO (7 unidades), cada uma imprime sua linha
  ao terminar; a matriz de concordância (que precisa de todas juntas) vem
  depois.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/lateralizacao_catalogo_definicoes_2026_09_16.py`
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

from core.b3_session import SAO_PAULO  # noqa: E402
from core.indicators import atr, bollinger_bands  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import (  # noqa: E402
    BARRAS_MORTE, MARGEM_MORTE, detecta_retangulo)

SIMBOLO = "WIN@"
W = 20
JANELA_PRODUCAO = W  # mesma janela do robô (`janela_barras=20`)
#: `TOLERANCIA_BORDA` do módulo (0,08) é só o FALLBACK histórico da função
#: pura — o robô em produção opera com `tolerancia_borda=0,20` (ver docstring
#: de `WinRetangulo.__init__`). Usar 0,08 aqui mediria um robô que não existe.
TOLERANCIA_PRODUCAO = 0.20
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
MIN_DURACAO_EVENTO = 10  # metade de W — filtra ruído de 1-2 barras

# limiares das definições alternativas (escolhas, documentadas acima)
LIM_ATR_COMPRESSAO = 0.60
LIM_BOLLINGER_PCTL = 0.20
JANELA_BOLLINGER_PCTL = 120
LIM_RAZAO_AMPLITUDE_ATR = 1.20
LIM_NR7_FRACAO = 0.30
LIM_INSIDE_FRACAO = 0.30
LIM_VOLUME_SECANDO = 0.70

LARGURA_MINIMA_PRODUCAO = 328.0  # a do robô win_retangulo, para o detector 1:1


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return "—" if x != x else br(100 * x, 1) + "%"


# --------------------------------------------------------------------------
# construção das bandeiras (causais, por pregão)
# --------------------------------------------------------------------------

def _rolling_pct_rank_last(x: np.ndarray, window: int) -> np.ndarray:
    """Para cada posição i, o percentil (0-1) do valor x[i] DENTRO da janela
    [i-window+1, i] (só passado, causal). NaN nas primeiras `window-1`
    posições."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        janela = x[i - window + 1 : i + 1]
        val = janela[-1]
        if np.isnan(val) or np.isnan(janela).any():
            continue
        out[i] = float(np.mean(janela <= val))
    return out


def flags_alternativas(g: pd.DataFrame) -> dict[str, np.ndarray]:
    """As 6 bandeiras booleanas alternativas, todas causais, para UM pregão."""
    high, low, close = g["high"], g["low"], g["close"]
    vol = g["tick_volume"].astype(float)
    n = len(g)

    atr14 = atr(high, low, close, window=14)
    razao_atr = (atr14 / atr14.shift(40)).to_numpy(float)
    f_atr = razao_atr <= LIM_ATR_COMPRESSAO

    upper, mid, lower = bollinger_bands(close, window=20, k=2.0)
    bandwidth = ((upper - lower) / mid).to_numpy(float)
    pct_rank = _rolling_pct_rank_last(bandwidth, JANELA_BOLLINGER_PCTL)
    f_boll = pct_rank <= LIM_BOLLINGER_PCTL

    amp20 = (high.rolling(20).max() - low.rolling(20).min()).to_numpy(float)
    razao_amp_atr = amp20 / (atr14.to_numpy(float) * np.sqrt(20.0))
    f_amp = razao_amp_atr <= LIM_RAZAO_AMPLITUDE_ATR

    bar_range = (high - low).to_numpy(float)
    is_nr7 = bar_range <= pd.Series(bar_range).rolling(7).min().to_numpy(float) + 1e-9
    frac_nr7 = pd.Series(is_nr7.astype(float)).rolling(20).mean().to_numpy(float)
    f_nr7 = frac_nr7 >= LIM_NR7_FRACAO

    h, l = high.to_numpy(float), low.to_numpy(float)
    is_inside = np.zeros(n, dtype=bool)
    is_inside[1:] = (h[1:] <= h[:-1]) & (l[1:] >= l[:-1])
    frac_inside = pd.Series(is_inside.astype(float)).rolling(20).mean().to_numpy(float)
    f_inside = frac_inside >= LIM_INSIDE_FRACAO

    vol_recente = vol.rolling(20).mean()
    razao_vol = (vol_recente / vol_recente.shift(40)).to_numpy(float)
    f_vol = razao_vol <= LIM_VOLUME_SECANDO

    def _clean(a):
        return np.where(np.isnan(a), False, a)

    return dict(
        atr_compressao=_clean(f_atr),
        bollinger_squeeze=_clean(f_boll),
        razao_amplitude_atr=_clean(f_amp),
        nr7_cluster=_clean(f_nr7),
        inside_bar_seq=_clean(f_inside),
        volume_secando=_clean(f_vol),
    )


def flag_retangulo_producao(g: pd.DataFrame) -> tuple[np.ndarray, list[dict]]:
    """Máquina de estado 1:1 com o robô: nasce na detecção, morre na regra de
    morte de produção. Retorna (bandeira ativa por barra, lista de eventos)."""
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    n = len(g)
    ativo = np.zeros(n, dtype=bool)
    eventos: list[dict] = []
    ret = None
    fora = 0
    nascimento = 0
    i = 3 * JANELA_PRODUCAO
    while i < n:
        if ret is None:
            anterior = float(h[i - 3 * JANELA_PRODUCAO : i - JANELA_PRODUCAO].max()
                             - l[i - 3 * JANELA_PRODUCAO : i - JANELA_PRODUCAO].min())
            r = detecta_retangulo(h[i - JANELA_PRODUCAO:i], l[i - JANELA_PRODUCAO:i],
                                  c[i - JANELA_PRODUCAO:i], anterior,
                                  tolerancia=TOLERANCIA_PRODUCAO)
            if r is not None and r["largura"] >= LARGURA_MINIMA_PRODUCAO:
                ret, fora, nascimento = r, 0, i
                ativo[i] = True
            i += 1
            continue
        ativo[i] = True
        margem = MARGEM_MORTE * ret["largura"]
        fora_da_banda = c[i] > ret["topo"] + margem or c[i] < ret["piso"] - margem
        if fora_da_banda:
            fora += 1
            if fora >= BARRAS_MORTE:
                fim = i - BARRAS_MORTE  # última barra realmente "dentro"
                ativo[fim + 1 : i + 1] = False
                eventos.append(dict(
                    inicio=nascimento, fim=fim, duracao=fim - nascimento + 1,
                    largura=float(ret["largura"]), motivo="morte",
                ))
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    if ret is not None:
        eventos.append(dict(inicio=nascimento, fim=n - 1, duracao=n - nascimento,
                            largura=float(ret["largura"]), motivo="fim_pregao"))
    return ativo, eventos


def segmenta_eventos(flag: np.ndarray, high: np.ndarray, low: np.ndarray,
                     min_duracao: int = MIN_DURACAO_EVENTO) -> list[dict]:
    """Bandeira booleana → lista de eventos (runs contíguos ≥ `min_duracao`)."""
    eventos = []
    n = len(flag)
    i = 0
    while i < n:
        if not flag[i]:
            i += 1
            continue
        j = i
        while j < n and flag[j]:
            j += 1
        duracao = j - i
        if duracao >= min_duracao:
            eventos.append(dict(
                inicio=i, fim=j - 1, duracao=duracao,
                largura=float(high[i:j].max() - low[i:j].min()),
            ))
        i = j
    return eventos


# --------------------------------------------------------------------------
# worker por definição
# --------------------------------------------------------------------------

def processa_definicao(nome: str, dados: dict) -> dict:
    """Roda UMA definição sobre todos os dias do IS. `dados` é
    {dia: (df_do_dia, horas_brt_array)}. Devolve eventos + bandeira completa
    (concatenada na ordem dos dias) para a matriz de concordância depois."""
    buf = StringIO()
    with redirect_stdout(buf):
        todos_eventos: list[dict] = []
        bandeira_completa: list[np.ndarray] = []
        for dia, (g, horas) in dados.items():
            high = g["high"].to_numpy(float)
            low = g["low"].to_numpy(float)
            if nome == "retangulo_producao":
                ativo, eventos = flag_retangulo_producao(g)
            else:
                alt = flags_alternativas(g)
                ativo = alt[nome]
                eventos = segmenta_eventos(ativo, high, low)
            for e in eventos:
                e["dia"] = dia
                e["hora_inicio"] = int(horas[e["inicio"]])
            todos_eventos.extend(eventos)
            bandeira_completa.append(ativo)
        bandeira = np.concatenate(bandeira_completa) if bandeira_completa else np.array([], bool)
    print(buf.getvalue(), end="", flush=True)
    return dict(nome=nome, eventos=todos_eventos, bandeira=bandeira)


def linha_resumo(nome: str, eventos: list[dict], n_dias: int, total_barras: int,
                 horas_sessao: np.ndarray) -> str:
    n = len(eventos)
    if n == 0:
        return f"  {nome:<22} 0 eventos — definição não produziu nenhum evento ≥{MIN_DURACAO_EVENTO} barras"
    dur = np.array([e["duracao"] for e in eventos], float)
    larg = np.array([e["largura"] for e in eventos], float)
    cobertura = sum(e["duracao"] for e in eventos) / total_barras
    horas = np.array([e["hora_inicio"] for e in eventos])
    hora_top, cnt_top = np.unique(horas, return_counts=True)
    pico = hora_top[np.argmax(cnt_top)]
    frac_pico_eventos = cnt_top.max() / n
    frac_pico_sessao = float(np.mean(horas_sessao == pico))
    return (f"  {nome:<22} n={n:>5} ({br(n/n_dias,2):>6}/pregão)  "
            f"duração med {br(float(np.median(dur)),0):>5}b  "
            f"largura med {br(float(np.median(larg)),0):>6}pts  "
            f"cobertura {_pct(cobertura):>6}  "
            f"pico {int(pico):>2}h BRT ({_pct(frac_pico_eventos)} dos eventos "
            f"vs {_pct(frac_pico_sessao)} das barras da sessão)")


def main():
    df = load_m1(SIMBOLO).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, c in cont.items() if c >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    dados: dict = {}
    for d in dias:
        g = df[df.index.date == d]
        if len(g) < 3 * W + 5:
            continue
        horas = g.index.tz_convert(SAO_PAULO).hour.to_numpy()
        dados[d] = (g, horas)
    n_dias = len(dados)
    total_barras = sum(len(g) for g, _ in dados.values())
    horas_sessao = np.concatenate([h for _, h in dados.values()])

    print("=" * 140)
    print("CATÁLOGO DE DEFINIÇÕES DE LATERALIZAÇÃO — WIN@ M1, IS apenas")
    print("=" * 140)
    print(f"  {n_dias} pregões | {dias[0]} a {dias[-1]} | {total_barras} barras totais")
    print(f"  min. duração do evento: {MIN_DURACAO_EVENTO} barras (exceto retângulo, que tem morte própria)")
    print(f"  retângulo: W={JANELA_PRODUCAO}, tol={TOLERANCIA_PRODUCAO}, largura mín={br(LARGURA_MINIMA_PRODUCAO,0)}"
          f" (parâmetros de PRODUÇÃO)\n", flush=True)

    nomes = ["retangulo_producao", "atr_compressao", "bollinger_squeeze",
             "razao_amplitude_atr", "nr7_cluster", "inside_bar_seq", "volume_secando"]

    resultados: dict[str, dict] = {}
    print("-" * 140)
    print("EVENTOS POR DEFINIÇÃO (cada linha sai assim que a unidade termina)")
    print("-" * 140)
    with ProcessPoolExecutor(max_workers=min(7, len(nomes))) as ex:
        futs = {ex.submit(processa_definicao, nome, dados): nome for nome in nomes}
        for fut in as_completed(futs):
            r = fut.result()
            resultados[r["nome"]] = r
            print(linha_resumo(r["nome"], r["eventos"], n_dias, total_barras, horas_sessao), flush=True)

    print("\n" + "=" * 140)
    print("DISTRIBUIÇÃO POR PREGÃO E TAXA DE ROMPIMENTO — retângulo de referência (produção)")
    print("=" * 140)
    ev_ret = resultados["retangulo_producao"]["eventos"]
    por_dia_cnt = {d: 0 for d in dados}
    for e in ev_ret:
        por_dia_cnt[e["dia"]] += 1
    contagens = np.array(list(por_dia_cnt.values()), float)
    dias_zero = int((contagens == 0).sum())
    print(f"  eventos/pregão: mediana {br(float(np.median(contagens)),1)}  "
          f"média {br(float(np.mean(contagens)),2)}  min {int(contagens.min())}  max {int(contagens.max())}  "
          f"NULO (uniforme) seria {br(len(ev_ret)/n_dias,2)} todo dia")
    print(f"  pregões SEM nenhum retângulo: {dias_zero}/{n_dias} ({_pct(dias_zero/n_dias)})")

    dow_evt = np.array([pd.Timestamp(e["dia"]).dayofweek for e in ev_ret])
    dow_dias = np.array([pd.Timestamp(d).dayofweek for d in dados])
    nomes_dow = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    print("\n  por dia da semana (fração dos EVENTOS vs fração dos PREGÕES = nulo):")
    for k in range(5):
        n_evt = int((dow_evt == k).sum())
        n_dia = int((dow_dias == k).sum())
        frac_evt = n_evt / len(ev_ret) if len(ev_ret) else float("nan")
        frac_dia = n_dia / n_dias
        print(f"    {nomes_dow[k]}: {_pct(frac_evt):>7} dos eventos (n={n_evt:>3})  "
              f"vs {_pct(frac_dia):>7} dos pregões (nulo, n={n_dia})")

    n_morte = sum(1 for e in ev_ret if e["motivo"] == "morte")
    n_fim = sum(1 for e in ev_ret if e["motivo"] == "fim_pregao")
    print(f"\n  taxa de rompimento (morte confirmada vs sobreviveu até o fim do pregão):")
    print(f"    morreu por rompimento: {n_morte}/{len(ev_ret)} ({_pct(n_morte/len(ev_ret))})")
    print(f"    NUNCA rompeu (fim de pregão): {n_fim}/{len(ev_ret)} ({_pct(n_fim/len(ev_ret))})")
    print("    -- 'nunca rompeu' é o retângulo que ficou vivo até o fechamento: sob a regra de")
    print("       morte de produção, é o piso da resposta a 'existe lateralização que nunca rompe?'")

    print("\n" + "=" * 140)
    print("MATRIZ DE CONCORDÂNCIA — P(coluna=lateral | linha=lateral), barra a barra, todo o IS")
    print("=" * 140)
    print("  NULO de cada célula: a fração de barras que a definição da COLUNA marca como lateral")
    print("  no IS inteiro (concordância por acaso, se as duas fossem independentes).\n")
    tamanhos = {n: len(resultados[n]["bandeira"]) for n in nomes}
    assert len(set(tamanhos.values())) == 1, f"bandeiras de tamanhos diferentes: {tamanhos}"
    bandeiras = {n: resultados[n]["bandeira"] for n in nomes}
    cobertura_marginal = {n: float(bandeiras[n].mean()) for n in nomes}

    header = "  " + " " * 24 + "".join(f"{n[:12]:>14}" for n in nomes)
    print(header)
    for linha in nomes:
        b_linha = bandeiras[linha]
        n_linha = int(b_linha.sum())
        vals = []
        for col in nomes:
            if n_linha == 0:
                vals.append(float("nan"))
                continue
            vals.append(float((b_linha & bandeiras[col]).sum()) / n_linha)
        print(f"  {linha:<24}" + "".join(f"{_pct(v):>14}" for v in vals))
    print("\n  NULO por coluna (fração da coluna que é lateral, no IS inteiro):")
    print("  " + " " * 24 + "".join(f"{_pct(cobertura_marginal[n]):>14}" for n in nomes))

    print("\n" + "=" * 140)
    print("COMO LER")
    print("=" * 140)
    print("  * Todas as bandeiras são CAUSAIS (só olham para trás) — não há look-ahead aqui.")
    print("  * Os limiares de 2-7 são ESCOLHAS documentadas na docstring, não medições: esta")
    print("    rodada cataloga e compara, a calibração fina é agenda futura.")
    print("  * 'cobertura' é a fração do tempo de sessão em que a definição está ATIVA — compare")
    print("    contra o retângulo antes de tratar qualquer definição como rara ou frequente.")
    print("  * A matriz de concordância lê-se por LINHA: 'dado que X está ativo, Y também está em Z%'.")
    print("  * Só o IS. A janela cega fica intacta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
