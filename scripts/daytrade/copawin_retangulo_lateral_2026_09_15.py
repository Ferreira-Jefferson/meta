# -*- coding: utf-8 -*-
"""WIN@: detector de RETANGULO -- a lateralizacao como o dono a define.

## A definicao, nas palavras do dono (2026-09-15)

"O preco por varios minutos ou barras vai a um ponto x e volta para proximo do
ponto de origem, depois retorna para proximo do ponto x e volta novamente para
perto do ponto de origem, podendo ficar um pouco abaixo e/ou um pouco acima. O
que da' para notar e' um desenho RETANGULAR que se forma. Quando passa o meio
deste desenho e depois volta passando o meio novamente no sentido contrario, e'
uma lateralizacao."

Veio com duas imagens do proprio grafico: duas linhas horizontais vermelhas, o
preco indo de uma a outra varias vezes ao longo de dezenas de barras.

## Por que isto NAO e' o que ja foi medido (e refutado) hoje

`copawin_lateralizacao_2026_09_15.py` mediu um ESCALAR -- razao de eficiencia
(deslocamento / caminho). Um retangulo pontua baixo nessa razao, mas a razao
tambem pontua baixo num V, numa caminhada aleatoria que voltou ao ponto de
partida, ou num funil. **Eficiencia baixa e' necessaria, nao suficiente.**

A definicao do dono tem TRES elementos estruturais que o escalar nao tem:

  1. REPETICAO      -- pelo menos duas idas a cada borda
  2. NIVEIS COERENTES -- os topos perto do mesmo preco, os fundos tambem,
                       com tolerancia ("um pouco acima/abaixo")
  3. CRUZAMENTOS DO MEIO em sentidos alternados -- o criterio operacional que
                       ele deu de forma mais precisa

E ha' uma diferenca de SELETIVIDADE que invalida a refutacao anterior para
este caso: o evento testado no fade foi "tocou a borda da faixa rolante de 10
barras e voltou", que acontece ~99 vezes por pregao (12.771 eventos em 129
pregoes). Um retangulo confirmado e' raro. A parede encontrada antes foi
"nenhum balde tem expectativa negativa"; um detector MUITO mais seletivo e'
exatamente o que poderia isolar um subconjunto que o escalar diluiu.

## A PERGUNTA QUE ESTE SCRIPT RESPONDE PRIMEIRO (e que pode matar a ideia)

Nao e' "da' dinheiro?". E': **quando o retangulo fica RECONHECIVEL, ele ainda
tem vida pela frente?** Exigir 2 toques por lado e 3 cruzamentos do meio
consome tempo -- pode ser que, no instante em que da' para confirma-lo, ele ja
esteja acabando. Se a resposta for "quase nao sobra vida", nenhuma estrategia
em cima dele funciona, qualquer que seja a geometria. Por isso a medicao
central aqui e' a VIDA DEPOIS DA CONFIRMACAO, nao o lucro.

## O detector (sem look-ahead)

Janela deslizante de W barras M1 terminando na barra `t`, dentro de UM pregao
(nada atravessa a virada). O retangulo so' e' declarado com barras JA FECHADAS
-- a confirmacao acontece em `t`, e tudo que e' medido depois usa so' barras
posteriores a `t`.

    topo = quantil 95 dos `high`      piso = quantil 5 dos `low`
    (quantil, nao max/min: o dono desenha a linha pelo AGLOMERADO de topos e
     tolera o repique que fura -- "podendo ficar um pouco abaixo e/ou acima")

    L = topo - piso          meio = (topo + piso) / 2
    zona de toque = tol x L a partir de cada borda

Condicoes, TODAS obrigatorias:
    - toques no topo >= 2  e  toques no piso >= 2
    - alternancia: a sequencia de toques troca de lado pelo menos 2 vezes
      (topo->piso->topo ou piso->topo->piso) -- e' o "vai e volta" do texto
    - cruzamentos do meio >= 3, em sentidos alternados por construcao
    - contencao: >= 90% dos fechamentos dentro de [piso, topo]
    - horizontalidade: |media do ultimo terco - media do primeiro terco| <=
      0,25 x L  (senao e' canal inclinado, nao retangulo)
    - largura minima: L >= LARGURA_MIN_TICKS ticks -- um retangulo estreito
      demais existe no grafico mas nao paga o pedagio de 1,5 tick (7,5 pontos)
      do WIN, entao nao interessa

Supressao de sobreposicao: confirmado em `t`, o retangulo vive ate o preco
FECHAR fora de [piso - tol*L, topo + tol*L]; a varredura so' recomeca depois
disso. Assim cada retangulo e' contado uma vez, e nao 40 vezes seguidas.

## O que sai

  1. Quantos retangulos por pregao, por W -- se der 30 por dia, o detector
     esta' frouxo; se der 0,05, esta' apertado demais para servir de base.
  2. VIDA DEPOIS DA CONFIRMACAO: minutos ate a quebra, travessias de borda a
     borda que ainda acontecem, cruzamentos do meio que ainda acontecem.
  3. Uma lista de EXEMPLOS com data, hora BRT, topo, piso e largura, para o
     dono conferir no proprio grafico -- e' a unica validacao que existe para
     um detector de padrao visual: bater com o olho de quem o descreveu.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_lateral_2026_09_15.py`
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

_spec = importlib.util.spec_from_file_location(
    "_base_ret", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CORTE_OOS = pd.Timestamp("2026-06-13").date()
SCRATCH = ROOT / "scratch"

#: janelas de varredura, em barras M1. O retangulo das imagens do dono ocupa
#: algumas dezenas de candles -- 20 a 60 cobre a faixa plausivel.
JANELAS = (30, 45, 60, 90, 120)
#: tolerancia das bordas, em fracao da largura ("um pouco acima/abaixo").
#: v1 usava 0,15 e isso, somado a banda q95/q05, fazia quase toda janela
#: qualificar (8.830 achados, 15/pregao, banda mediana de 598 pontos = 120
#: ticks). Um retangulo tem borda ESTREITA -- e' o que a define.
TOL = 0.08
#: minimos estruturais da definicao
TOQUES_MIN = 2
#: VISITAS por borda -- barras consecutivas encostadas colapsam em uma. E' o
#: criterio fiel a definicao do dono ("vai ao x, volta, retorna ao x"); contar
#: barras deixa passar o preco grudado na borda por 14 minutos como se fossem
#: 14 idas. Este e' o parametro que de fato governa a forma.
VISITAS_MIN = 2
CRUZAMENTOS_MIN = 3
#: contencao so' e' um TESTE se a banda for mais apertada que os extremos; com
#: q95/q05 ela dava >=90%% por construcao. Agora q90/q10 com exigencia de 95%%.
CONTENCAO_MIN = 0.95
#: CONTRACAO -- o elemento que faltava em v1 e que salta da imagem do dono: o
#: retangulo e' ESTREITO comparado ao movimento que veio antes dele. Sem isso,
#: "retangulo" e' so' um pedaco de mercado qualquer visto de perto.
CONTRACAO_MAX = 0.55
#: os toques tem de estar ESPALHADOS no tempo ("vai, volta, vai de novo"), nao
#: agrupados em 3 barras seguidas: primeiro e ultimo toque de cada borda
#: separados por pelo menos W/3 barras.
ESPALHAMENTO_MIN = 1 / 3
#: inclinacao maxima: deriva do primeiro ao ultimo terco, em fracao da largura
DERIVA_MAX = 0.25
#: um retangulo mais estreito que isto nao paga o pedagio de 1,5 tick
LARGURA_MIN_TICKS = 6.0


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _avalia_janela(high, low, close, range_antes=None, tol=TOL):
    """Devolve o dicionario do retangulo se a janela qualifica, senao None.

    `range_antes` e' a amplitude das 2W barras ANTERIORES a janela -- serve so'
    para o teste de CONTRACAO. Quando nao existe (comeco do pregao), o teste e'
    pulado e isso fica marcado no achado."""
    topo = float(np.quantile(high, 0.90))
    piso = float(np.quantile(low, 0.10))
    L = topo - piso
    if L <= 0:
        return None
    meio = (topo + piso) / 2.0
    zona = tol * L

    # toques, na ordem cronologica, com o lado E a posicao (para o espalhamento)
    lados, pos_topo, pos_piso = [], [], []
    for i, (h, lo) in enumerate(zip(high, low)):
        if h >= topo - zona:
            lados.append(1)
            pos_topo.append(i)
        elif lo <= piso + zona:
            lados.append(-1)
            pos_piso.append(i)
    n_topo, n_piso = len(pos_topo), len(pos_piso)
    if n_topo < TOQUES_MIN or n_piso < TOQUES_MIN:
        return None
    # VISITAS: barras consecutivas na mesma borda colapsam em uma visita so'.
    # E' o que a definicao do dono pede ("vai ao ponto x, VOLTA, RETORNA ao
    # x") -- contar BARRAS confunde "visitou 3 vezes" com "ficou 14 minutos
    # encostado na borda", que sao coisas diferentes no grafico.
    def _visitas(pos):
        return 1 + sum(1 for a, b in zip(pos, pos[1:]) if b - a > 1)
    v_topo, v_piso = _visitas(pos_topo), _visitas(pos_piso)
    if v_topo < VISITAS_MIN or v_piso < VISITAS_MIN:
        return None
    minimo = ESPALHAMENTO_MIN * len(close)
    if (pos_topo[-1] - pos_topo[0]) < minimo or (pos_piso[-1] - pos_piso[0]) < minimo:
        return None
    # alternancia: quantas vezes a sequencia de toques troca de borda
    trocas = sum(1 for a, b in zip(lados, lados[1:]) if a != b)
    if trocas < 2:
        return None

    # cruzamentos do meio (troca de lado do fechamento)
    acima = close > meio
    cruz = int(np.sum(acima[1:] != acima[:-1]))
    if cruz < CRUZAMENTOS_MIN:
        return None

    contencao = float(np.mean((close >= piso) & (close <= topo)))
    if contencao < CONTENCAO_MIN:
        return None

    n = len(close)
    t1 = float(np.mean(close[: n // 3]))
    t3 = float(np.mean(close[-(n // 3):]))
    if abs(t3 - t1) > DERIVA_MAX * L:
        return None

    contraiu = float("nan")
    if range_antes is not None and range_antes > 0:
        contraiu = L / range_antes
        if contraiu > CONTRACAO_MAX:
            return None

    return dict(topo=topo, piso=piso, largura=L, meio=meio, contracao=contraiu,
                visitas_topo=v_topo, visitas_piso=v_piso,
                toques_topo=n_topo, toques_piso=n_piso, trocas=trocas,
                cruzamentos=cruz, contencao=contencao,
                deriva_frac=abs(t3 - t1) / L)


def _vida_depois(idx, high, low, close, ret, inicio, margem, barras_fora):
    """Mede o que acontece DEPOIS da confirmacao. Nada aqui olha para tras.

    `margem` (em fracao da largura) e `barras_fora` (fechamentos consecutivos
    fora) definem quando o retangulo MORREU. Isto nao e' detalhe: com
    margem=TOL e barras_fora=1 o primeiro repique mata o padrao, e a "vida"
    medida vira artefato do criterio. Nas imagens do dono o preco FURA as
    linhas e volta, e o retangulo continua -- por isso o script roda os dois
    criterios lado a lado e reporta a sensibilidade."""
    topo, piso, L, meio = ret["topo"], ret["piso"], ret["largura"], ret["meio"]
    fora_cima, fora_baixo = topo + margem * L, piso - margem * L
    lado_ant = 1 if close[inicio] > meio else -1
    borda_ant = None
    travessias = cruz = seguidas = 0
    fim = len(close) - 1
    quebrou = False
    for j in range(inicio + 1, len(close)):
        if close[j] > fora_cima or close[j] < fora_baixo:
            seguidas += 1
            if seguidas >= barras_fora:
                fim = j
                quebrou = True
                break
        else:
            seguidas = 0
        lado = 1 if close[j] > meio else -1
        if lado != lado_ant:
            cruz += 1
            lado_ant = lado
        borda = 1 if high[j] >= topo - TOL * L else (-1 if low[j] <= piso + TOL * L else None)
        if borda is not None:
            if borda_ant is not None and borda != borda_ant:
                travessias += 1
            borda_ant = borda
    minutos = (idx[fim] - idx[inicio]).total_seconds() / 60.0
    direcao = ("cima" if quebrou and close[fim] > fora_cima
               else "baixo" if quebrou else "fim do pregao")
    return dict(vida_min=minutos, travessias_depois=travessias,
                cruzamentos_depois=cruz, quebrou=int(quebrou), direcao=direcao,
                barras_depois=fim - inicio)


def roda_dia(args):
    dia, tick = args
    df, _ = _base._df()
    b = df[df.index.date == dia]
    if b.empty:
        return []
    idx = b.index
    high = b["high"].to_numpy(float)
    low = b["low"].to_numpy(float)
    close = b["close"].to_numpy(float)
    achados = []
    for W in JANELAS:
        t = W - 1
        while t < len(close):
            ini = t - W + 1
            antes0 = max(0, ini - 2 * W)
            range_antes = (float(high[antes0:ini].max() - low[antes0:ini].min())
                           if ini - antes0 >= W else None)
            ret = _avalia_janela(high[ini:t + 1], low[ini:t + 1],
                                 close[ini:t + 1], range_antes)
            if ret is None or ret["largura"] < LARGURA_MIN_TICKS * tick:
                t += 1
                continue
            # ESTRITO: morre no 1o fechamento fora da tolerancia de borda.
            # TOLERANTE: so' morre depois de 3 fechamentos seguidos alem de
            # 25% da largura -- e' o que corresponde ao "fura e volta" do
            # desenho. O segundo e' o que governa a supressao, senao o
            # detector recomeca a varrer no meio do proprio retangulo.
            vida = _vida_depois(idx, high, low, close, ret, t, TOL, 1)
            vida_tol = _vida_depois(idx, high, low, close, ret, t, 0.25, 3)
            achados.append(dict(
                data=dia, janela_barras=W,
                confirmou_utc=idx[t], inicio_utc=idx[t - W + 1],
                largura_pontos=ret["largura"],
                largura_ticks=ret["largura"] / tick,
                **{k: ret[k] for k in ("topo", "piso", "visitas_topo", "visitas_piso",
                                       "toques_topo", "toques_piso",
                                       "trocas", "cruzamentos", "contencao",
                                       "deriva_frac", "contracao")},
                **vida,
                **{f"tol_{k}": v for k, v in vida_tol.items()}))
            # supressao pelo criterio TOLERANTE (o mais longo dos dois)
            t = t + max(1, vida_tol["barras_depois"])
    return achados


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    df, dias = _base._df()
    strat = _base._construir_estrategia()
    tick = float(strat.tick_size)

    print("=" * 112)
    print("WIN@ -- DETECTOR DE RETANGULO (a lateralizacao como o dono a define)")
    print("=" * 112)
    print(f"{len(dias)} pregoes ({dias[0]} a {dias[-1]}), tick = {br(tick, 0)} pontos.")
    print(f"criterios: >= {VISITAS_MIN} VISITAS por borda (barras seguidas colapsam), "
          f">= 2 trocas de borda, "
          f">= {CRUZAMENTOS_MIN} cruzamentos do meio,")
    print(f"           contencao >= {int(CONTENCAO_MIN*100)}%, deriva <= {int(DERIVA_MAX*100)}% da largura, "
          f"largura >= {br(LARGURA_MIN_TICKS,0)} ticks, tolerancia de borda {int(TOL*100)}%,")
    print(f"           CONTRACAO: banda <= {int(CONTRACAO_MAX*100)}% da amplitude das 2W barras anteriores,")
    print(f"           ESPALHAMENTO: 1o e ultimo toque de cada borda separados por >= W/3 barras.")
    print(f"janelas varridas: {JANELAS} barras M1.\n", flush=True)

    linhas = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(roda_dia, (d, tick)): d for d in dias}
        feitos = 0
        for fut in as_completed(futs):
            linhas.extend(fut.result())
            feitos += 1
            if feitos % 40 == 0:
                print(f"  ... {feitos}/{len(dias)} pregoes", flush=True)

    r = pd.DataFrame(linhas)
    if r.empty:
        print("\nNENHUM retangulo encontrado -- o detector esta' apertado demais.")
        return
    r["janela"] = np.where(pd.to_datetime(r["data"]).dt.date < CORTE_OOS, "IS", "OOS")
    r["hora_brt"] = pd.to_datetime(r["confirmou_utc"], utc=True).dt.tz_convert(
        "America/Sao_Paulo").dt.strftime("%H:%M")
    r = r.sort_values(["data", "confirmou_utc"])
    r.to_csv(SCRATCH / "copawin_retangulos.csv", index=False, encoding="utf-8")

    print(f"\n{len(r)} retangulos detectados -> scratch/copawin_retangulos.csv\n")

    print("=" * 112)
    print("1) FREQUENCIA -- o detector esta' frouxo ou apertado?")
    print("=" * 112)
    hdr = (f"  {'W (barras)':<12}{'n':>7}{'por pregao':>13}{'pregoes com':>13}"
           f"{'largura ticks (mediana)':>26}{'largura pontos':>17}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in JANELAS:
        s = r[r.janela_barras == W]
        print(f"  {W:<12}{len(s):>7}{br(len(s)/len(dias)):>13}"
              f"{f'{s.data.nunique()}/{len(dias)}':>13}"
              f"{br(s.largura_ticks.median(), 1):>26}{br(s.largura_pontos.median(), 0):>17}")

    print("\n" + "=" * 112)
    print("2) VIDA DEPOIS DA CONFIRMACAO -- a pergunta que mata ou libera a ideia")
    print("   (tudo medido SO' com barras posteriores ao instante em que o retangulo")
    print("    ficou reconhecivel; se sobra pouca vida, nenhuma geometria salva)")
    print("=" * 112)
    for rot, pre in (("ESTRITO (morre no 1o fechamento fora da tolerancia de borda)", ""),
                     ("TOLERANTE (3 fechamentos seguidos alem de 25% da largura)", "tol_")):
        print(f"\n  --- criterio de morte {rot} ---")
        hdr = (f"  {'W':<5}{'jan':<5}{'n':>6}{'vida med (min)':>16}{'p25':>7}{'p75':>7}"
               f"{'travessias med':>16}{'>=1 travessia':>15}{'>=2':>7}{'quebrou':>9}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for W in JANELAS:
            for jan in ("IS", "OOS"):
                s = r[(r.janela_barras == W) & (r.janela == jan)]
                if s.empty:
                    continue
                print(f"  {W:<5}{jan:<5}{len(s):>6}{br(s[pre+'vida_min'].median(), 1):>16}"
                      f"{br(s[pre+'vida_min'].quantile(.25), 0):>7}"
                      f"{br(s[pre+'vida_min'].quantile(.75), 0):>7}"
                      f"{br(s[pre+'travessias_depois'].median(), 1):>16}"
                      f"{br(100*(s[pre+'travessias_depois'] >= 1).mean(), 0) + '%':>15}"
                      f"{br(100*(s[pre+'travessias_depois'] >= 2).mean(), 0) + '%':>7}"
                      f"{br(100*s[pre+'quebrou'].mean(), 0) + '%':>9}")

    print("\n  COMO LER: 'travessias depois' = quantas vezes o preco ainda foi de uma borda")
    print("  a outra DEPOIS de o retangulo virar reconhecivel. E' o numero de oportunidades")
    print("  de fade que sobram. Zero = o padrao so' e' visivel quando ja acabou.")

    print("\n" + "=" * 112)
    print("2b) VISITAS x TOQUES -- 'visita' e' ida a borda; 'toque' e' barra encostada nela")
    print("=" * 112)
    hdr = (f"  {'W':<6}{'visitas topo':>15}{'visitas piso':>15}"
           f"{'toques topo':>14}{'toques piso':>14}{'>=3 visitas nas 2 bordas':>27}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in JANELAS:
        s2 = r[r.janela_barras == W]
        tres = 100 * ((s2.visitas_topo >= 3) & (s2.visitas_piso >= 3)).mean()
        print(f"  {W:<6}{br(s2.visitas_topo.median(), 1):>15}{br(s2.visitas_piso.median(), 1):>15}"
              f"{br(s2.toques_topo.median(), 1):>14}{br(s2.toques_piso.median(), 1):>14}"
              f"{br(tres, 0) + '%':>27}")
    print("  (medianas. 'visita' colapsa barras consecutivas na mesma borda.)")
    print()
    print("=" * 112)
    print("3) COMO O RETANGULO MORRE")
    print("=" * 112)
    print(r.groupby(["janela_barras", "tol_direcao"]).size().unstack(fill_value=0).to_string())

    print("\n" + "=" * 112)
    print("4) EXEMPLOS PARA CONFERIR NO GRAFICO -- os 25 de maior vida depois da confirmacao")
    print("   (abra a data/hora no seu grafico e veja se o desenho e' o que voce descreveu)")
    print("=" * 112)
    ex = r.sort_values("tol_vida_min", ascending=False).head(25)
    cols = ["data", "hora_brt", "janela_barras", "topo", "piso", "largura_pontos",
            "visitas_topo", "visitas_piso", "toques_topo", "toques_piso",
            "cruzamentos", "tol_vida_min",
            "tol_travessias_depois", "tol_direcao"]
    print(ex[cols].to_string(index=False))
    ex.to_csv(SCRATCH / "copawin_retangulos_exemplos.csv", index=False, encoding="utf-8")

    print("\n  Os 25 exemplos tambem estao em scratch/copawin_retangulos_exemplos.csv.")
    print("  A hora e' BRT e marca o instante da CONFIRMACAO -- o retangulo comeca")
    print("  `W` barras antes dela.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
