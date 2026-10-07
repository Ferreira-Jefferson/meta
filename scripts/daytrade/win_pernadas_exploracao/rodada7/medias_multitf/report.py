import pickle, json, numpy as np, pandas as pd, core
A = pickle.load(open('finalA.pkl', 'rb')); R1 = pd.read_pickle('real_com_nulo.pkl'); TB = pd.read_pickle('tabB.pkl')
FIL = pd.read_pickle('filtros.pkl'); RU = pd.read_pickle('ruina.pkl'); PER = pd.read_pickle('per_com_nulo.pkl')
PC = pd.DataFrame(pickle.load(open('perconf.pkl', 'rb')))
FRZ = json.load(open('congelado_ANTES_da_confirmacao.json', encoding='utf-8'))


def f(x, d=1):
    return '' if x is None or (isinstance(x, float) and not np.isfinite(x)) else (f"{x:.{d}f}".replace('.', ','))


def md(df):
    cols = list(df.columns)
    s = '| ' + ' | '.join(cols) + ' |\n|' + '|'.join(['---'] * len(cols)) + '|\n'
    for _, r in df.iterrows():
        s += '| ' + ' | '.join(str(v) for v in r.values) + ' |\n'
    return s


L = []
w = L.append
w("# Encaixe de médias entre tempos gráficos (EMA 9/21/50) no WIN — setup do dono\n")
w("Janelas: descoberta jan–jun/2026, confirmação jul–ago/2026, set/2026 como terceira. Só 2026; nov–dez/2025 só aqueceu as médias. Todo número é pts/contrato; R$0,20/pt; custo 2 pts; stop a mercado +5 pts; limite conservadora (só enche se negociar 5 pts além); mesma vela: stop vence. Código e saídas: `scripts/daytrade/win_pernadas_exploracao/rodada7/medias_multitf/`.\n")

w("## 1. Resposta curta\n")
w("""- O encaixe das médias (M5/M10 rompe, TF maior alinhado só tocando EMA9/21) **não mudou de forma sustentada a probabilidade de acerto** de uma entrada a favor. Na descoberta jan–jun achei uma região (pares M10×M30 e M5×M30, stop técnico de 5/15 velas, alinhamento estrito) com +34 a +60 pts/op em 9 regras, que passou no critério de platô e ficou 2,0–3,2 desvios acima do nulo embaralhado. **Na confirmação jul–ago as mesmas 9 regras juntas deram −20,7 pts/op (n=400) e em set −41,9 (n=263).** Só 1 de 9 (R7, M15×H1) ficou positivo nas duas janelas novas (+56 e +45 pts, IC cruza 0; na descoberta era ≈0).
- A definição literal do dono (M5 rompe as 3 médias, M15 alinhado, toque ≤0,5 ATR, stop das últimas 15 velas, alvo 5×): −17 pts/op na descoberta (n=156), −6 em jul–ago (n=55), +17 em set (n=25); todos os ICs cruzam zero. Acerto 16% contra breakeven empírico 18,5%.
- **Os períodos não importam** (achado): numa grade 3×3×3 em torno de 9/21/50 as regras mantêm o mesmo sinal em ~27/27 células na descoberta, e o resultado quase não depende do número (9/21/50 ≈ 5/17/34 ≈ 13/24/120). Só quebra com média 40 (colada à lenta 50). SMA no lugar de EMA inverte o sinal em 3 das 5 regras M10×M30 (R2, R4, R8) e reduz à metade o ganho nas outras 2 (R1, R3). Vale o par de tempos e o stop, não o número da média — e na confirmação nem isso sustentou.
- Contra a ruína do jogador e contra entradas aleatórias no mesmo horário, o encaixado fica dentro do ruído: acerto 16% × 20,5% do aleatório; esperança −17,4 × −22,1 (descoberta, referência).
- Ticks (mar–set, mesmos sinais): **idênticos ao M1** (19.114 trades, 10 diferem). O desenho exige stop ≥ 50 pts e alvo ≥ 150 pts, então a ordem dentro da vela quase nunca decide. O custo é descartar ~1/3 dos sinais (stop técnico fora de 50–500 pts).
""")

