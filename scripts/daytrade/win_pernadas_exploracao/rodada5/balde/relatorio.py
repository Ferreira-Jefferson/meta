import sys, json, pickle; sys.path.insert(0, '.')
from agg import *
from balde_core import PARES, TRIGS, DIRS, ALVOS, STOPS, load_days
import ruido

r = carrega(); names = r['names']; months = r['months']
F = r[False]['F']; Fo = r[True]['F']
W = {w: wmask(months, w) for w in ('desc', 'conf', 'ref')}
M = {w: metricas(F, W[w]) for w in W}; Mo = {w: metricas(Fo, W[w]) for w in W}
nu = pickle.load(open('nulo_res.pkl', 'rb'))['res']
rows = pickle.load(open('conf_rows.pkl', 'rb')); RU = pickle.load(open('ruina_res.pkl', 'rb'))
fr = json.load(open('congelado_ANTES_da_confirmacao.json'))
L = []


def p(s=''): L.append(s)


def f1(x, d=1):
    return '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}".replace('.', ',')


def tab(headers, rws):
    p('| ' + ' | '.join(headers) + ' |'); p('|' + '---|' * len(headers))
    for x in rws: p('| ' + ' | '.join(str(v) for v in x) + ' |')
    p()


nF = 696
df = pd.DataFrame(dict(key=[str(n[0]) for n in names], kind=[n[0][0] for n in names], trig=[n[1] for n in names], dir=[n[2] for n in names]))
for w in M:
    for k in ('nf', 'mean', 't', 'win', 'be', 'streak', 'opsdia', 'fill'): df[f'{k}_{w}'] = M[w][k]
    df[f'mean_otim_{w}'] = Mo[w]['mean']
df.to_csv('celulas.csv', index=False, sep=';', decimal=',')

p('# Balde: stop curto, alvo longo no WIN ("perder de colherinha, ganhar de balde")')
p()
p('Janelas: descoberta jan–jun/2026 (122 pregões), confirmação jul–ago/2026 (44 pregões), referência set/2026. Nada antes de 2026.')
p()
p('## Execução e método')
p('- Entrada: limite no fechamento da vela-gatilho, válida por 5 barras M1. Enche só se o preço negociar 1 tick (5 pts) além do limite (conservador) ou ao tocar (otimista, mostrada ao lado). Alvo: limite; conservador exige máxima ≥ alvo+5, otimista ao toque. Stop a mercado com 5 pts de deslize; custo 2 pts/op; fim do pregão às 17:50 a mercado (−5 −2). Na mesma vela M1 o stop vence o alvo; na vela do preenchimento só vale o stop (alvo a partir da seguinte). Um trade por vez (ordem pendente também bloqueia). Nenhuma geometria com alvo < 3× o stop.')
p('- Grade: stop {50, 75, 100, 150, 200, 250} × alvo {300, 400, 600, 750, 1000, 1500} com alvo ≥ 3× stop = 29 pares. Gatilhos: sem filtro; hora < 11h; vela M1 com range ≥ 2× o médio do mesmo minuto nos 20 pregões anteriores (v2x); onda de volatilidade (range das 30 últimas velas ≥ 1,5× o esperado para o trecho); h<11 e v2x; v2x e onda. Direção: (a) moeda (nulo), (b) pernada em curso (zigzag de 750), (c) a favor da vela-gatilho, (d) contra a vela-gatilho.')
p('- Gestão: fixa (F); mover o stop para a entrada depois de +1× ou +2× o stop (BE1, BE2); parcial de metade em T/2 com stop da outra metade na entrada (P). Stop por volatilidade (V: 0,3 ou 0,5 × range M1 médio do horário, mínimo 50, alvo 4× ou 7,5×); stop técnico (TC: além da mínima/máxima das 5 ou 15 últimas velas, só se couber entre 50 e 400 pts, alvo 4× ou 7,5×).')
p('- Células: 31 variantes de geometria/gestão × 6 gatilhos × 4 direções = 2.976 células na descoberta (cada uma também na confirmação e em set/26). Nulo: 40 repetições com as velas M1 embaralhadas em blocos de 30 min nas 696 células de geometria fixa. IC por bootstrap de DIAS (2.000 reamostragens); t por razão agrupada por dia. A ordem fina dentro do minuto não foi testada com ticks (stop e entrada na mesma vela contam como stop).')
p()
p('## 1. Nulo e superfícies')
p('Esperança por operação (pts), média sobre as 696 células de geometria fixa; fração de células com esperança > 0; maior t.')
rws = []
for w in ('desc', 'conf', 'ref'):
    mr = M[w]['mean'][:nF]; mn = np.nanmean(nu[w]['mean'], axis=0)
    rws.append([w, f1(np.nanmean(mr)), f1(np.nanmean(mn)), f1(100 * (mr > 0).mean()) + '%', f1(100 * (nu[w]['mean'] > 0).mean()) + '%', f1(np.nanmax(M[w]['t'][:nF]), 2), f1(np.nanpercentile(np.nanmax(nu[w]['t'], axis=1), 95), 2)])
