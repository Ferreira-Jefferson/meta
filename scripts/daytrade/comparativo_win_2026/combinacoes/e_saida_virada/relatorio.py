import pandas as pd
m=pd.read_csv('resultado_mensal.csv'); p=pd.read_csv('resultado_pareado.csv'); c=pd.read_csv('resultado_controles.csv')
f=lambda x: f"{x:,.0f}".replace(",",".")
meses=['jan','fev','mar','abr','mai','jun','jul','ago','set','out']
L=["# Frente E - Saida pela virada da outra familia (teste pareado)\n",
"Mesmas entradas (1.421 ops: Win 181, Cinco 308, Desloc 65, RetEma34 733, WdoRet 134; Win_c1 fora). Saida extra a MERCADO no `last` do 1o tick da M1 t+1 quando o voto vira contra numa M1 fechada t; vale so' se antes da saida original (stop/alvo originais intocados; a mercado e' aceitavel por ser saida condicional tipo stop). Familias: tendencia {Win, Cinco, Desloc}, retangulo {RetEma34, WdoRet}. V1 = outra familia INTEIRA contra; V2 = QUALQUER da outra contra; V3 = qualquer outra da PROPRIA familia (sem a propria) contra; a = sem, b = exigindo posicao no lucro no close da M1 t. **Celulas olhadas: 6 variantes pre-registradas x (5 estrategias + soma) = 36 celulas pareadas, mais 2 custos; nenhuma outra variante foi rodada.** Limitacao: as entradas seguintes da mesma estrategia no dia nao sao recalculadas.\n",
"## Soma das 5 (1 contrato cada, caixa R$1.000 corrido por ordem de saida), por mes da saida\n"]
for cu,tt in ((0.0,'sem custo'),(2.0,'R$2/op')):
    L.append(f"### {tt}\n"); L.append("| variante | "+" | ".join(meses)+" | total | caixa min | MaxDD | quebra |"); L.append("|"+"---|"*15)
    s=m[(m.escopo=='soma')&(m.custo==cu)]
    for r in s.itertuples():
        L.append(f"| {r.variante} | "+" | ".join(f(getattr(r,f'm{i}')) for i in range(1,11))+f" | **{f(r.total)}** | {f(r.caixa_min)} | {f(r.maxdd)} | {'QUEBRA' if r.quebra else 'nao'} |")
    L.append("")
L.append("## Por estrategia, total (R$): original -> variante\n")
for cu,tt in ((0.0,'sem custo'),(2.0,'R$2/op')):
    L.append(f"### {tt}\n"); vs=['original','V1a','V1b','V2a','V2b','V3a','V3b']
    L.append("| estrategia | "+" | ".join(vs)+" |"); L.append("|"+"---|"*8)
    for e in ['Win','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34','WdoRetangulo','soma']:
        row=[f(m[(m.variante==v)&(m.escopo==e)&(m.custo==cu)].total.iloc[0]) for v in vs]
        L.append(f"| {e} | "+" | ".join(row)+" |")
    L.append("")
L.append("Nenhuma celula quebrou o caixa de R$1.000 (todas com caixa minimo > 0; ver colunas acima).\n")
L.append("## Pareado: R$ da saida nova - R$ da original, por operacao (IC 95% bootstrap por dia, 2000 reamostras)\n")
L.append("| variante | escopo | ops | afetadas | delta total R$ | media/op [IC] | media/afetada [IC] |"); L.append("|"+"---|"*7)
for r in p.itertuples():
    L.append(f"| {r.variante} | {r.escopo} | {r.n} | {r.afetadas} | {f(r.delta_total)} | {r.media_por_op:.2f} [{r.ic_lo:.2f}; {r.ic_hi:.2f}] | {r.media_afetadas:.2f} [{r.ic_af_lo:.2f}; {r.ic_af_hi:.2f}] |")
L.append("\n## Controles (200 sorteios): percentil do delta total real (maior = real melhor que o sorteio)\n")
L.append("Sorteio de instante: os atrasos (M1 desde a entrada) das saidas disparadas sao permutados entre as mesmas operacoes (nas variantes b, exige lucro no instante sorteado). Placebo: voto da outra familia/propria trocado por lado sorteado, persistente em cada trecho continuo de voto.\n")
L.append("| variante | escopo | disparadas | delta real | sorteio medio (p95) | pct sorteio | placebo medio (p95) | pct placebo |"); L.append("|"+"---|"*8)
for r in c.itertuples():
    L.append(f"| {r.variante} | {r.escopo} | {r.disparadas} | {f(r.delta_real)} | {f(r.sorteio_media)} ({f(r.sorteio_p95)}) | {r.pct_sorteio:.1f} | {f(r.placebo_media)} ({f(r.placebo_p95)}) | {r.pct_placebo:.1f} |")
L.append("""
## Leitura
- Nenhuma variante melhora a soma: delta total entre -3.180 e -8.587 R$ (sem custo); IC 95% da media por operacao inclui zero em V1a, V1b, V3a, V3b e fica abaixo de zero so' em V2a/V2b (as mais agressivas, que disparam em 44% das ops). Sair pela virada devolve o alvo/ganho que a saida original ia colher.
- Contra o sorteio de instante: V1a (outra familia inteira) e' o melhor que o acaso (pct 100) e V1b 96,5, mas ainda negativo contra a original: a virada perde MENOS que sair cedo ao acaso, nao ganha. V2 (pct 51-60) e V3 (0-33) nao se distinguem do acaso ou ficam abaixo.
- Placebo: V2 e V3 sao MELHORES que o placebo (pct 99-100), mas o placebo dispara muito mais cedo e perde bem mais; contra o placebo V1 nao se destaca (30-72).
- Por estrategia: o dano vem do WinCincoMedias (-2,9 a -5,6 mil em V1/V2) e do RetEma34/WdoRet em V2/V3; ganhos pontuais em Win (V2b +181) e WdoRet (V1a +367, V1b +286, V2a +48) sao pequenos e com poucas ops. Com 36 celulas olhadas e correcao de Bonferroni (6 variantes) nada sobrevive.
""")
open('resultado.md','w',encoding='utf-8').write("\n".join(L))