w("## 2. Definições congeladas (antes de abrir jul–ago)\n")
w("""- EMA 9/21/50 do fechamento (pandas `ewm(span, adjust=False)`) em M5, M10, M15, M30, H1 e diário (diário só no par H1×D). Barras de TF maior agrupadas a partir de 09:00; "fechada" = última barra completa; "formando" = EMA recalculada com o preço do minuto (sem look-ahead). Testei as duas.
- Tendência do TF maior: **estrita** EMA9>EMA21>EMA50 e EMA21 subindo; **frouxa** só EMA21 subindo. Sempre exigido: preço do TF maior ≥ EMA50 dele (senão é "TF maior rompendo").
- Toque: mínima das 2 últimas barras do TF maior ≤ EMA(ref) + x·ATR14(TF maior), x ∈ {0; 0,1; 0,25; 0,5; 1}, ref = EMA9 ou EMA21.
- Gatilho (aresta): 1ª barra fechada do TF menor que fecha abaixo só da EMA9 (f), EMA9 e 21 (fm) ou das três (fms). Sinal entre 09:30 e 17:00. Venda = espelho.
- Entrada: limite no fechamento da vela-gatilho, prazo 10 min (5/15 testados: sem efeito, o preço cobre 5 pts abaixo no 1º minuto), conservadora. Entrada na EMA9/21 do TF maior também testada (coluna entrada).
- Stop: mínima das últimas N velas M1 −5 (N=5,10,15,30), ou 1 tick abaixo da EMA50 do TF maior, ou k·ATR14 do M15; só vale se 50 ≤ S ≤ 500 pts. Alvo: K × S, K ∈ {3; 5; 7,5; 10}, ou máxima das últimas 12 barras do TF maior (se ≥ 3×S). Um trade por vez (ordem pendente bloqueia); long e short simulados separadamente.
- Nulos: M1 de cada pregão embaralhado em blocos de 30 min e reencadeado; **40 sorteios** nas grades 1 e 2, 30 na grade de períodos, 60 nas regras congeladas (todas as janelas). IC95% por bootstrap de dias.
""")

w("## 3. Contagem de testes e quantos passariam por acaso\n")
t = pd.DataFrame([
    ['Grade 1: eixos de 1 em 1 (períodos, SMA, toque, ruptura, tendência, variante, par, prazo, N, K, stop, entrada), mapa rápida×média (lenta 50) e grade conjunta f×m×s', '931 células (836 com n≥30)', 't≥2: 0 reais · 1,5 no nulo (máx 17); t≥1,5: 5 reais · 15,8 no nulo'],
    ['Grade 2: par(5) × ruptura(3) × toque x(4) × tendência(2) × variante(2) × stop(4) × K(3), períodos 9/21/50', '2.880 células (1.677 com n≥60)', 't≥2: 6 reais · 6,2 no nulo (máx 34); t≥1,5: 31 reais · 46,8 no nulo; fração com esperança>0: 50,3% real · 43,3% nulo'],
    ['Famílias de 12 células (x×K) com ≥10/12 positivas, média ponderada>0, n≥30', '240 famílias', '51 passam · 51,3 no nulo (min 22, máx 89): o critério de platô sozinho não discrimina. Com p≤0,05 contra o nulo da mesma família: 22 reais · ~12 esperadas por acaso'],
    ['Sensibilidade a períodos das 10 regras congeladas (56 células cada) em 3 janelas', '560 × 3', 'seção 7'],
], columns=['grade', 'células', 'passaram × passariam por acaso'])
w(md(t))
w("Total de células avaliadas na descoberta: ~4.400. Nada com t≥2 além do que o nulo gera. O **nulo embaralhado não é zero**: com stop por ATR ou alvo grande ele dá esperança positiva (atr1,0: +91 pts; referência: +8,7), porque o WIN de 2026 tem tendência e volatilidade agrupada. Por isso toda célula é comparada com a MESMA célula no nulo (coluna z).\n")