tab(['janela', 'real', 'nulo', 'real >0', 'nulo >0', 'maior t real', 'maior t nulo (p95)'], rws)
p('Na descoberta, 0 das 2.976 células têm t ≥ 3; o maior t é 2,48 (50/1000, v2x&onda, contra a vela), dentro do que o nulo produz em 696 células (p95 do máximo = 2,64). A esperança média da grade é negativa em todas as janelas e mais negativa que a do nulo (−14,2 contra −11,9 na descoberta): na ordem real das velas o ruído de 1 minuto varre os stops curtos mais do que na ordem embaralhada.')
p()
p('Esperança média (pts) por gatilho × direção, geometria fixa, descoberta / confirmação:')
f = df[df.kind == 'F']
rws = []
for tg in TRIGS:
    rr = [tg]
    for dn in DIRS:
        s = f[(f.trig == tg) & (f.dir == dn)]
        rr.append(f"{f1(s.mean_desc.mean())} / {f1(s.mean_conf.mean())}")
    rws.append(rr)
tab(['gatilho'] + DIRS, rws)
p('Média por gestão (todas as células, pts por operação; % de células positivas na descoberta):')
g = df[df.kind.isin(['F', 'BE', 'P'])].copy(); g['kk'] = g.key.map(lambda k: eval(k)[0] + (str(eval(k)[3]) if eval(k)[0] == 'BE' else ''))
rws = [[k] + [f1(g[g.kk == k][f'mean_{w}'].mean()) for w in ('desc', 'conf', 'ref')] + [f1(100 * (g[g.kk == k]['mean_desc'] > 0).mean()) + '%'] for k in ('F', 'BE1', 'BE2', 'P')]
rws += [[{'V': 'V (stop por volatilidade)', 'TC': 'TC (stop técnico)'}[k]] + [f1(df[df.kind == k][f'mean_{w}'].mean()) for w in ('desc', 'conf', 'ref')] + [f1(100 * (df[df.kind == k]['mean_desc'] > 0).mean()) + '%'] for k in ('V', 'TC')]
tab(['gestão/stop', 'desc', 'conf', 'set', '% células >0 (desc)'], rws)
p('Nenhuma gestão muda o sinal da esperança. Mover o stop para a entrada e a parcial deixam o ganho médio menor, sem criar vantagem; o stop por volatilidade piora (1% das células positivas); o stop técnico é o único grupo menos negativo, só nos gatilhos de volatilidade e sem significância (seção 4).')
p()
p('### Superfícies stop × alvo (geometria fixa; esperança em pts, descoberta | confirmação; n = operações da descoberta)')
for tg in TRIGS:
    for dn in DIRS:
        p(f'**{tg} · {dn}**')
        p()
        rws = []
        for s in STOPS:
            rr = [str(s)]
            for t in ALVOS:
                if t < 3 * s: rr.append('·'); continue
                i = names.index((('F', s, t), tg, dn))
                rr.append(f"{f1(M['desc']['mean'][i], 0)} \\| {f1(M['conf']['mean'][i], 0)} (n{int(M['desc']['nf'][i])})")
            rws.append(rr)
        tab(['stop \\ alvo'] + [str(t) for t in ALVOS], rws)
