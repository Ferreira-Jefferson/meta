import json, pickle, datetime, pandas as pd, numpy as np
import rules
r2 = pd.read_pickle('real2_com_nulo.pkl'); F = pd.read_pickle('fam.pkl')
out = dict(congelado_em=str(datetime.datetime.now()),
  janelas="descoberta jan-jun/2026 (win=1); confirmacao jul-ago/2026 (win=2) ainda NAO aberta; set/2026 (win=3) NAO aberta",
  criterio="grade de nao-periodos (2880 celulas, periodos fixos EMA 9/21/50), familias de 12 celulas (x em {0,1;0,25;0,5;1} x K em {3;5;7,5}); "
           "so entram familias com >=10/12 celulas positivas, media ponderada >0, n>=30 em todas e z_fam>=1,3 vs nulo embaralhado (40 sorteios), "
           "mais R10 = controle literal do dono. Sensibilidade a periodos (grade 3x3x3 + 3 eixos) rodada so na descoberta: nao alterou nenhuma regra.",
  definicoes=dict(periodos="EMA 9/21/50 do fechamento em todos os TFs", tendencia_strict="EMA9>EMA21>EMA50 e EMA21 subindo; loose = so EMA21 subindo (preco>=EMA50 sempre exigido)",
    toque="minima das 2 ultimas barras do TF maior <= EMA(media 'm'=21, ou rapida 'f'=9 conforme 'ref')+x*ATR14; preco do TF maior >= EMA50 do TF maior",
    gatilho="aresta: primeira barra FECHADA do TF menor que fecha abaixo de [f]=EMA9 | [fm]=EMA9 e 21 | [fms]=as tres, depois de uma barra que nao estava",
    variante_c="valores do TF maior da ultima barra FECHADA; f = formando (EMA com o preco do minuto)", horario_sinal="09:30-17:00",
    entrada="limite no fechamento da vela-gatilho, prazo 10 min, conservador (enche so se negociar 5 pts abaixo)",
    stop="x5/x15 = minima das ultimas 5/15 velas M1 - 5 pts; e50h = 1 tick abaixo da EMA50 do TF maior; valido se 50<=S<=500 pts; mercado, +5 pts de deslize",
    alvo="K x stop, limite (conservador: high >= alvo+5), K celula central=5", custo="2 pts/op", mesma_vela="stop vence; na vela do preenchimento so o stop", fim_do_dia="mercado (-5-2)"),
  regras=[])
for fam in rules.FAMS:
    rid = fam[0]; key = f"{fam[1][0]}/{fam[1][1]}|{fam[2]}|{fam[3]}|{fam[4]}|{fam[5]}"
    c = r2.loc[f"{fam[1][0]}/{fam[1][1]}|{fam[2]}|0.5|{fam[3]}|{fam[4]}|{fam[5]}|K5"]
    f = F.loc[key]
    out['regras'].append(dict(id=rid, par=f"M{fam[1][0]}/{'M30' if fam[1][1]==30 else 'M15' if fam[1][1]==15 else 'H1'}", ltf_min=fam[1][0], htf_min=fam[1][1], ruptura=fam[2], tendencia=fam[3], variante=fam[4], stop=fam[5],
       celula_central="x=0,5 ATR; K=5; EMA 9/21/50", plato="12 celulas x,K", descoberta=dict(n=int(c.n), esperanca_pts=round(float(c['mean']), 1), acerto=round(float(c.win), 3), be=round(float(c.be), 3), z_vs_nulo=round(float(c.z), 2),
          fam_pos=int(f.pos), fam_wmean=round(float(f.wmean), 1), fam_nulo=round(float(f.nul_wmean), 1), fam_z=round(float(f.z_fam), 2))))
json.dump(out, open('congelado_ANTES_da_confirmacao.json', 'w'), indent=1, ensure_ascii=False)
print(json.dumps(out['regras'], ensure_ascii=False)[:1500])