w("## 4. Comparações obrigatórias (mesma geometria: entrada no fechamento, stop 15 velas, alvo 5×)\n")
w("Esperança em pts/op [IC95% bootstrap de dias]. 'reversão' = comprar contra o rompimento do TF menor (a favor de um TF maior de alta); 'continuação' = seguir o rompimento. Aleatório = mesmo horário (±15 min), mesmo lado, mesmo número de sinais, 20 repetições.\n")
for rid, tit in (('R10', 'R10: definição literal do dono (M5×M15, três médias, estrito)'), ('R1', 'R1: M10×M30, rompe EMA9 (melhor da descoberta)')):
    rows = []
    for win in (1, 2, 3):
        tt = A['cmp'][(rid, win)]
        for _, r in tt.iterrows():
            rows.append([['desc', 'conf', 'set'][win - 1], r['grupo'], int(r['n']), f(r['por_dia'], 2), f(100 * r['acerto'], 1) + '%', f(100 * r['be_emp'], 1) + '%', f(r['esp'], 1), f"[{f(r['ic_lo'],0)} ; {f(r['ic_hi'],0)}]", f(r['payoff'], 1), int(r['seq_perdas'])])
    w(f"**{tit}**\n")
    w(md(pd.DataFrame(rows, columns=['janela', 'grupo', 'n', 'op/dia', 'acerto', 'BE emp.', 'esp pts', 'IC95%', 'ganho/perda', 'seq perdas máx'])))
w("Excursão (MFE/MAE em 30/60 min após o preenchimento) está em `cmp_out.txt` e `finalA.pkl`. No R10 da descoberta, MFE30 372 × MAE30 327 pts e MFE60 529 × MAE60 481: o preço vai para os dois lados na mesma proporção; o aleatório dá 316/326 e 441/454.\n")
w("**Pergunta direta do dono: P(nova máxima do TF maior antes de uma barra do TF maior fechar abaixo da EMA50 dele).**\n")
pv = []
for rid in ('R10', 'R1', 'R7'):
    for win in (1, 2, 3):
        p = A['pud'][(rid, win)]
        pe = p.iloc[0]; pa = p[p.grupo.str.startswith('ALEATORIO')].iloc[0]; pc = p.iloc[1]
        e = A['central'][(rid, win)]
        pv.append([rid, ['desc', 'conf', 'set'][win - 1], int(e['nev']), f(100 * e['pv'], 1) + '%', f(100 * e['pf'], 1) + '%', f(100 * e['pn'], 1) + '%', f(100 * e['pnull'], 1) + '%',
                   f(100 * pe['P_sobe'], 1) + '% × ' + f(100 * pe['P_cai'], 1) + '%', f(100 * pa['P_sobe'], 1) + '% × ' + f(100 * pa['P_cai'], 1) + '%', f(100 * pc['P_sobe'], 1) + '% × ' + f(100 * pc['P_cai'], 1) + '%'])
w(md(pd.DataFrame(pv, columns=['regra', 'janela', 'n eventos', 'volta (máx. antes)', 'falha (fecha < EMA50)', 'nenhum até o fim do dia', 'ruína dos mesmos níveis', 'padronizado: sobe × cai (encaixado)', 'aleatório', 'oposto (contra)'])))
w("Leitura: no R10 literal da descoberta, 21% voltam à máxima, 45% fecham abaixo da EMA50 do M15 antes e 33% nenhum dos dois; descontados os 'nenhum', a chance de voltar é 32% contra 44% de ruína, ou seja, **pior que o acaso**. Na versão padronizada em ATR (mesma distância para todos os grupos) o encaixado fica +2 pp acima da ruína, o aleatório −4 pp, o rompimento sem TF maior −6/+1, o encaixado 'contra' −4: diferenças menores que o erro (n≈250). Na confirmação os sinais trocam de lado (R10 conf: encaixado −11 pp, contra +11 pp).\n")

