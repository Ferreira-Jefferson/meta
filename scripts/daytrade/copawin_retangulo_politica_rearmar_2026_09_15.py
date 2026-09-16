# -*- coding: utf-8 -*-
"""WIN@ retangulo: a POLITICA DE RE-ARMAR -- quantas operacoes por retangulo,
e por quanto tempo.

Correcao do dono (2026-09-15): "eu disse 'se estamos no W30 e sabemos que dura
ao todo 61min podemos replicar isso ate a barra 50 se nao romper antes' -- mas
talvez voce tenha encarado esse valor como algo fixo. Quero que meca isso
tambem: e se rodar so' 10 barras a mais? 20 barras a mais? E se rodar uma
operacao so' -- bateu alvo ou stop, espera outra lateralizacao para iniciar
outro trade? Teste essas e outras hipoteses."

Ele esta certo: a rodada anterior tratou "armar enquanto o retangulo viver"
como se fosse A politica, quando ela e' um EIXO. Este script varre o eixo.

## O que esta em jogo

A geometria ja foi medida e tem candidato: entrada no CENTRO, stop 0,5xL (na
borda), alvo 0,8xL (ALEM da borda oposta), W=30 -- IS +777,50 (771 trades,
41,2%) e OOS +1.036,80 (338, 44,7%); controle sem os criterios de retangulo da
IS -2.949,40, ou seja, o detector e' load-bearing. E o efeito mora nos
retangulos LARGOS: +57,38 pts/op no IS e +70,22 no OOS no terco superior
(> 388 pontos), contra estreito (+5,95 / -12,47) e medio (-9,75 / +33,49).

Com a geometria fixada, o que sobra e' QUANTAS vezes e ATE QUANDO operar cada
retangulo. Cada politica muda a populacao de trades -- nao e' ajuste fino, e'
outra estrategia.

## Os eixos

1. `max_barras_apos` -- para de armar entrada N barras depois da confirmacao.
   {10, 20, 30, 50, None}. O None e' "enquanto o retangulo viver", que era o
   default implicito da rodada anterior. A vida mediana medida apos a
   confirmacao no W=30 e' 20 barras (criterio tolerante), entao 10 e' "metade
   da vida esperada" e 50 e' "bem alem dela".

2. `uma_por_retangulo` -- bateu alvo ou stop, so' volta a operar quando um
   retangulo NOVO for confirmado. {False, True}.

3. `barras_extra_apos_morte` -- continua armando por N barras DEPOIS de o
   retangulo morrer, com os ultimos niveis conhecidos. {0, 10, 20}. E' o "10
   barras a mais / 20 barras a mais" do pedido, e testa uma hipotese propria:
   o rompimento e' justamente o momento em que os niveis viram referencia de
   retest -- pode ser que operar 10 barras ALEM da morte seja melhor que
   parar nela.

4. `largura_min_pontos` -- {0 (todos), 388 (so' o terco superior, corte
   CONGELADO no IS)}. Entra porque o corte de largura foi o unico que manteve
   sinal e magnitude nas duas janelas.

## Convencoes

Geometria fixa em alvo 0,8xL / stop 0,5xL, modo centro, W=30 (o candidato).
Capital R$3.000, 1 contrato fixo (isola geometria do portao de capital),
desenho de execucao fechado, corte de achatamento de producao. IS < 2026-06-13,
OOS >= 2026-06-13. Criterio: positivo nas DUAS janelas; sinal trocado refuta.

RESSALVA que nao muda: WIN@ nao tem fila calibrada -- a limite enche no TOQUE.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_politica_rearmar_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "estr_pol", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_pol"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
CAPITAL = _estr.CAPITAL
CORTE_OOS = pd.Timestamp("2026-06-13").date()

#: a geometria candidata, fixa neste script
GEO = dict(modo="centro", W=30, alvo_frac=1.6, stop_frac=0.5)
#: corte do terco superior de largura, CONGELADO no IS
LARGURA_TERCO_SUPERIOR = 388.0

MAX_BARRAS = (10, 20, 30, 50, None)
EXTRAS_MORTE = (0, 10, 20)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _unidade(args):
    rotulo, janela_nome, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _estr._roda(dias, **kw)
    c = _base.consistencia(list(res.trades), dias)
    pts = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    return dict(rotulo=rotulo, janela=janela_nome, c=c, pts=pts, res=res)


def main():
    df, dias = _base._df()
    janelas = {"IS": [d for d in dias if d < CORTE_OOS],
               "OOS": [d for d in dias if d >= CORTE_OOS]}

    variantes = []
    for largura, tag_l in ((0.0, "todos"), (LARGURA_TERCO_SUPERIOR, "largos")):
        for uma, tag_u in ((False, "repete"), (True, "1 por ret.")):
            for mb in MAX_BARRAS:
                for ex in EXTRAS_MORTE:
                    # a sobrevida so' faz sentido quando o teto de barras nao
                    # corta antes: com max=10 e sobrevida 20 a sobrevida nunca
                    # chega a valer. Fica de fora para nao poluir a grade.
                    if ex > 0 and mb is not None and mb <= 20:
                        continue
                    rot = (f"{tag_l:<6} {tag_u:<10} ate {str(mb):<4} +{ex:>2}b")
                    variantes.append((rot, dict(
                        **GEO, max_barras_apos=mb, uma_por_retangulo=uma,
                        barras_extra_apos_morte=ex, largura_min_pontos=largura)))

    print("=" * 118)
    print("WIN@ retangulo -- POLITICA DE RE-ARMAR (quantas operacoes por retangulo, e ate quando)")
    print("=" * 118)
    print(f"geometria FIXA: modo centro, W=30, alvo 0,8xL, stop 0,5xL  |  capital R$ {br(CAPITAL,0)}, "
          f"1 contrato")
    print(f"{len(variantes)} variantes x 2 janelas = {2*len(variantes)} rodadas")
    print("vida mediana do retangulo W=30 apos a confirmacao: 20 barras (criterio tolerante)")
    print("RESSALVA: WIN@ sem fila calibrada -- a limite enche no TOQUE.\n", flush=True)

    tarefas = [(rot, jn, dd, kw) for rot, kw in variantes for jn, dd in janelas.items()]
    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        feitos = 0
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["rotulo"], {})[r["janela"]] = r
            feitos += 1
            if feitos % 20 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    print("\n" + "=" * 118)
    print("RESULTADO -- criterio: positivo no IS E no OOS")
    print("=" * 118)
    hdr = (f"  {'variante':<34}{'IS liq':>11}{'IS n':>7}{'IS win':>8}{'IS pts/op':>11}"
           f"{'OOS liq':>11}{'OOS n':>7}{'OOS win':>9}{'OOS pts/op':>12}{'':>5}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    passou = []
    for rot, _kw in variantes:
        ri, ro = out[rot]["IS"], out[rot]["OOS"]
        ci, co = ri["c"], ro["c"]
        ok = ci["liquido"] > 0 and co["liquido"] > 0 and ci["n"] >= 30 and co["n"] >= 15
        if ok:
            passou.append((rot, ci, co, ri, ro))
        print(f"  {rot:<34}{br(ci['liquido']):>11}{ci['n']:>7}"
              f"{(br(100*ci['win'],1) if ci['n'] else '--'):>8}{br(ri['pts'],2):>11}"
              f"{br(co['liquido']):>11}{co['n']:>7}"
              f"{(br(100*co['win'],1) if co['n'] else '--'):>9}{br(ro['pts'],2):>12}"
              f"{('  <<<' if ok else ''):>5}")

    print(f"\n  {len(passou)} de {len(variantes)} positivas nas duas janelas.")

    if passou:
        print("\n" + "=" * 118)
        print("CONSISTENCIA das que passaram (o que separa edge de concentracao)")
        print("=" * 118)
        hdr2 = (f"  {'variante':<34}{'jan':<5}{'preg+':>7}{'bl20+':>7}{'mes+':>7}"
                f"{'top5':>7}{'seq-':>6}{'BEemp%':>9}{'veredito':>12}{'sem_tr':>10}")
        print(hdr2)
        print("  " + "-" * (len(hdr2) - 2))
        for rot, ci, co, _ri, _ro in passou:
            for jan, c in (("IS", ci), ("OOS", co)):
                sem_tr = f"{c['sem_trade']}/{c['pregoes']}"
                print(f"  {rot:<34}{jan:<5}"
                      f"{(br(100*c['frac_preg'],0)+'%'):>7}{(br(100*c['frac_bl'],0)+'%'):>7}"
                      f"{(br(100*c['frac_mes'],0)+'%'):>7}"
                      f"{(br(100*c['top5'],0)+'%') if c['top5']==c['top5'] else '--':>7}"
                      f"{c['seq_neg']:>6}"
                      f"{(br(100*c['be'],1)+'%') if c['be']==c['be'] else '--':>9}"
                      f"{c['veredito']:>12}{sem_tr:>10}")

    print("\n" + "=" * 118)
    print("LEITURA POR EIXO -- qual decisao move o resultado?")
    print("=" * 118)
    for eixo, valores, extrai in (
        ("teto de barras apos a confirmacao", MAX_BARRAS, lambda kw: kw["max_barras_apos"]),
        ("uma operacao por retangulo", (False, True), lambda kw: kw["uma_por_retangulo"]),
        ("barras alem da morte", EXTRAS_MORTE, lambda kw: kw["barras_extra_apos_morte"]),
        ("piso de largura", (0.0, LARGURA_TERCO_SUPERIOR), lambda kw: kw["largura_min_pontos"]),
    ):
        print(f"\n  --- {eixo} (media das celulas que compartilham o valor) ---")
        print(f"  {'valor':<12}{'n celulas':>11}{'IS liq medio':>15}{'OOS liq medio':>15}"
              f"{'celulas +/+':>13}")
        for v in valores:
            sel = [(rot, kw) for rot, kw in variantes if extrai(kw) == v]
            if not sel:
                continue
            li = [out[rot]["IS"]["c"]["liquido"] for rot, _ in sel]
            lo = [out[rot]["OOS"]["c"]["liquido"] for rot, _ in sel]
            pos = sum(1 for a, b in zip(li, lo) if a > 0 and b > 0)
            print(f"  {str(v):<12}{len(sel):>11}{br(sum(li)/len(li)):>15}"
                  f"{br(sum(lo)/len(lo)):>15}{f'{pos}/{len(sel)}':>13}")

    print("\n  Um eixo cujo valor nao muda a media e' eixo MORTO -- a decisao nele nao importa,")
    print("  e uma celula que so' vence por causa dele e' ruido. Ver item 6.25 de LICOES.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
