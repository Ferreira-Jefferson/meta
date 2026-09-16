# -*- coding: utf-8 -*-
"""WIN@ retangulo: a MATRIZ inteira de alvo x stop, e os alvos DINAMICOS.

Perguntas do dono (2026-09-15): "eu passei 90%, mas sera que o ideal seria um
percentual menor? Ou talvez posicionar o alvo com base no que o mercado nos da
como sinal apos a ordem ter sido aceita? Crie outros testes e verificacoes."

## A previsao que este script tenta FALSIFICAR

A grade de estrategias (`copawin_retangulo_estrategias_2026_09_15.py`) mostrou
o win% caindo praticamente EM CIMA do breakeven empirico em toda celula:
centro W30 stop0,50 -> 53,8% contra 54,0%; centro W60 stop0,25 -> 37,1% contra
37,6%; falso W60 stop0,50 -> 28,5% contra 28,5%. Isso e' a assinatura de JOGO
JUSTO: dentro do retangulo o preco entre os niveis se comporta como passeio
aleatorio, e mexer em alvo/stop so' desloca o par (acerto, payoff) ao longo da
MESMA curva de expectativa zero.

Se isso for verdade, a matriz inteira de alvo x stop e' plana no zero (menos o
custo) e NAO existe percentual ideal a achar -- nem 90%, nem 50%, nem nenhum.
Se for falso, existe uma regiao da matriz onde o acerto DESCOLA do breakeven, e
essa regiao e' o achado.

E' uma previsao arriscada e e' o ponto do script. Varrer fino serve justamente
para ela poder morrer.

## Por que trajetoria, e nao mais backtests

Rodar a grade de geometrias como backtests separados custa uma rodada por
celula e mede cada uma num caminho diferente. Aqui cada ENTRADA e' gravada uma
vez com a trajetoria inteira do preco depois dela; toda combinacao de alvo e
stop e' entao avaliada SOBRE AS MESMAS trajetorias. Uma passada, matriz
inteira, e as celulas ficam comparaveis entre si por construcao.

## Geracao de eventos (causal)

Detector rodando barra a barra (mesma `_avalia_janela` do detector original,
mesmo criterio de morte tolerante). Enquanto o retangulo vive:

  modo CENTRO: ordem-limite no meio, do lado que descansa corretamente
               (venda se o preco esta ABAIXO do meio; compra se acima)
  modo BORDA : ordem-limite na borda da metade em que o preco esta
               (venda no topo; compra no piso)

Preenchimento quando uma barra POSTERIOR toca o nivel, dentro do prazo. Depois
do fill, grava-se a trajetoria (maxima, minima e fechamento de cada barra,
relativos ao preco de entrada, com o sinal do lado, normalizados pela largura
L do retangulo) ate a morte do retangulo ou o teto de barras.

ATENCAO -- OS EVENTOS SE SOBREPOEM. Para nao amarrar a geracao a uma geometria
especifica (o proximo evento so' comecaria depois de o anterior sair, e "sair"
depende do alvo escolhido -- circular), os eventos sao gerados com um intervalo
minimo de `COOLDOWN` barras e podem se sobrepor. Consequencia: os n NAO sao
observacoes independentes e os IC saem estreitos demais. Isto responde "existe
edge nesta geometria?", nao "quanto renderia o robo" -- essa segunda pergunta
exige sequenciamento, e so' vale a pena se a primeira der SIM.

## As duas armadilhas obrigatorias

1. Barra M1 nao diz se a maxima veio antes da minima. Quando alvo e stop caem
   na MESMA barra, conta como STOP (pessimista).
2. Custo: 7,5 pontos por round trip (1,5 tick do WIN), descontado de TODO
   resultado. Um alvo pequeno em fracao de L pode ficar abaixo disso -- a
   tabela marca as celulas em que o alvo bruto nao paga o pedagio.

## Os alvos DINAMICOS (a segunda pergunta do dono)

Avaliados nas MESMAS trajetorias, todos com stop fixo por baixo:

  D-TEMPO   sai a mercado se o alvo nao veio em M barras
  D-RECUO   sai quando a excursao favoravel recua X% do proprio pico
            (trailing de LUCRO, nao de stop)
  D-EXAUSTAO sai na primeira barra que fecha CONTRA o lado, ja com lucro >= y
  D-DEIXA   alvo na borda, mas se o preco ROMPER a borda deixa correr com
            trailing de recuo (captura o rompimento em vez de sair nele)

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_matriz_alvo_stop_2026_09_15.py`
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


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_mx")
_det = _carrega("copawin_retangulo_lateral_2026_09_15.py", "_det_mx")

SCRATCH = ROOT / "scratch"
CORTE_OOS = pd.Timestamp("2026-06-13").date()
TICK = 5.0
CUSTO_PONTOS = 7.5          # round trip do WIN: tarifa 2,5 + 1 tick de slippage
MARGEM_MORTE, BARRAS_MORTE = 0.25, 3
TTL_BARRAS = 10             # prazo da ordem-limite de entrada
COOLDOWN = 5                # barras minimas entre dois eventos do mesmo modo
MAX_BARRAS_TRAJ = 120       # teto da trajetoria gravada

JANELAS_W = (30, 60)
#: grade de alvo e stop, em fracao da LARGURA do retangulo, medida a partir do
#: preco de ENTRADA. No modo centro a borda oposta esta a 0,5L; no modo borda,
#: a borda oposta esta a 1,0L.
ALVOS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
         0.60, 0.70, 0.80, 0.90, 1.00)
STOPS = (0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 0.75)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# geracao de eventos
# ---------------------------------------------------------------------------

def roda_dia(args):
    dia, W, modo = args
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if len(b) < 3 * W + 10:
        return []
    hi = b["high"].to_numpy(float)
    lo = b["low"].to_numpy(float)
    cl = b["close"].to_numpy(float)
    n = len(cl)

    eventos = []
    ret = None
    fora = 0
    ultimo_evento = -10 ** 9

    for t in range(3 * W, n - 2):
        if ret is not None:
            L = ret["largura"]
            if cl[t] > ret["topo"] + MARGEM_MORTE * L or cl[t] < ret["piso"] - MARGEM_MORTE * L:
                fora += 1
                if fora >= BARRAS_MORTE:
                    ret, fora = None, 0
            else:
                fora = 0
        if ret is None:
            range_antes = float(hi[t - 3 * W:t - W + 1].max() - lo[t - 3 * W:t - W + 1].min())
            cand = _det._avalia_janela(hi[t - W + 1:t + 1], lo[t - W + 1:t + 1],
                                       cl[t - W + 1:t + 1], range_antes)
            if cand is None or cand["largura"] < _det.LARGURA_MIN_TICKS * TICK:
                continue
            ret = cand
            fora = 0
            continue

        if t - ultimo_evento < COOLDOWN:
            continue

        topo, piso, meio, L = ret["topo"], ret["piso"], ret["meio"], ret["largura"]
        if modo == "centro":
            nivel = meio
            lado = -1 if cl[t] < meio else (1 if cl[t] > meio else 0)
        else:
            if cl[t] > meio and cl[t] < topo:
                nivel, lado = topo, -1
            elif cl[t] < meio and cl[t] > piso:
                nivel, lado = piso, 1
            else:
                continue
        if lado == 0:
            continue
        # a limite tem de descansar do lado certo do preco
        if lado < 0 and nivel <= cl[t]:
            continue
        if lado > 0 and nivel >= cl[t]:
            continue

        # preenchimento: primeira barra POSTERIOR que toca o nivel, dentro do prazo
        fill = None
        for j in range(t + 1, min(t + 1 + TTL_BARRAS, n)):
            if (lado < 0 and hi[j] >= nivel) or (lado > 0 and lo[j] <= nivel):
                fill = j
                break
        if fill is None:
            continue

        # trajetoria depois do fill, normalizada pela largura e pelo lado
        fim = min(n - 1, fill + MAX_BARRAS_TRAJ)
        fav, adv, fech = [], [], []
        for j in range(fill + 1, fim + 1):
            if lado < 0:
                fav.append((nivel - lo[j]) / L)
                adv.append((hi[j] - nivel) / L)
                fech.append((nivel - cl[j]) / L)
            else:
                fav.append((hi[j] - nivel) / L)
                adv.append((nivel - lo[j]) / L)
                fech.append((cl[j] - nivel) / L)
            # a trajetoria termina quando o retangulo morre
            if (cl[j] > topo + MARGEM_MORTE * L or cl[j] < piso - MARGEM_MORTE * L):
                pass   # deixa correr; a morte e' registrada pelo campo abaixo
        if not fav:
            continue
        eventos.append(dict(
            data=dia, W=W, modo=modo, lado=("short" if lado < 0 else "long"),
            largura=L, fav=np.array(fav), adv=np.array(adv), fech=np.array(fech)))
        ultimo_evento = fill
    return eventos


# ---------------------------------------------------------------------------
# avaliacao de geometria FIXA sobre as trajetorias
# ---------------------------------------------------------------------------

def resultado_fixo(ev, alvo_f, stop_f):
    """Pontos liquidos da operacao sob (alvo, stop) em fracao da largura.
    Alvo e stop na MESMA barra => STOP (pessimista)."""
    L = ev["largura"]
    a, s = alvo_f * L, stop_f * L
    fav, adv, fech = ev["fav"] * L, ev["adv"] * L, ev["fech"] * L
    bateu_stop = adv >= s
    bateu_alvo = fav >= a
    for i in range(len(fav)):
        if bateu_stop[i]:
            return -s - CUSTO_PONTOS      # pessimista: stop ganha o empate
        if bateu_alvo[i]:
            return a - CUSTO_PONTOS
    return float(fech[-1]) - CUSTO_PONTOS   # nao resolveu: marca a mercado


def resultado_dinamico(ev, regra, par, stop_f):
    L = ev["largura"]
    s = stop_f * L
    fav, adv, fech = ev["fav"] * L, ev["adv"] * L, ev["fech"] * L
    pico = 0.0
    for i in range(len(fav)):
        if adv[i] >= s:
            return -s - CUSTO_PONTOS
        pico = max(pico, fav[i])
        if regra == "tempo":
            if i + 1 >= par:
                return float(fech[i]) - CUSTO_PONTOS
        elif regra == "recuo":
            if pico > 0 and fech[i] <= pico * (1 - par) and pico >= 0.10 * L:
                return float(fech[i]) - CUSTO_PONTOS
        elif regra == "exaustao":
            if fech[i] >= par * L and i > 0 and fech[i] < fech[i - 1]:
                return float(fech[i]) - CUSTO_PONTOS
        elif regra == "deixa":
            # alvo na borda oposta; se romper, segue com trailing de recuo
            if pico >= par * L and fech[i] <= pico * 0.70:
                return float(fech[i]) - CUSTO_PONTOS
    return float(fech[-1]) - CUSTO_PONTOS


def _classifica(ev, alvo_f, stop_f):
    """Como a operacao TERMINOU: 'alvo', 'stop' ou 'marcado' (marcada a mercado
    no fim da trajetoria). Mesma regra pessimista de `resultado_fixo`."""
    L = ev["largura"]
    a, s = alvo_f * L, stop_f * L
    fav, adv, fech = ev["fav"] * L, ev["adv"] * L, ev["fech"] * L
    for i in range(len(fav)):
        if adv[i] >= s:
            return "stop", -s - CUSTO_PONTOS
        if fav[i] >= a:
            return "alvo", a - CUSTO_PONTOS
    return "marcado", float(fech[-1]) - CUSTO_PONTOS


def _stats(vals):
    v = np.asarray(vals, float)
    if len(v) == 0:
        return dict(n=0, media=float("nan"), win=float("nan"),
                    be=float("nan"), gap=float("nan"))
    g, p = v[v > 0], v[v <= 0]
    gm = g.mean() if len(g) else 0.0
    pm = abs(p.mean()) if len(p) else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    win = len(g) / len(v)
    return dict(n=len(v), media=float(v.mean()), win=win, be=be,
                gap=(win - be) if be == be else float("nan"))


def main():
    df, dias = _base._df()
    print("=" * 118)
    print("WIN@ retangulo -- MATRIZ alvo x stop e ALVOS DINAMICOS, sobre as MESMAS trajetorias")
    print("=" * 118)
    print(f"{len(dias)} pregoes | custo {br(CUSTO_PONTOS,1)} pontos/op ja descontado | "
          f"empate alvo-stop na mesma barra = STOP")
    print("PREVISAO A FALSIFICAR: se o retangulo e' jogo justo, a matriz inteira e' plana no")
    print("zero e nao existe percentual ideal. Uma regiao onde o acerto DESCOLA do breakeven")
    print("refuta isso -- e seria o achado.\n", flush=True)

    tarefas = [(d, W, modo) for d in dias for W in JANELAS_W for modo in ("centro", "borda")]
    eventos = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(roda_dia, t): t for t in tarefas}
        feitos = 0
        for fut in as_completed(futs):
            eventos.extend(fut.result())
            feitos += 1
            if feitos % 200 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    for ev in eventos:
        ev["janela"] = "IS" if pd.Timestamp(ev["data"]).date() < CORTE_OOS else "OOS"
    print(f"\n{len(eventos)} eventos gravados")
    resumo = pd.DataFrame([{k: e[k] for k in ("data", "W", "modo", "lado", "janela", "largura")}
                           for e in eventos])
    print(resumo.groupby(["modo", "W", "janela"]).size().unstack(fill_value=0).to_string())

    for modo in ("centro", "borda"):
        for W in JANELAS_W:
            sel = [e for e in eventos if e["modo"] == modo and e["W"] == W]
            if len(sel) < 100:
                continue
            print("\n" + "=" * 118)
            print(f"MATRIZ  modo={modo}  W={W}   ({len(sel)} eventos)")
            print("  celula = pontos liquidos por operacao (IS / OOS). Negrito mental: positivo nas DUAS.")
            print("=" * 118)
            cab = f"  {'stop\\alvo':<12}" + "".join(f"{br(a,2):>16}" for a in ALVOS)
            print(cab)
            print("  " + "-" * (len(cab) - 2))
            melhores = []
            for sf in STOPS:
                linha = f"  {br(sf,2):<12}"
                for af in ALVOS:
                    vi = [resultado_fixo(e, af, sf) for e in sel if e["janela"] == "IS"]
                    vo = [resultado_fixo(e, af, sf) for e in sel if e["janela"] == "OOS"]
                    si, so = _stats(vi), _stats(vo)
                    marca = "*" if (si["media"] > 0 and so["media"] > 0) else " "
                    linha += f"{(br(si['media'],1) + '/' + br(so['media'],1) + marca):>16}"
                    melhores.append(dict(alvo=af, stop=sf, is_=si, oos=so))
                print(linha)
            ok = [m for m in melhores if m["is_"]["media"] > 0 and m["oos"]["media"] > 0]
            print(f"\n  celulas positivas nas DUAS janelas: {len(ok)} de {len(melhores)}"
                  + (f"  -> {[(m['alvo'], m['stop']) for m in ok]}" if ok else ""))

            print(f"\n  O ACERTO DESCOLA DO BREAKEVEN? (gap = win% - breakeven empirico, IS)")
            cab2 = f"  {'stop\\alvo':<12}" + "".join(f"{br(a,2):>10}" for a in ALVOS)
            print(cab2)
            print("  " + "-" * (len(cab2) - 2))
            for sf in STOPS:
                linha = f"  {br(sf,2):<12}"
                for af in ALVOS:
                    vi = [resultado_fixo(e, af, sf) for e in sel if e["janela"] == "IS"]
                    si = _stats(vi)
                    linha += f"{br(100 * si['gap'], 1) + 'pp':>10}"
                print(linha)

    print("\n" + "=" * 118)
    print("ALVOS DINAMICOS -- o alvo definido pelo que o mercado mostra DEPOIS do fill")
    print("=" * 118)
    regras = ([("tempo", m) for m in (5, 10, 20, 40)]
              + [("recuo", x) for x in (0.30, 0.50)]
              + [("exaustao", y) for y in (0.05, 0.10, 0.20)]
              + [("deixa", y) for y in (0.40, 0.50)])
    for modo in ("centro", "borda"):
        for W in JANELAS_W:
            sel = [e for e in eventos if e["modo"] == modo and e["W"] == W]
            if len(sel) < 100:
                continue
            print(f"\n  --- modo={modo} W={W} ({len(sel)} eventos) ---")
            hdr = (f"  {'regra':<22}{'stop':>7}{'n IS':>7}{'pts/op IS':>12}{'win IS':>9}"
                   f"{'BE IS':>8}{'n OOS':>7}{'pts/op OOS':>13}{'win OOS':>10}{'':>5}")
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for regra, par in regras:
                for sf in (0.25, 0.50):
                    vi = [resultado_dinamico(e, regra, par, sf) for e in sel if e["janela"] == "IS"]
                    vo = [resultado_dinamico(e, regra, par, sf) for e in sel if e["janela"] == "OOS"]
                    si, so = _stats(vi), _stats(vo)
                    ok = si["media"] > 0 and so["media"] > 0
                    print(f"  {regra + ' ' + str(par):<22}{br(sf,2):>7}{si['n']:>7}"
                          f"{br(si['media'],2):>12}{br(100*si['win'],1) + '%':>9}"
                          f"{br(100*si['be'],1) + '%':>8}{so['n']:>7}"
                          f"{br(so['media'],2):>13}{br(100*so['win'],1) + '%':>10}"
                          f"{('  <<<' if ok else ''):>5}")

    print("\n" + "=" * 118)
    print("DECOMPOSICAO da regiao promissora -- alvo atingido, stop, ou MARCACAO A MERCADO?")
    print("  Uma celula que so' parece boa porque a maioria das operacoes termina marcada a")
    print("  mercado no fim da trajetoria NAO esta medindo o alvo: esta medindo 'segurar ate")
    print("  o teto de barras'. A decomposicao separa as duas leituras.")
    print("=" * 118)
    for modo in ("centro", "borda"):
        for W in JANELAS_W:
            sel = [e for e in eventos if e["modo"] == modo and e["W"] == W]
            if len(sel) < 100:
                continue
            print("\n" + f"  --- modo={modo} W={W} ---")
            hdr = (f"  {'geometria':<20}{'jan':<5}{'n':>6}{'%alvo':>8}{'%stop':>8}{'%marcado':>10}"
                   f"{'pts alvo':>10}{'pts stop':>10}{'pts marc':>10}{'pts/op':>9}")
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for af, sf in ((0.45, 0.50), (0.80, 0.50), (1.00, 0.50), (0.35, 0.10), (0.45, 0.25)):
                for jan in ("IS", "OOS"):
                    sub = [e for e in sel if e["janela"] == jan]
                    if not sub:
                        continue
                    pares = [_classifica(e, af, sf) for e in sub]
                    cat = np.array([c for c, _ in pares])
                    val = np.array([v for _, v in pares], dtype=float)
                    def _m(tag):
                        x = val[cat == tag]
                        return float(x.mean()) if len(x) else float("nan")
                    print(f"  {f'alvo{af} stop{sf}':<20}{jan:<5}{len(val):>6}"
                          f"{br(100*np.mean(cat=='alvo'),1):>8}{br(100*np.mean(cat=='stop'),1):>8}"
                          f"{br(100*np.mean(cat=='marcado'),1):>10}"
                          f"{br(_m('alvo'),1):>10}{br(_m('stop'),1):>10}{br(_m('marcado'),1):>10}"
                          f"{br(float(val.mean()),2):>9}")

    print("\n" + "=" * 118)
    print("O RESULTADO DEPENDE DA LARGURA DO RETANGULO?")
    print("  Tudo acima ja e' relativo a largura L de CADA retangulo. Aqui a pergunta")
    print("  seguinte: retangulo LARGO se comporta diferente de ESTREITO na mesma geometria")
    print("  RELATIVA? Tercos da largura congelados no IS.")
    print("=" * 118)
    for modo in ("centro", "borda"):
        for W in JANELAS_W:
            sel = [e for e in eventos if e["modo"] == modo and e["W"] == W]
            larg_is = np.array([e["largura"] for e in sel if e["janela"] == "IS"])
            if len(sel) < 100 or len(larg_is) < 30:
                continue
            c1, c2 = float(np.quantile(larg_is, 1 / 3)), float(np.quantile(larg_is, 2 / 3))
            print("\n" + f"  --- modo={modo} W={W} | cortes IS: {br(c1,0)} e {br(c2,0)} pontos ---")
            hdr = (f"  {'geometria':<20}{'largura':<14}{'n IS':>7}{'pts/op IS':>12}"
                   f"{'n OOS':>7}{'pts/op OOS':>13}")
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for af, sf in ((0.45, 0.50), (0.80, 0.50), (0.35, 0.10)):
                for lo_l, hi_l, nome in ((0.0, c1, "1-estreito"), (c1, c2, "2-medio"),
                                         (c2, 1e18, "3-largo")):
                    vi = [resultado_fixo(e, af, sf) for e in sel
                          if e["janela"] == "IS" and lo_l <= e["largura"] < hi_l]
                    vo = [resultado_fixo(e, af, sf) for e in sel
                          if e["janela"] == "OOS" and lo_l <= e["largura"] < hi_l]
                    si, so = _stats(vi), _stats(vo)
                    if si["n"] < 20:
                        continue
                    print(f"  {f'alvo{af} stop{sf}':<20}{nome:<14}{si['n']:>7}"
                          f"{br(si['media'],2):>12}{so['n']:>7}{br(so['media'],2):>13}")
    print("\n" + "=" * 118)
    print("RESSALVAS")
    print("=" * 118)
    print("  - Eventos SE SOBREPOEM (cooldown de 5 barras, sem sequenciamento): os n nao sao")
    print("    independentes e os IC seriam estreitos demais. Isto responde 'existe edge nesta")
    print("    geometria?', nao 'quanto renderia o robo'.")
    print("  - Alvo e stop na mesma barra contam como STOP (pessimista).")
    print("  - Custo de 7,5 pontos por operacao ja descontado em toda celula.")
    print("  - WIN@ sem fila calibrada: a limite enche no TOQUE, otimista.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