w("## 5. Curvas de sensibilidade (referência: 9/21/50 EMA, M5×M15, três médias, estrito, fechada, x=0,5, stop 15 velas, K=5; descoberta jan–jun, n≈156)\n")
w("Cada tabela mexe só um número. `nulo` = esperança da mesma célula nos 40 embaralhamentos; z = (real − nulo)/dp do nulo.\n")
ax_names = {'fast': 'EMA rápida', 'mid': 'EMA média', 'slow': 'EMA lenta', 'kind': 'tipo de média', 'x': 'toque x·ATR', 'breach': 'EMAs do TF menor que precisam ser rompidas (f=só a rápida, fm=rápida+média, fms=as três)', 'ref_touch': 'EMA do toque (f=rápida, m=média)', 'trend': 'alinhamento do TF maior',
            'var': 'TF maior fechado (c) ou formando (f)', 'triple': 'encaixe triplo (M5, M15 e H1)', 'par': 'par menor/maior em minutos (0 = diário)', 'Nstop': 'N velas do stop técnico', 'K': 'alvo K × stop', 'stop': 'tipo de stop', 'entry': 'entrada (cl = fechamento, f = EMA rápida do TF maior, m = EMA média do TF maior)', 'otim': 'preenchimento'}
for ax in ['fast', 'mid', 'slow', 'kind', 'x', 'breach', 'ref_touch', 'trend', 'var', 'triple', 'par', 'Nstop', 'K', 'stop', 'entry', 'otim']:
    s = R1[R1.axis == ax].copy()
    if ax in ('fast', 'mid', 'slow', 'x', 'Nstop'):
        s = s.sort_values('value', key=lambda c: c.astype(float))
    rows = [[str(r.value), int(r.n), f(100 * r.win, 1) + '%', f(100 * r.be, 1) + '%', f(r['mean'], 1), f"[{f(r.ci_lo,0)} ; {f(r.ci_hi,0)}]", f(r.nul_mean, 1), f(r.z, 2)] for _, r in s.iterrows()]
    w(f"**{ax_names[ax]}**\n")
    w(md(pd.DataFrame(rows, columns=['valor', 'n', 'acerto', 'BE emp.', 'esp pts', 'IC95%', 'nulo', 'z'])))
w("Leitura: (i) a rápida (5 a 15) não mexe em nada, esperança entre −27 e −17, acerto 15–17%; (ii) a média vai de −17 (21) a ≈0 (19) e volta a −10…−23 até 40, tudo dentro do ruído (IC ±50); (iii) a lenta só 'melhora' de 89 a 120, mas com n=19–42 (poucos sinais com lenta tão longa), efeito de amostra pequena; (iv) toque de 0 a 1 ATR não muda; (v) romper só a EMA9 ou a 9+21 dá mais operações e esperança positiva não significativa (+31/+21) contra as três (−17): **exigir mais médias rompidas piora**; (vi) TF maior 'formando' piora (−43); (vii) M5×M30 e M10×M30 são os melhores pares na descoberta (+30/+10), M15×H1 e M5×H1 ficam em ≈0; (viii) stop de 5 velas piora (−36) contra 15 (−17); stop ATR 1,0 dá +104 mas o nulo também dá +91 (z 0,3); (ix) prazo de 5/10/15 min é irrelevante com entrada no fechamento (n idêntico: todas enchem no 1º minuto).\n")
h = R1[R1.axis == 'heat'].copy(); ff = h.value.str.split('/', expand=True).astype(int); h['f'] = ff[0]; h['m'] = ff[1]
w("**Mapa de calor rápida × média (lenta = 50): esperança em pts/op (descoberta; n de 99 a 176 por célula)**\n")
pt = h.pivot(index='f', columns='m', values='mean').round(0)
pt.index = [f"rápida {i}" for i in pt.index]; pt.columns = [f"média {c}" for c in pt.columns]
pt = pt.map(lambda v: '' if not np.isfinite(v) else f"{v:+.0f}")
w(md(pt.reset_index().rename(columns={'index': ' '})))
w("Das 81 células, nenhuma passa de +6 pts e 77 são ≤0; z contra o nulo entre −1,3 e +0,2; acerto 14,4–18,9% (BE 17–22%). A coluna da média 19 é a menos negativa (≈0), mas é uma coluna isolada, sem platô.\n")
j = R1[R1.axis == 'joint'].copy(); fj = j.value.str.split('/', expand=True).astype(int); j['f'] = fj[0]; j['m'] = fj[1]; j['s'] = fj[2]
w("**Grade conjunta rápida × média × lenta (771 células válidas com rápida<média<lenta), agregada pela lenta**\n")
g = j.groupby('s').agg(cel=('n', 'size'), n_med=('n', 'median'), esp=('mean', 'mean'), nulo=('nul_mean', 'mean'), z=('z', 'mean'), pos=('mean', lambda x: (x > 0).mean())).reset_index()
w(md(pd.DataFrame([[int(r.s), int(r.cel), int(r.n_med), f(r.esp, 1), f(r.nulo, 1), f(r.z, 2), f(100 * r.pos, 0) + '%'] for _, r in g.iterrows()], columns=['lenta', 'células', 'n mediano', 'esp média pts', 'nulo', 'z médio', '% positivas'])))
w("Lenta ≥ 89 fica positiva, mas com n mediano 24–55 (a pilha EMA9>21>lenta tão longa quase não ocorre) e z ≤ 1,3. A melhor célula isolada da grade conjunta tem t=1,92 (n=17); nenhuma das 771 chega a t≥2 (esperado ao acaso: 1,5–2,8). A lenta 40 (+14, 94% positivas) é vizinha de 34 (−1) e 45 (−10): não é platô.\n")

