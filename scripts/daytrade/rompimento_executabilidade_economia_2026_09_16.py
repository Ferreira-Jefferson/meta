# -*- coding: utf-8 -*-
"""ROMPIMENTO de retângulo: EXECUTABILIDADE e ECONOMIA sob o desenho de
execução fechado -- não é território de definição/anatomia (isso é de outros
agentes desta rodada); aqui a pergunta é "dado que o retângulo rompe, existe
alguma forma de OPERAR isso que a corretora aceite, e ela sobra depois do
pedágio?"

## Ponto de partida: reusa a MESMA população de `rompimento_retangulo_
## fenomeno_2026_09_16.py` (não redefine retângulo nem rompimento)

Retângulo: `detecta_retangulo` de PRODUÇÃO (`strategy.daytrade.lab.
win_retangulo`), W=20, tolerância 0,20, largura mínima 328 pontos. Rompimento:
a mesma regra de MORTE que o robô de fade já usa -- fechamento além da borda
+ 25% da largura (`MARGEM_MORTE`) por 3 barras (`BARRAS_MORTE`). Confirmado
neste script (`scratch/rompimento_fenomeno_baseline_2026_09_16.log`): 417
rompimentos, 129 pregões IS, 3,2/pregão -- os MESMOS números do fenômeno.

## A enumeração exaustiva das formas -- feita ANTES de medir, não depois

O desenho de execução é FECHADO (CLAUDE.md): entrada só por `EnterLimit`
(nunca `Enter`, que levanta `EntradaAMercadoNaoSuportada` de propósito --
`src/backtest/intraday/machine.py:70,1233`); alvo só por ordem-limite real;
só o stop é a mercado. `IntradayAction = Union[Enter, EnterLimit, Exit,
AdjustStop, AdjustTarget]` (`src/strategy/daytrade/base.py`) -- **não existe
ordem STOP-DE-ENTRADA** (buy-stop/sell-stop, que dispara a mercado quando o
preço TOCA um nível). Isso não é lacuna de parametrização, é ausência de tipo
de ação no motor inteiro.

Uma ordem-limite de COMPRA só descansa ABAIXO do preço corrente; uma de
VENDA só ACIMA (é a conferência mecânica que `WinRetangulo`/`WdoRetangulo` já
fazem antes de armar: `if lado=="short" and limite<=bar.close: return []` /
`if lado=="long" and limite>=bar.close: return []`). Rompimento é o preço
INDO EMBORA do nível na direção da continuação -- logo qualquer forma que
tente "comprar mais alto" ou "vender mais baixo" para CAPTURAR a continuação
exige um preço-limite do lado ERRADO no instante em que seria armada, e o
próprio motor a rejeitaria (ou, sem a conferência, ela preencheria na hora
seguinte como taker disfarçado de maker -- pior ainda).

Formas enumeradas, com veredito:

| # | forma | executável? | motivo mecânico |
|---|---|---|---|
| A1 | Retest COMPLETO na borda rompida (limite no nível, mirando a continuação) | **SIM** | limite fica do lado certo: após romper para cima, borda < preço corrente -> compra abaixo; após romper para baixo, borda > preço corrente -> venda acima |
| A2 | Retorno PARCIAL (limite num nível de retração entre o preço de detecção e a borda, ex. 50%) | **SIM** | mesmo lado que A1, nível ainda mais conservador (mais perto do preço corrente) |
| A3 | Escada de limites em várias profundidades de retração | **SIM em princípio** | cada degrau é individualmente uma A1/A2; não medida nesta rodada (ver "perguntas abertas") |
| B | Perseguir o rompimento -- limite MAIS LONGE na direção da continuação, à frente do preço | **NÃO** | exige compra ACIMA do preço corrente (alta) ou venda ABAIXO (baixa) -- não existe tipo de ação para isso (nem `Enter` nem `EnterLimit` cobrem; seria uma ordem STOP, ausente do motor) |
| C | Reancorar a limite a cada barra, colada 1 tick atrás do preço, perseguindo a extensão | **MECANICAMENTE sim, estruturalmente NÃO** | válida a cada instante (sempre do lado certo), mas degenera: preenche na primeira reversão de 1 tick -- é ordem a mercado disfarçada de limite, mesmo pecado que o T1 do WDO F1 (proibido por precedente) |
| D | Entrada a mercado no instante do rompimento, ou alvo a mercado | **NÃO** | proibido pelo desenho fechado (`EntradaAMercadoNaoSuportada`; TP nativo desliza 57,9%) |
| E | Entrada na borda OPOSTA (fade completo através do retângulo) | **fora de escopo** | não é rompimento -- é a estratégia IRMÃ já em produção/sombra (`win_retangulo`/`wdo_retangulo`), que entra no MEIO mirando a borda oposta |

Esta rodada mede A1 e A2. B, C, D e E ficam LISTADAS e descartadas pelo
motivo acima -- para ninguém as redescobrir daqui a um mês.

## Regras de medição

Só IS (<2026-06-13), 129 pregões, `MIN_BARRAS_POR_PREGAO=400`. WIN@ M1 real
(`feed_kind="m1"`): 1 barra = 1 minuto EXATO, sem a armadilha de tick-como-
barra-degenerada do WDO (`ttl_bars` aqui já É tempo, não precisa calibração).

Este script mede diretamente da série (MFE/MAE, ordem de chegada, revisitas)
-- não roda o motor de backtest completo (`backtest/intraday/engine.py`)
porque a pergunta desta rodada é sobre o preço em si (existe caminho de
preenchimento? Sobra economia?), não sobre P&L de carteira com dimensionamento
de caixa -- mesmo espírito de `rompimento_retangulo_fenomeno_2026_09_16.py`.
Por isso os números aqui são POR OPERAÇÃO, 1 contrato, sem o portão de caixa
do motor -- e a seção de piso de capital abaixo é o que reconecta isso com o
caixa mínimo real.

WIN@ não tem `queue_ahead_qty`/`exit_queue_ahead_qty` calibrados em
`backtest/intraday/fidelidade.py` (só WDO@ tem) -- todo preenchimento aqui
assume TOQUE, dos dois lados, que é a MESMA premissa otimista que o motor
usa hoje para o WIN@ (não é um viés introduzido por este script; é o estado
da arte do projeto para este símbolo). A seção de FILA abaixo é a checagem
qualitativa/quantitativa que substitui a calibração ausente.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/rompimento_executabilidade_economia_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA = 0.20
LARGURA_MINIMA = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
PEDAGIO_PONTOS = 7.5
PONTO_BRL = 0.20            # core.instruments.economics_for("WIN@").point_value_brl
TICK = 5.0                  # core.instruments.economics_for("WIN@").price_tick_size
MARGEM_BRL = 100.0          # core.instruments.economics_for("WIN@").margin_per_contract_brl
HORIZONTE_RETESTE = 400     # bem além de qualquer ttl candidato -- praticamente "até o fim do pregão"
HORIZONTE_ECONOMIA = 120    # janela para MFE/MAE e ordem de chegada após o fill
HORIZONTE_REVISITA = 60     # janela de revisita do nível (proxy de fila), mesma do fenômeno
TTL_CANDIDATOS = (5, 10, 15, 20, 30, 45, 60, 90, 120)
LIMIARES_ABSOLUTOS = (20.0, 40.0, 60.0, 100.0, 150.0, 200.0, 300.0)
RETRACAO_PARCIAL = 0.50      # A2: 50% do caminho entre o preço de detecção e a borda


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "-"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, dec=1):
    return "-" if x != x else br(100 * x, dec) + "%"


# ---------------------------------------------------------------------------
# Detecção -- reusa a função pura de produção, não reimplementa
# ---------------------------------------------------------------------------

def _rectangulos_e_rompimentos(g: pd.DataFrame):
    """Varre um pregão UMA vez, devolvendo (retangulos_todos, rompimentos).

    `retangulos_todos`: todo retângulo validado que nasceu no pregão, com
    `meio`/`largura`/idx de nascimento e de fim (morte por rompimento ou fim
    do pregão) -- usado só para a comparação de FILA (revisitas ao meio).

    `rompimentos`: mesmo evento de `rompimento_retangulo_fenomeno_2026_09_16.
    rompimentos_do_pregao` (idêntico critério), com `meio` adicionado (dedu-
    zido de borda+largura+lado, sem reabrir o detector)."""
    from strategy.daytrade.lab.win_retangulo import (BARRAS_MORTE,
                                                      MARGEM_MORTE,
                                                      detecta_retangulo)
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    n = len(g)
    retangulos: list[dict] = []
    rompimentos: list[dict] = []
    ret = None
    fora = 0
    nascimento = 0
    i = 3 * JANELA
    while i < n:
        if ret is None:
            anterior = float(h[i - 3 * JANELA:i - JANELA].max()
                             - l[i - 3 * JANELA:i - JANELA].min())
            r = detecta_retangulo(h[i - JANELA:i], l[i - JANELA:i], c[i - JANELA:i],
                                  anterior, tolerancia=TOLERANCIA)
            if r is not None and r["largura"] >= LARGURA_MINIMA:
                ret, fora, nascimento = r, 0, i
                retangulos.append(dict(meio=r["meio"], largura=r["largura"],
                                        idx_nascimento=i))
            i += 1
            continue
        margem = MARGEM_MORTE * ret["largura"]
        acima = c[i] > ret["topo"] + margem
        abaixo = c[i] < ret["piso"] - margem
        if acima or abaixo:
            fora += 1
            if fora >= BARRAS_MORTE:
                lado = "alta" if acima else "baixa"
                borda = float(ret["topo"] if acima else ret["piso"])
                largura = float(ret["largura"])
                meio = borda - largura / 2.0 if lado == "alta" else borda + largura / 2.0
                rompimentos.append(dict(
                    idx=i, lado=lado, borda=borda, largura=largura, meio=meio,
                    barras_vivo=i - nascimento, preco_deteccao=float(c[i]),
                    idx_nascimento=nascimento,
                ))
                retangulos[-1]["idx_fim"] = i
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    if ret is not None:
        retangulos[-1]["idx_fim"] = n - 1
    for r in retangulos:
        r.setdefault("idx_fim", n - 1)
    return retangulos, rompimentos


def _tempo_ate_toque(h, l, idx, referencia, lado, horizonte):
    """Índice (1-based, em barras após `idx`) do primeiro toque de
    `referencia`, ou `None` se não tocar dentro do horizonte/pregão."""
    fim = min(idx + 1 + horizonte, len(h))
    if fim <= idx + 1:
        return None
    if lado == "alta":
        tocou = np.where(l[idx + 1:fim] <= referencia)[0]
    else:
        tocou = np.where(h[idx + 1:fim] >= referencia)[0]
    return int(tocou[0] + 1) if len(tocou) else None


def _excursao_pos_fill(h, l, idx_fill, referencia, lado, horizonte):
    """MFE/MAE a partir de `referencia` (o preço de FILL), na direção da
    CONTINUAÇÃO do rompimento, olhando `horizonte` barras à frente do fill."""
    fim = min(idx_fill + 1 + horizonte, len(h))
    if fim <= idx_fill + 1:
        return None
    hh, ll = h[idx_fill + 1:fim], l[idx_fill + 1:fim]
    if lado == "alta":
        return dict(mfe=float(hh.max() - referencia), mae=float(referencia - ll.min()))
    return dict(mfe=float(referencia - ll.min()), mae=float(hh.max() - referencia))


def _ordem_chegada(h, l, idx_fill, referencia, lado, alvo_pts, stop_pts, horizonte):
    """`True` se o ALVO (a favor) é tocado antes do STOP (contra); `False` se
    o contrário; `None` se nenhum dos dois nos `horizonte` barras seguintes ao
    fill. `alvo_pts`/`stop_pts` sempre positivos, medidos a partir de
    `referencia` na direção da continuação (alvo) e da reversão (stop)."""
    fim = min(idx_fill + 1 + horizonte, len(h))
    if fim <= idx_fill + 1:
        return None
    hh, ll = h[idx_fill + 1:fim], l[idx_fill + 1:fim]
    if lado == "alta":
        favor = np.where(hh >= referencia + alvo_pts)[0]
        contra = np.where(ll <= referencia - stop_pts)[0]
    else:
        favor = np.where(ll <= referencia - alvo_pts)[0]
        contra = np.where(hh >= referencia + stop_pts)[0]
    if not len(favor) and not len(contra):
        return None
    if not len(contra):
        return True
    if not len(favor):
        return False
    return bool(favor[0] < contra[0])


def _revisitas(h, l, idx_inicio, referencia, horizonte, excluir_primeira=False):
    """Quantas barras distintas, nas `horizonte` seguintes a `idx_inicio`,
    tocam `referencia` (proxy de volume/fila no nível -- nível muito visitado
    é nível barato de fila, achado do `win_retangulo`). `excluir_primeira`
    pula a própria barra de fill (que por definição toca)."""
    fim = min(idx_inicio + 1 + horizonte, len(h))
    ini = idx_inicio + 1
    if fim <= ini:
        return 0
    toques = (l[ini:fim] <= referencia) & (h[ini:fim] >= referencia)
    return int(toques.sum())


# ---------------------------------------------------------------------------
# Unidade de trabalho: um pregão
# ---------------------------------------------------------------------------

def processa_dia(args):
    dia_str, dados = args
    sys.path.insert(0, str(ROOT / "src"))
    g = pd.DataFrame(dados)
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)

    retangulos, rompimentos = _rectangulos_e_rompimentos(g)

    linhas_evt = []
    for r in rompimentos:
        idx, lado, borda, largura, meio = (r["idx"], r["lado"], r["borda"],
                                            r["largura"], r["meio"])
        preco_det = r["preco_deteccao"]

        # -- A1: retest completo na borda --------------------------------
        t_a1 = _tempo_ate_toque(h, l, idx, borda, lado, HORIZONTE_RETESTE)
        linha = dict(dia=dia_str, lado=lado, borda=borda, largura=largura,
                     meio=meio, idx=idx, preco_deteccao=preco_det,
                     forma="A1_retest_completo", delay_min=t_a1,
                     preenche=t_a1 is not None)
        if t_a1 is not None:
            idx_fill = idx + t_a1
            linha["revisitas_pos_fill"] = _revisitas(
                h, l, idx_fill, borda, HORIZONTE_REVISITA)
            exc = _excursao_pos_fill(h, l, idx_fill, borda, lado, HORIZONTE_ECONOMIA)
            if exc is not None:
                linha["mfe"], linha["mae"] = exc["mfe"], exc["mae"]
            for t in LIMIARES_ABSOLUTOS:
                linha[f"chega_{int(t)}"] = _ordem_chegada(
                    h, l, idx_fill, borda, lado, t, t, HORIZONTE_ECONOMIA)
            # geometria herdada da família (alvo 0,80L além da borda / stop
            # 0,50L de volta pelo retângulo) e uma variante simétrica 0,50L/0,50L
            linha["chega_geo_80_50"] = _ordem_chegada(
                h, l, idx_fill, borda, lado, 0.80 * largura, 0.50 * largura,
                HORIZONTE_ECONOMIA)
            linha["chega_geo_50_50"] = _ordem_chegada(
                h, l, idx_fill, borda, lado, 0.50 * largura, 0.50 * largura,
                HORIZONTE_ECONOMIA)
        linhas_evt.append(linha)

        # -- A2: retorno parcial (50% do caminho detecção -> borda) -------
        if lado == "alta":
            ref_a2 = preco_det - RETRACAO_PARCIAL * (preco_det - borda)
        else:
            ref_a2 = preco_det + RETRACAO_PARCIAL * (borda - preco_det)
        t_a2 = _tempo_ate_toque(h, l, idx, ref_a2, lado, HORIZONTE_RETESTE)
        linha2 = dict(dia=dia_str, lado=lado, borda=borda, largura=largura,
                      meio=meio, idx=idx, preco_deteccao=preco_det,
                      forma="A2_retorno_parcial", delay_min=t_a2,
                      preenche=t_a2 is not None, referencia=ref_a2)
        if t_a2 is not None:
            idx_fill = idx + t_a2
            linha2["revisitas_pos_fill"] = _revisitas(
                h, l, idx_fill, ref_a2, HORIZONTE_REVISITA)
            for t in LIMIARES_ABSOLUTOS:
                linha2[f"chega_{int(t)}"] = _ordem_chegada(
                    h, l, idx_fill, ref_a2, lado, t, t, HORIZONTE_ECONOMIA)
            linha2["chega_geo_80_50"] = _ordem_chegada(
                h, l, idx_fill, ref_a2, lado, 0.80 * largura, 0.50 * largura,
                HORIZONTE_ECONOMIA)
        linhas_evt.append(linha2)

    linhas_ret = []
    for r in retangulos:
        rev = _revisitas(h, l, r["idx_nascimento"], r["meio"], HORIZONTE_REVISITA)
        linhas_ret.append(dict(dia=dia_str, meio=r["meio"], largura=r["largura"],
                                idx_nascimento=r["idx_nascimento"],
                                revisitas_meio=rev))

    return linhas_evt, linhas_ret, len(rompimentos)


def main():
    from market_data_intraday.storage import load_m1

    df = load_m1(SIMBOLO).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, n in cont.items()
                  if n >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 148)
    print("ROMPIMENTO DE RETÂNGULO -- EXECUTABILIDADE e ECONOMIA sob o desenho fechado")
    print("=" * 148)
    print(f"  {SIMBOLO} M1 | {len(dias)} pregões | {dias[0]} a {dias[-1]} | IS apenas")
    print(f"  retângulo W={JANELA}, tolerância {TOLERANCIA}, largura mínima {br(LARGURA_MINIMA,0)}")
    print(f"  pedágio ida-e-volta {br(PEDAGIO_PONTOS,1)} pontos = "
          f"R$ {br(PEDAGIO_PONTOS*PONTO_BRL,2)}/contrato | margem crua R$ {br(MARGEM_BRL,2)}")
    print(f"  horizonte reteste {HORIZONTE_RETESTE} barras (~fim do pregão) | "
          f"horizonte economia {HORIZONTE_ECONOMIA} barras | horizonte revisita {HORIZONTE_REVISITA} barras\n",
          flush=True)

    tarefas = [(str(d), df[df.index.date == d][["high", "low", "close"]].to_dict("list"))
               for d in dias if len(df[df.index.date == d]) >= 3 * JANELA + 5]

    todas_evt: list[dict] = []
    todas_ret: list[dict] = []
    total_rompimentos = 0
    concluidos = 0
    with ProcessPoolExecutor() as ex:
        futuros = {ex.submit(processa_dia, t): t[0] for t in tarefas}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            try:
                linhas_evt, linhas_ret, n_romp = fut.result()
            except Exception as e:  # nao deixa 1 pregao derrubar a rodada
                print(f"  [ERRO] {dia}: {e}", flush=True)
                continue
            todas_evt.extend(linhas_evt)
            todas_ret.extend(linhas_ret)
            total_rompimentos += n_romp
            concluidos += 1
            print(f"  [{concluidos:>3}/{len(tarefas)}] {dia}: "
                  f"{n_romp} rompimento(s), {len(linhas_ret)} retângulo(s)", flush=True)

    print(f"\n  total: {total_rompimentos} rompimentos "
          f"({br(total_rompimentos/len(dias),1)}/pregão) -- deve bater com o fenômeno (417, 3,2/pregão)")

    # ======================================================================
    print("\n" + "=" * 148)
    print("(B) PRAZO (ttl_bars=minutos, feed M1) -- taxa de PREENCHIMENTO e ATRASO REALIZADO, por FORMA")
    print("=" * 148)
    for forma in ("A1_retest_completo", "A2_retorno_parcial"):
        evs = [e for e in todas_evt if e["forma"] == forma]
        delays = np.array([e["delay_min"] for e in evs if e["delay_min"] is not None], float)
        n = len(evs)
        print(f"\n  -- {forma} (n={n} rompimentos elegíveis) --")
        print(f"     nunca preenche até o fim do pregão: {pct(1 - len(delays)/n)} ({n-len(delays)} de {n})")
        if len(delays):
            print(f"     atraso entre os que preenchem: mediana {br(float(np.median(delays)),0)} min "
                  f"(p10 {br(float(np.percentile(delays,10)),0)}, p90 {br(float(np.percentile(delays,90)),0)})")
        print(f"     {'ttl (min)':<12}{'preenche%':>12}{'atraso mediano':>17}{'atraso p90':>13}")
        for ttl in TTL_CANDIDATOS:
            sub = delays[delays <= ttl]
            taxa = len(sub) / n
            med = float(np.median(sub)) if len(sub) else float("nan")
            p90 = float(np.percentile(sub, 90)) if len(sub) else float("nan")
            print(f"     {str(ttl)+' min':<12}{pct(taxa):>12}{br(med,1)+' min':>17}{br(p90,1)+' min':>13}")

    # ======================================================================
    print("\n" + "=" * 148)
    print("(C) ECONOMIA CRUA CONTRA O PEDÁGIO -- só operações PREENCHIDAS (A1, retest completo)")
    print("=" * 148)
    a1 = [e for e in todas_evt if e["forma"] == "A1_retest_completo" and e["preenche"]]
    print(f"  n={len(a1)} entradas preenchidas de {sum(1 for e in todas_evt if e['forma']=='A1_retest_completo')} rompimentos\n")
    print(f"  {'geometria (alvo/stop)':<28}{'n decidido':>11}{'win%':>9}{'breakeven nom.':>16}"
          f"{'R$/op (bruto)':>16}{'R$/op (líq. pedágio)':>22}")
    for chave, alvo_r, stop_r, rotulo in [
        ("chega_geo_50_50", 0.50, 0.50, "0,50L / 0,50L"),
        ("chega_geo_80_50", 0.80, 0.50, "0,80L / 0,50L (herdada)"),
    ]:
        decs = []
        for e in a1:
            v = e.get(chave)
            if v is None:
                continue
            alvo_pts = alvo_r * e["largura"]
            stop_pts = stop_r * e["largura"]
            decs.append((v, alvo_pts, stop_pts))
        n_dec = len(decs)
        if n_dec == 0:
            continue
        wins = sum(1 for v, _, _ in decs if v)
        winp = wins / n_dec
        be = stop_r / (alvo_r + stop_r)
        bruto = np.mean([(a if v else -s) for v, a, s in decs])
        liq = bruto * PONTO_BRL - PEDAGIO_PONTOS * PONTO_BRL
        print(f"  {rotulo:<28}{n_dec:>11}{pct(winp):>9}{pct(be):>16}"
              f"{br(bruto,1)+' pts':>16}{'R$ '+br(liq,2):>22}")

    print(f"\n  {'limiar simétrico':<28}{'n decidido':>11}{'win%':>9}{'R$/op (líq. pedágio)':>22}")
    for t in LIMIARES_ABSOLUTOS:
        vs = [e[f"chega_{int(t)}"] for e in a1 if e.get(f"chega_{int(t)}") is not None]
        if not vs:
            continue
        wins = sum(1 for v in vs if v)
        winp = wins / len(vs)
        bruto = np.mean([(t if v else -t) for v in vs])
        liq = bruto * PONTO_BRL - PEDAGIO_PONTOS * PONTO_BRL
        print(f"  {br(t,0)+' pts (sim.)':<28}{len(vs):>11}{pct(winp):>9}{'R$ '+br(liq,2):>22}")

    print("\n  -- A2 (retorno parcial 50%), geometria herdada 0,80L/0,50L a partir DA MESMA borda --")
    a2 = [e for e in todas_evt if e["forma"] == "A2_retorno_parcial" and e["preenche"]]
    vs2 = [e["chega_geo_80_50"] for e in a2 if e.get("chega_geo_80_50") is not None]
    if vs2:
        wins2 = sum(1 for v in vs2 if v)
        winp2 = wins2 / len(vs2)
        bruto2 = np.mean([(0.80 * e["largura"] if v else -0.50 * e["largura"])
                          for e, v in zip((x for x in a2 if x.get("chega_geo_80_50") is not None), vs2)])
        liq2 = bruto2 * PONTO_BRL - PEDAGIO_PONTOS * PONTO_BRL
        print(f"     n decidido={len(vs2)}  win%={pct(winp2)}  breakeven nom.={pct(0.50/1.30)}  "
              f"R$/op líq.=R$ {br(liq2,2)}  (entrada mais rasa -> alvo/stop maiores em pontos "
              f"a partir de um ponto de referência mais frágil)")

    # ======================================================================
    print("\n" + "=" * 148)
    print("(D) FILA -- quantas vezes o preço REVISITA o nível de entrada DEPOIS do fill (proxy de fila)")
    print("=" * 148)
    revs_borda = np.array([e["revisitas_pos_fill"] for e in a1 if "revisitas_pos_fill" in e], float)
    revs_meio = np.array([r["revisitas_meio"] for r in todas_ret], float)
    print(f"  BORDA rompida (romper-e-retestar, n={len(revs_borda)}): "
          f"mediana {br(float(np.median(revs_borda)) if len(revs_borda) else float('nan'),1)} revisitas "
          f"em {HORIZONTE_REVISITA} barras seguintes ao fill "
          f"(p10 {br(float(np.percentile(revs_borda,10)) if len(revs_borda) else float('nan'),1)}, "
          f"p90 {br(float(np.percentile(revs_borda,90)) if len(revs_borda) else float('nan'),1)})")
    print(f"  MEIO do retângulo (win_retangulo, n={len(revs_meio)}): "
          f"mediana {br(float(np.median(revs_meio)) if len(revs_meio) else float('nan'),1)} revisitas "
          f"em {HORIZONTE_REVISITA} barras seguintes ao nascimento "
          f"(p10 {br(float(np.percentile(revs_meio,10)) if len(revs_meio) else float('nan'),1)}, "
          f"p90 {br(float(np.percentile(revs_meio,90)) if len(revs_meio) else float('nan'),1)})")
    if len(revs_borda) and len(revs_meio):
        zero_borda = float(np.mean(revs_borda == 0))
        zero_meio = float(np.mean(revs_meio == 0))
        print(f"  fração com ZERO revisitas (nível visitado 1x e o preço vai embora): "
              f"borda {pct(zero_borda)}  |  meio {pct(zero_meio)}")

    # ======================================================================
    print("\n" + "=" * 148)
    print("(E) PISO DE CAPITAL -- pior rebaixamento POR OPERAÇÃO + margem crua")
    print("=" * 148)
    for chave, alvo_r, stop_r, rotulo in [
        ("chega_geo_50_50", 0.50, 0.50, "0,50L / 0,50L"),
        ("chega_geo_80_50", 0.80, 0.50, "0,80L / 0,50L (herdada)"),
    ]:
        piores = []
        for e in a1:
            v = e.get(chave)
            if v is None:
                continue
            stop_pts = stop_r * e["largura"]
            if not v:
                piores.append(stop_pts * PONTO_BRL)
        pior = max(piores) if piores else float("nan")
        print(f"  {rotulo:<28}pior perda medida R$ {br(pior,2):>10}  ->  "
              f"piso sugerido R$ {br(pior + MARGEM_BRL,2)} (perda + margem R$ {br(MARGEM_BRL,0)})")

    print("\n" + "=" * 148)
    print("COMO LER")
    print("=" * 148)
    print("  * Só as formas A1/A2 são executáveis (ver enumeração no topo do arquivo); B/C/D estão")
    print("    mecanicamente descartadas e D é regra explícita do projeto.")
    print("  * (C) usa só as entradas que PREENCHERAM -- taxa de preenchimento está em (B), não aqui;")
    print("    não confundir R$/op (que já é condicional a preencher) com R$/pregão (que precisa de (B)).")
    print("  * Nenhum custo de fila foi cobrado (WIN@ não tem fidelidade.py calibrada) -- (D) é a")
    print("    checagem qualitativa que substitui a calibração ausente.")
    print("  * Só o IS. A janela cega fica intacta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