p('Todas as 2.976 células (win%, breakeven empírico, t, maior sequência de perdas, esperança otimista, set/26) estão em `celulas.csv`.')
p()
p('## 2. Quanto o ruído varre um stop de 100 pts (100/750, sem filtro, direção aleatória, jan–ago)')
days = load_days()
rg = {}
for d in days:
    if d['month'] <= 8:
        for mm, rr_ in zip(d['m'], d['h'] - d['l']): rg.setdefault((mm - 540) // 30, []).append(rr_)
t = ruido.tab(100, 750, 'none', 'a_aleat')
t['range_M1'] = [np.mean(rg[(int(b[:2]) - 9) * 2 + int(b[3:]) // 30]) for b in t.bloco]
rws = [[x.bloco, x.n, f1(x.range_M1, 0), f1(x.stop_ate1bar) + '%', f1(x.stop_ate5bar) + '%', f1(x.stop_pct) + '%', f1(x.alvo_pct) + '%', f1(x.nulo_alvo) + '%', f1(x['mean'], 0)] for _, x in t.iterrows()]
tab(['bloco', 'n', 'range M1 médio', 'stop em ≤1 barra do preenchimento', 'stop em ≤5 barras', 'stop até o fim', 'alvo 750 atingido', 'nulo S/(S+T)', 'esperança pts'], rws)
p('Um stop de 100 pts é varrido na vela do preenchimento ou na seguinte em 49–59% das operações antes das 11h30 e em 28–38% depois das 13h; em 5 minutos, 70–77% de manhã e 48–62% à tarde. A frequência do alvo de 750 fica ao redor do nulo de 11,8% (9–13% de manhã; 13–21% depois das 15h30, com n de 190–240 por bloco). A esperança só é positiva em blocos isolados (erro padrão de ~10 pts em n≈700), sem consistência entre blocos vizinhos. O stop morre por ruído em ~89% das operações: 107 pts de perda contra 742 de ganho exigem acerto de 12,6% e o mercado entrega 10–11% de manhã.')
for (S, T) in [(50, 400), (150, 1000), (250, 1500)]:
    t2 = ruido.tab(S, T, 'none', 'a_aleat')
    p(f'- {S}/{T}: stop em ≤1 barra após o preenchimento = {t2.stop_ate1bar.iloc[:5].mean():.0f}% (09:00–11:30) e {t2.stop_ate1bar.iloc[-6:].mean():.0f}% (14:30–17:30); alvo atingido {t2.alvo_pct.mean():.1f}% (nulo {S / (S + T) * 100:.1f}%).')
p()
p('## 3. Congelamento (antes de olhar jul–ago)')
p(f"Arquivo `congelado_ANTES_da_confirmacao.json` (gravado {fr['congelado_em'][:19]}). Critério: as 12 células de maior t na descoberta (n ≥ 150, execução conservadora) mais as 3 melhores 100/750. Nenhuma atingiu t ≥ 3: são os melhores candidatos, não regras sustentadas, e o nulo diz que o maior t esperado por acaso em 696 células é 1,8–2,6.")
p()
p('## 4. Descoberta × confirmação das células congeladas')
rws = []
for x in rows:
    d, c, s = x['desc'], x['conf'], x['ref']
    rws.append([x['cel'].replace('(', '').replace(')', ''),
                f"{d['n']} / {f1(100 * d['win'])}% × {f1(100 * d['be'])}% / {f1(d['mean'])} [{f1(d['lo'], 0)}; {f1(d['hi'], 0)}] / t {f1(d['t'], 2)}",
                f"{c['n']} / {f1(100 * c['win'])}% × {f1(100 * c['be'])}% / {f1(c['mean'])} [{f1(c['lo'], 0)}; {f1(c['hi'], 0)}] / t {f1(c['t'], 2)}",
                f"{c['streak']:.0f} (p95 iid {c['streak_p95']:.0f})", f1(c['mean_otim']), f"{f1(s['mean'])} (n{s['n']})"])
tab(['célula', 'desc: n / acerto × breakeven / esperança pts [IC95 dias] / t', 'conf: idem', 'conf: maior seq. de perdas', 'conf otimista', 'set'], rws)
p('Leitura: 13 das 15 células invertem de sinal na confirmação (as de stop 50–250, alvo 750–1500, contra a vela, perdem de 14 a 49 pts por operação em jul–ago). A referência do dono (100/750 com h<11 e v2x, contra a vela) fica em −1 pt/op na descoberta e −54 pts/op na confirmação (IC95 [−82; −23], t −3,4), −48 em set. As duas que não invertem são do grupo stop técnico em v2x&onda: TC 15/7,5 aleatória (positiva nas três janelas, 21 operações na confirmação, IC −154 a +312 pts) e TC 5/7,5 contra a vela (+17 na confirmação com 38 operações, IC −116 a +210; −3 em set). Não confirma nem refuta.')
p()
p('Grupo TC nos gatilhos de volatilidade (esperança pts/op; descoberta | confirmação | set):')
tcm = df[df.kind == 'TC']
rws = []
for _, x in tcm.sort_values('t_desc', ascending=False).iterrows():
    if x.trig in ('v2x', 'v2x&onda', 'h<11&v2x') and x.nf_desc >= 100:
        rws.append([f"{x.key} {x.trig} {x.dir}", f"{f1(x.mean_desc, 0)} (n{int(x.nf_desc)}) \\| {f1(x.mean_conf, 0)} (n{int(x.nf_conf)}) \\| {f1(x.mean_ref, 0)} (n{int(x.nf_ref)})"])
tab(['célula TC', 'pts/op'], rws[:12])
p('## 5. Quantas vezes se pode perder, risco de ruína e capital')
p('Motor `rodada4/decisao/motor.py`: R$ 0,20/pt, 1 contrato, ruína = caixa < R$ 100 (margem crua), 250 pregões, distribuição = operações de jan–ago da célula (reamostradas), 3.000 caminhos. As distribuições são in-sample e as células foram escolhidas depois de ver os dados: otimistas. Nas células de esperança negativa, o capital "para ruína ≤ 5%" só adia a perda: a última coluna mostra a perda esperada no horizonte.')
rws = []
for nm, x in RU.items():
    rws.append([nm, x['n'], f1(x['opd'], 1), f1(100 * x['win']) + '%', f1(x['mean_pts']) + ' pts / R$ ' + f1(x['mean_brl'], 2), f1(x['loss_med_brl'], 2), f"{x['streak_p95']:.0f}",
                f1(100 * x['ruina'][250], 0) + '%', (('R$ ' + f"{x['cap_5pct']:,}".replace(',', '.')) if x['cap_5pct'] else '> R$ 50.000'),
                'R$ ' + f1(x['mean_brl'] * x['opd'] * 250, 0)])
tab(['célula (jan–ago)', 'n', 'ops/dia', 'acerto', 'esperança/op', 'perda típica R$', 'seq. de perdas p95 (250 pregões)', 'ruína de R$250', 'capital p/ ruína ≤ 5%', 'resultado esperado em 250 pregões'], rws)
open('../../relatorios_rodada5/balde.md', 'w', encoding='utf-8').write('\n'.join(L))
print('ok', len(L))