w("## 6. As 10 regras congeladas (platô da descoberta): resultado nas 3 janelas\n")
w(f"Congelado em `congelado_ANTES_da_confirmacao.json` ({FRZ['congelado_em'][:19]}) **antes** de qualquer leitura de jul–ago. Seleção: famílias de 12 células (x × K) com ≥10/12 positivas, média ponderada > 0, n ≥ 30 em todas e z da família contra o nulo ≥ 1,3; famílias de stop ATR foram excluídas (o nulo delas também é positivo). R10 é o controle literal do dono. Célula central: x=0,5 ATR, K=5, EMA 9/21/50.\n")
rows = []
nm = {'R1': 'M10×M30 · rompe EMA9 · estrito · stop 15v', 'R2': 'M10×M30 · rompe 9+21 · estrito · stop 5v', 'R3': 'M10×M30 · rompe EMA9 · estrito · stop 5v', 'R4': 'M10×M30 · rompe 9+21 · frouxo · stop 5v',
      'R5': 'M5×M30 · rompe 9+21 · estrito · stop 15v', 'R6': 'M5×M30 · rompe EMA9 · estrito · stop 15v', 'R7': 'M15×H1 · rompe EMA9 · frouxo · stop 15v', 'R8': 'M10×M30 · rompe 9+21 · estrito · stop 15v',
      'R9': 'M5×M30 · rompe EMA9 · frouxo · stop = EMA50 do M30', 'R10': 'M5×M15 · rompe 9+21+50 · estrito · stop 15v (literal)'}
for rid in [f"R{i}" for i in range(1, 11)]:
    for win in (1, 2, 3):
        e = A['central'][(rid, win)]; tb = TB[(TB.regra == rid) & (TB.jan == win)].iloc[0]
        rows.append([rid if win == 1 else '', nm[rid] if win == 1 else '', ['desc', 'conf', 'set'][win - 1], int(e['n']), f(100 * e['win'], 1) + '%', f(100 * e['be'], 1) + '%', f(e['mean'], 1), f"[{f(e['ci_lo'],0)} ; {f(e['ci_hi'],0)}]",
                     f"{int(tb.m1_famPos)}/12", f(tb.m1_fam, 1), f"{f(tb.nulo,1)} ± {f(tb.nulo_sd,0)}", f(tb.z_M1, 2), f(tb.tk_esp, 1), int(tb.tk_n)])
w(md(pd.DataFrame(rows, columns=['regra', 'definição', 'janela', 'n', 'acerto', 'BE emp.', 'esp pts (M1)', 'IC95%', 'família +', 'família esp', 'nulo (60)', 'z', 'esp pts (ticks)', 'n ticks'])))
w("A coluna ticks usa só os dias com arquivo de ticks (a descoberta perde jan–fev, por isso n menor). **Agregado das 9 regras (R1–R9, centro), M1 × ticks nos dias com ticks:** descoberta +50,2 × +50,6 (n=804, com forte sobreposição entre regras, não são 804 eventos independentes); confirmação **−20,7 × −20,7** (n=400); set **−41,9 × −41,9** (n=263).\n")
w("**Platôs que replicaram: 0 de 9.** R2 e R4 ficaram positivas em 8/12 e 9/12 células da família em jul–ago (esp +16 e +18), mas caíram a 1/12 e 0/12 em set. R7 foi a única com 11/12 e 12/12 nas duas janelas novas (+56 e +45 no centro), com IC [−64 ; +228] e [−112 ; +205] e z contra o nulo de 1,5 e 0,7; na descoberta era −1 (família 11/12, média +29).\n")

w("### Regras (SE … ENTÃO …)\n")
rr = [
    ['SE o TF maior (M30; M10 ou M5 como menor) está alinhado de alta (EMA9>21>50, EMA21 subindo), o preço dele não fechou abaixo da EMA50 e o TF menor acaba de fechar abaixo da EMA9 (ou 9+21) pela 1ª vez ENTÃO comprar com limite no fechamento (prazo 10 min), stop = mínima das últimas 5–15 velas −5, alvo 5×', 'LIGA (entrada a favor), STOP, ALVO', '+34 a +60 pts/op em 9 regras; famílias 12/12', '−20,7 pts/op (n=400); 0/9 platôs; só R7 positivo', '−41,9 (n=263)', '**falhou**: era seleção sobre ruído; z de 2–3 na descoberta não sobreviveu'],
    ['SE o par é M15×H1, ruptura só da EMA9, alinhamento frouxo (só EMA21 subindo) ENTÃO mesma entrada', 'LIGA', '−1 (z 0,5)', '+56 (IC −64 ; +228)', '+45 (IC −112 ; +205)', '**pista**: 11/12 e 12/12 células positivas nas 2 janelas novas, mas n=34 e 28 e z de 1,5 e 0,7; não confirma, não recusa'],
    ['SE a definição literal do dono (M5×M15, 3 médias, toque ≤0,5 ATR) ENTÃO entrar a favor', 'LIGA?', '−17 (n=156); 2/12 células +', '−6 (n=55)', '+17 (n=25)', '**negativa/ruído**'],
    ['SE exigir que o TF menor rompa as TRÊS médias (em vez de só a EMA9 ou 9+21) ENTÃO', 'ACEITA/REJEITA', 'pior: −17 contra +31/+21 (n 156–208)', 'não testado isoladamente', '—', 'tendência na descoberta; se usar, só EMA9 ou 9+21'],
    ['SE usar SMA em vez de EMA ENTÃO', 'parâmetro', 'SMA inverte R2 (−30), R4 (−29), R8 (−40) contra +45 a +59 com EMA; em R1/R3 cai de +56/+60 a +22/+24', '—', '—', 'EMA ≥ SMA na descoberta; sem regra'],
    ['SE variar rápida (5–15), média (15–34), lenta (34–120) ENTÃO o resultado', 'parâmetro', '27/27 positivas em R1–R6 e R8: insensível; quebra só com média 40 colada à lenta', 'mesmas grades com sinal médio −69 a +38 conforme a regra', 'idem', '**insensível ao número**; o período não decide'],
    ['SE o stop é técnico (≥50 pts) ENTÃO conferir com ticks', 'STOP', 'ticks = M1 (10 de 19.114 divergem)', 'idem', 'idem', '**replicou** porque S ≥ 50'],
    ['SE horário < 11h ou vela M1 ≥ 2× ENTÃO o encaixe melhora', 'LIGA', 'R1: <11h +133, v2x +280 (n=28 e 14)', 'R1 conf+set: <11h +3 (n=23), v2x −16 (n=10)', '(junto)', '**falhou**: o efeito da descoberta some'],
    ['SE a pernada de 750 em curso é a favor / contra do trade ENTÃO', 'DIREÇÃO', 'R6: a favor +85 × contra +26 (n=84/118)', 'R6 conf+set: −35 × −34', '(junto)', '**falhou**'],
]
w(md(pd.DataFrame(rr, columns=['regra', 'papel', 'descoberta', 'confirmação jul–ago', 'set', 'status'])))

w("## 7. Sensibilidade a períodos das regras congeladas\n")
w("Grade 3×3×3 (rápida 7/9/11 × média 19/21/24 × lenta 40/50/60, EMA) por regra e janela; `nulo` é a esperança média da mesma grade nos 30 embaralhamentos da descoberta.\n")
rows = []
for rid in [f"R{i}" for i in range(1, 11)]:
    row = [rid]
    d = PER[(PER.axis == rid) & PER.value.str.match(r'P\d+/\d+/\d+$')]
    row += [f"{int((d['mean']>0).sum())}/27", f(d['mean'].mean(), 1), f(d.nm.mean(), 1), f(d['mean'].min(), 0) + ' a ' + f(d['mean'].max(), 0)]
    for wn in (2, 3):
        c = PC[(PC.axis == rid) & (PC.w == wn) & PC.value.str.match(r'P\d+/\d+/\d+$')]
        row += [f"{int((c['mean']>0).sum())}/27", f(c['mean'].mean(), 1)]
    rows.append(row)
w(md(pd.DataFrame(rows, columns=['regra', 'desc: positivas', 'desc: esp média', 'nulo', 'desc: min a max', 'conf: positivas', 'conf: esp média', 'set: positivas', 'set: esp média'])))
w("Curvas de um eixo por vez (descoberta; esperança em pts/op e n entre parênteses):\n")
for rid in ('R1', 'R2', 'R5'):
    w(f"**{rid}**\n")
    r = PER[PER.axis == rid]
    lines = []
    for pre, lab in (('fast', 'rápida'), ('mid', 'média'), ('slow', 'lenta')):
        s = r[r.value.str.startswith(pre)].copy(); s['v'] = s.value.str[len(pre):].astype(int); s = s.sort_values('v')
        lines.append(f"- {lab}: " + ' · '.join(f"{int(a)}: {m:+.0f} ({int(n)})" for a, m, n in zip(s.v, s['mean'], s.n)))
    w('\n'.join(lines) + '\n')
w("Em R1, R2 e R5 a esperança é positiva em quase toda a faixa de rápida e de lenta (planalto na descoberta), mas o planalto não existe fora da amostra em que foi escolhido. Média = 40 (colada à lenta 50) é o único ponto que inverte (−45 e −33). Na confirmação (jul–ago), R2/R4 seguem positivas em 24/27 e 26/27 células; em set caem a 0/27: o sinal oscila com a janela, não com o período.\n")

w("## 8. Filtros cruzados (horário, vela M1 ≥ 2×, pernada de 750)\n")
sel = FIL[(FIL.regra.isin(['R1', 'R6', 'R7', 'R10']))]
rows = [[r.regra, r.janela, r.filtro, r.grupo, int(r.n), f(100 * r.acerto, 1) + '%', f(100 * r.be, 1) + '%', f(r.esp, 1)] for _, r in sel.iterrows()]
w(md(pd.DataFrame(rows, columns=['regra', 'janela', 'filtro', 'grupo', 'n', 'acerto', 'BE emp.', 'esp pts'])))
w("Sem estabilidade entre descoberta e confirmação (cada célula tem n ≤ 50 depois da divisão e nenhum filtro mantém o sinal). Não ligar nenhum.\n")

w("## 9. Tamanho de mão e risco de ruína a partir de R$250 (1 contrato; `rodada4/decisao/motor.py`)\n")
w("Esperança na janela (pts e R$ a R$0,20/pt), perda média por operação perdida, p encolhido (n0=100) para a base, mão = `motor.tamanho` (Kelly 1/4 com teto de pior caso 25%), ruína = Monte Carlo de 215 operações com piso R$100.\n")
rows = [[r.regra, r.janela, int(r.n), f(r.esp_pts, 1), f(r.esp_R, 2), int(r.S_med), f(r.perda_R, 1), f(r.p_encolhido, 3), int(r.mao), f(100 * r.ruina_215ops, 0) + '%', int(r.seq_perdas)] for _, r in RU.iterrows()]
w(md(pd.DataFrame(rows, columns=['regra', 'janela', 'n', 'esp pts', 'esp R$', 'stop médio pts', 'perda R$/op', 'p encolhido', 'mão', 'ruína 215 ops', 'seq. perdas máx'])))
w("Na confirmação+set agregada, 6 das 10 têm esperança ≤ 0 (mão 0, ruína 100%) e 3 têm ruína ≥ 83%; R7 é a única positiva com mão 1 e ainda 55% de ruína em 215 operações (acerto ~18–19%, 13 perdas seguidas). A R$250 só cabe 1 contrato e uma perda (R$23–53) já é 9–21% do caixa.\n")

w("## 10. Veredito\n")
w("""1. **O encaixe muda a probabilidade de acerto de uma entrada a favor?** Na descoberta, em 9 regras, parecia (+34 a +60 pts/op, acerto 23–34% contra BE 17–22%, 2–3 desvios acima do nulo). Na confirmação e em set, **não**: juntas dão −21 e −42 pts/op, acerto 15% e 12%. A definição literal do dono nunca saiu do ruído (−17, −6, +17, ICs de ±70).
2. **Quanto?** Se existe, é menor do que a janela consegue ver: com ~1 operação/dia e 25–80 operações por janela, o IC95% é de ±70 a ±120 pts/op. Não é mensurável com os dados de 2026.
3. **Paga o custo?** Nenhuma célula confirmou esperança positiva estável. R7 (M15×H1, rompe EMA9, alinhamento frouxo) foi a única a não falhar nas duas janelas novas e merece ≥150 operações novas antes de qualquer decisão.
4. **Períodos:** o resultado é insensível ao número exato (9/21/50 ≈ 5/17/34 ≈ 13/24/120). Importam o par de tempos, o stop técnico e quantas médias o TF menor precisa romper (menos é melhor). SMA × EMA: sem efeito consistente.
5. **Tese do dono ("é só um recuo, não um rompimento")**: o rompimento do TF menor SEM o TF maior alinhado dá −13 a −4 pts em reversão e +1 a −21 em continuação; o TF maior também rompendo é o pior grupo na descoberta (−38 a −49). O TF maior alinhado não faz o recuo do M5 virar uma entrada melhor que o acaso.
6. **Em aberto:** R7. Qualquer uso exige pregões novos (após 01/10) e leitura sempre contra o nulo da MESMA célula (o nulo embaralhado do WIN-2026 é positivo para stops largos).
""")
w("## 11. Limitações\n")
w("""- 1 a 1,7 operações/dia e 25–80 por janela de confirmação: ICs cruzam zero em quase tudo. O resultado negativo também tem IC largo (só R5 em conf [−116 ; −8] e set [−157 ; −3] exclui zero).
- Sinais com stop técnico fora de 50–500 pts são descartados (~34% na referência): a regra só vale na faixa aceita.
- Long e short simulados com posição independente por lado; R1–R9 compartilham sinais (não são independentes).
- Diário: ~40 barras de aquecimento (nov–dez/2025), EMA50 diária não convergida; par H1×D com 3–10 sinais, sem conclusão.
- WIN@D é série ajustada por diferença; ticks alinhados por deslocamento diário (desvio ≈0,6 pt).
- Fora dos mapas: o semanal não foi testado (opcional).
""")
open('C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/relatorios_rodada7/medias_multitf.md', 'w', encoding='utf-8').write('\n'.join(L))
print('ok', len('\n'.join(L)))
