"""Registro das perguntas: (id, origem, texto, familia, regua, tipo, esperada, fonte, exp, fn, lado)
fn(F, S) -> codigos int8 (compra da visao). exp = codigo da resposta esperada. lado=False -> pergunta sem lado (nao direcional).
"""
import numpy as np, pandas as pd
from bq_core import cod, nn, cat, filtros, dados

SIM, NAO = 1, 0
R = []

def Q(id, origem, texto, fam, regua, tipo, esperada, fonte, exp, fn, lado=True):
    R.append(dict(id=id, origem=origem, texto=texto, fam=fam, regua=regua, tipo=tipo, esperada=esperada, fonte=fonte, exp=exp, fn=fn, lado=lado))

def N(F, *ks): return [F[k].to_numpy(float) for k in ks]
def grp(F, s, fn):
    return s.groupby(F["c"].index.normalize()).transform(fn)

# ------------------------------------------------------------------ NOVAS
# VWAP / perfil de volume
Q("N01", "nova", "O preço está acima do VWAP do dia?", "VWAP/perfil", "fechamento M15 > VWAP acumulado do dia (preço típico x volume)", "sim/não", "sim", "VWAP é a referência institucional do dia; acima = compradores no controle do custo médio", SIM,
  lambda F, S: cod(F["c"] > F["vwap"], nn(F["c"], F["vwap"])))
Q("N02", "nova", "O preço está esticado em relação ao VWAP (mais de 1,5 ATR acima)?", "VWAP/perfil", "(fechamento − VWAP)/ATR M15 > 1,5", "sim/não", "não", "esticamento em relação à média ponderada tende a devolver (reversão à média)", NAO,
  lambda F, S: cod((F["c"] - F["vwap"]) / F["a"] > 1.5, nn(F["c"], F["vwap"], F["a"])))
Q("N03", "nova", "O VWAP está inclinado a favor?", "VWAP/perfil", "VWAP agora > VWAP 4 velas atrás (mesmo pregão)", "sim/não", "sim", "VWAP subindo = fluxo comprador persistente (Dalton/Grimes)", SIM,
  lambda F, S: cod(F["vwap"] > F["vwap"].shift(4), nn(F["vwap"], F["vwap"].shift(4)) & (F["tod"].to_numpy() >= 4)))
Q("N04", "nova", "O preço acabou de retomar o VWAP por cima (estava abaixo nas últimas 3 velas)?", "VWAP/perfil", "fechou > VWAP e alguma das 3 velas anteriores fechou <= VWAP", "sim/não", "sim", "retomada de nível-chave com sustentação (Wyckoff/Brooks: failed breakdown)", SIM,
  lambda F, S: cod((F["c"] > F["vwap"]) & ((F["c"].shift(1) <= F["vwap"].shift(1)) | (F["c"].shift(2) <= F["vwap"].shift(2)) | (F["c"].shift(3) <= F["vwap"].shift(3))), nn(F["c"], F["vwap"]) & (F["tod"].to_numpy() >= 3)))
Q("N05", "nova", "O preço está acima do ponto de controle (POC) do dia?", "VWAP/perfil", "POC = faixa de 100 pts com mais volume acumulado no dia; fechamento > POC (a partir das 10:00)", "sim/não", "sim", "Market Profile: preço acima do POC = aceitação em valores mais altos", SIM,
  lambda F, S: cod(F["c"] > F["poc"], nn(F["c"], F["poc"]) & (F["tod"].to_numpy() >= 4)))
def _q_va(F, S):
    c, hi, lo = N(F, "c", "pvah", "pval"); return cat(np.where(c > hi, 2.5, np.where(c < lo, 0.5, 1.5)), [1, 2], nn(c, hi, lo))
Q("N06", "nova", "Onde o preço está em relação à área de valor de ontem?", "VWAP/perfil", "área de valor = 70% do volume de ontem em torno do POC; 0 = abaixo, 1 = dentro, 2 = acima", "categoria (3)", "acima (2)", "Dalton: aceitação acima do valor de ontem favorece continuidade de alta", 2, _q_va)
def _q_ab(F, S):
    dop, hi, lo = N(F, "dop", "pdh", "pdl"); return cat(np.where(dop > hi, 2.5, np.where(dop < lo, 0.5, 1.5)), [1, 2], nn(dop, hi, lo))
Q("N07", "nova", "A abertura do dia ficou dentro ou fora da faixa de ontem?", "Níveis de ontem", "abertura do pregão vs máxima/mínima de ontem; 0 = abaixo da mínima, 1 = dentro, 2 = acima da máxima", "categoria (3)", "acima (2)", "Dalton: abertura fora da faixa anterior = convicção direcional", 2, _q_ab)
Q("N08", "nova", "O preço rompeu a máxima de ontem e sustenta (2 fechamentos acima)?", "Níveis de ontem", "fechamento e fechamento anterior > máxima de ontem", "sim/não", "sim", "Dow/Murphy: rompimento só vale com confirmação de fechamento", SIM,
  lambda F, S: cod((F["c"] > F["pdh"]) & (F["c"].shift(1) > F["pdh"]), nn(F["c"], F["pdh"]) & (F["tod"].to_numpy() >= 1)))
Q("N09", "nova", "O preço perdeu a mínima de ontem (fechou abaixo)?", "Níveis de ontem", "fechamento < mínima de ontem", "sim/não", "não", "perda de suporte do dia anterior sinaliza fraqueza (Murphy)", NAO,
  lambda F, S: cod(F["c"] < F["pdl"], nn(F["c"], F["pdl"])))
def _q_spring(F, S):
    c, pdl = N(F, "c", "pdl")
    mn = F["l"].groupby(F["c"].index.normalize()).transform(lambda s: s.rolling(8, min_periods=1).min()).to_numpy(float)
    return cod((mn < pdl) & (c > pdl), nn(c, pdl) & (F["tod"].to_numpy() >= 1))
Q("N10", "nova", "Houve rompimento falso para baixo da mínima de ontem (rompeu e voltou) nas últimas 8 velas?", "Níveis de ontem", "mínima das últimas 8 velas do dia < mínima de ontem e fechamento atual > mínima de ontem", "sim/não", "sim", "Wyckoff (spring) e Brooks (failed breakout): armadilha de vendedores", SIM, _q_spring)
Q("N11", "nova", "Ontem o preço fechou no terço superior da própria faixa?", "Dias anteriores", "(fech. − mín.)/(máx. − mín.) de ontem ≥ 0,67", "sim/não", "sim", "fechamento perto da máxima tende a continuar no dia seguinte (Crabel, L. Williams)", SIM,
  lambda F, S: cod((F["pdc"] - F["pdl"]) / (F["pdh"] - F["pdl"]) >= 0.67, nn(F["pdc"], F["pdl"], F["pdh"])))
Q("N12", "nova", "Ontem foi dia de alta (fechou acima da abertura)?", "Dias anteriores", "fechamento de ontem > abertura de ontem", "sim/não", "sim", "momentum diário (série temporal) persiste no curto prazo", SIM,
  lambda F, S: cod(F["pdc"] > F["pdo"], nn(F["pdc"], F["pdo"])))
Q("N13", "nova", "O mercado fechou 3 dias seguidos contra a operação?", "Dias anteriores", "3 fechamentos diários consecutivos de queda (compra)", "sim/não", "sim", "Connors/Alvarez: série de 3 dias contra tende a reverter no curto prazo", SIM,
  lambda F, S: cod(F["tresq"] == 1, nn(F["tresq"])))
Q("N14", "nova", "Ontem foi um inside day (faixa dentro da faixa de anteontem)?", "Volatilidade/regime", "máx. de ontem < máx. de anteontem e mín. de ontem > mín. de anteontem", "sim/não", "sim", "Crabel: contração diária precede expansão (sem direção)", SIM,
  lambda F, S: cod((F["pdh"] < F["pd2h"]) & (F["pdl"] > F["pd2l"]), nn(F["pdh"], F["pd2h"], F["pdl"], F["pd2l"])), lado=False)
Q("N15", "nova", "Ontem foi o dia de menor faixa dos últimos 7 (NR7)?", "Volatilidade/regime", "faixa de ontem é a menor das 7 últimas faixas diárias", "sim/não", "sim", "Crabel (NR7): dia estreito antecede expansão (sem direção)", SIM,
  lambda F, S: cod(F["nr7"] == 1, nn(F["nr7"])), lado=False)
Q("N16", "nova", "O preço está acima da abertura da semana?", "Níveis de referência", "fechamento > primeira abertura da semana", "sim/não", "sim", "referência semanal (Murphy/Grimes): lado do preço vs abertura do período", SIM,
  lambda F, S: cod(F["c"] > F["wop"], nn(F["c"], F["wop"])))
Q("N17", "nova", "O preço está acima da abertura do mês?", "Níveis de referência", "fechamento > primeira abertura do mês", "sim/não", "sim", "referência mensal; já apareceu como única pista de regime mensal no projeto", SIM,
  lambda F, S: cod(F["c"] > F["mop"], nn(F["c"], F["mop"])))
Q("N18", "nova", "O preço superou a máxima dos últimos 10 dias?", "Tendência/momentum", "fechamento > máxima dos 10 pregões anteriores", "sim/não", "sim", "Donchian/Turtle: rompimento de canal de 10 dias (Murphy)", SIM,
  lambda F, S: cod(F["c"] > F["h10"], nn(F["c"], F["h10"])))
Q("N19", "nova", "O preço está acima da média simples de 20 dias?", "Tendência/momentum", "fechamento > média dos 20 fechamentos diários até ontem", "sim/não", "sim", "Dow/Murphy: tendência primária pelo lado da média de 20 dias", SIM,
  lambda F, S: cod(F["c"] > F["dmm20"], nn(F["c"], F["dmm20"])))
Q("N20", "nova", "O mercado subiu nos últimos 5 dias (momentum diário)?", "Tendência/momentum", "fechamento de ontem > fechamento de 6 dias atrás", "sim/não", "sim", "Moskowitz-Ooi-Pedersen: momentum de série temporal", SIM,
  lambda F, S: cod(F["mom5"] > 0, nn(F["mom5"])))
Q("N21", "nova", "O preço está acima da média simples de 200 velas M15?", "Tendência/momentum", "fechamento > MMS200 do M15 (~7 pregões)", "sim/não", "sim", "Murphy: média longa como filtro de tendência", SIM,
  lambda F, S: cod(F["c"] > F["m200"], nn(F["c"], F["m200"])))
def _q_pos(F, S):
    c, hi, lo, ad = N(F, "c", "dhi", "dlo", "ad"); r = (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan)
    return cat(r, [1/3, 2/3], nn(r, ad) & ((hi - lo) >= 0.25 * ad) & (F["tod"].to_numpy() >= 4))
Q("N22", "nova", "Em que terço da faixa do dia o preço está?", "Posição no dia", "(fech. − mín. do dia)/(máx. − mín. do dia); 0 = inferior, 1 = meio, 2 = superior (faixa ≥ 0,25 ATR diário, após 10:00)", "tercil (3)", "superior (2)", "Brooks/Grimes: fechar perto da máxima do dia = pressão compradora (trend day)", 2, _q_pos)
def _q_desl(F, S):
    c, dop, ad = N(F, "c", "dop", "ad"); x = (c - dop) / ad; return cat(x, [-0.4, 0.4], nn(x))
Q("N23", "nova", "Quanto o preço se deslocou desde a abertura, em ATR diário?", "Posição no dia", "(fech. − abertura do dia)/ATR diário; 0 = contra (≤ −0,4), 1 = neutro, 2 = a favor (≥ +0,4)", "faixa (3)", "a favor (2)", "Gao et al. 2018 / momentum intradiário: o dia tende a continuar na direção já feita", 2, _q_desl)
Q("N24", "nova", "O preço fechou acima da faixa dos primeiros 60 minutos (ORB)?", "Faixa inicial", "fechamento > máxima de 09:00–10:00 (só após 10:00)", "sim/não", "sim", "Crabel (Opening Range Breakout)", SIM,
  lambda F, S: cod(F["c"] > F["orh"], nn(F["c"], F["orh"]) & (F["tod"].to_numpy() >= 4)))
Q("N25", "nova", "A faixa dos primeiros 60 minutos foi estreita (< 0,25 ATR diário)?", "Faixa inicial", "(máx. − mín. de 09:00–10:00)/ATR diário < 0,25", "sim/não", "sim", "Crabel: contração inicial antecede dia de tendência (sem direção)", SIM,
  lambda F, S: cod((F["orh"] - F["orl"]) / F["ad"] < 0.25, nn(F["orh"], F["orl"], F["ad"]) & (F["tod"].to_numpy() >= 4)), lado=False)
Q("N26", "nova", "As últimas 12 velas formam uma faixa lateral estreita?", "Volatilidade/regime", "máx. − mín. das 12 últimas velas ≤ 2,5 ATR M15", "sim/não", "sim", "lateralização/compressão (Wyckoff, Bollinger): precede expansão (sem direção)", SIM,
  lambda F, S: cod((F["h"].rolling(12).max() - F["l"].rolling(12).min()) <= 2.5 * F["a"], nn(F["h"].rolling(12).max(), F["a"])), lado=False)
Q("N27", "nova", "A volatilidade está em contração (ATR atual < 0,8× a média das últimas 100 velas)?", "Volatilidade/regime", "ATR14 M15 < 0,8 × média de 100 valores", "sim/não", "sim", "volatilidade é persistente e agrupa em regimes (Mandelbrot/Engle)", SIM,
  lambda F, S: cod(F["a"] < 0.8 * F["a"].rolling(100).mean(), nn(F["a"], F["a"].rolling(100).mean())), lado=False)
Q("N28", "nova", "A volatilidade está em expansão (ATR atual > 1,2× a média das últimas 100 velas)?", "Volatilidade/regime", "ATR14 M15 > 1,2 × média de 100 valores", "sim/não", "sim", "idem; expansão favorece rompimentos", SIM,
  lambda F, S: cod(F["a"] > 1.2 * F["a"].rolling(100).mean(), nn(F["a"], F["a"].rolling(100).mean())), lado=False)
Q("N29", "nova", "As bandas de Bollinger estão em aperto (squeeze)?", "Volatilidade/regime", "largura das bandas (20,2) ≤ 1,1× a menor das últimas 100 velas", "sim/não", "sim", "Bollinger: aperto antecede expansão (sem direção)", SIM,
  lambda F, S: cod(F["sqz"] == 1, nn(F["sqz"])), lado=False)
Q("N30", "nova", "O volume desta vela está bem acima do normal do horário?", "Volume", "volume da vela ≥ 1,5× a média do mesmo horário nos 20 pregões anteriores", "sim/não", "sim", "Wyckoff: esforço; volume anormal marca participação institucional (sem direção)", SIM,
  lambda F, S: cod(F["rv"] >= 1.5, nn(F["rv"])), lado=False)
Q("N31", "nova", "O volume acumulado do dia está acima do normal até este horário?", "Volume", "volume acumulado ≥ 1,2× a média do mesmo horário nos 20 pregões anteriores", "sim/não", "sim", "dia ativo/informado (sem direção)", SIM,
  lambda F, S: cod(F["rvd"] >= 1.2, nn(F["rvd"])), lado=False)
Q("N32", "nova", "A vela fechou de alta com volume bem acima do normal?", "Volume", "fechamento > abertura e volume ≥ 1,5× o normal do horário", "sim/não", "sim", "Wyckoff: esforço e resultado alinhados (demanda real)", SIM,
  lambda F, S: cod((F["c"] > F["o"]) & (F["rv"] >= 1.5), nn(F["rv"])))
Q("N33", "nova", "Houve vela de baixa com volume alto que fechou na metade superior (absorção)?", "Volume", "fechamento < abertura, volume ≥ 1,5×, fechamento acima do ponto médio da vela", "sim/não", "sim", "Wyckoff: esforço sem resultado = absorção por compradores", SIM,
  lambda F, S: cod((F["c"] < F["o"]) & (F["rv"] >= 1.5) & (F["c"] > (F["h"] + F["l"]) / 2), nn(F["rv"])))
def _q_clim(F, S):
    x = ((F["h"] - F["l"]) >= 2 * F["a"]) & (F["rv"] >= 2) & (F["c"] < F["o"])
    return cod(x.astype(float).rolling(4).max() > 0, nn(F["rv"], F["a"]))
Q("N34", "nova", "Houve clímax vendedor nas últimas 4 velas?", "Volume", "vela de baixa com faixa ≥ 2 ATR e volume ≥ 2× o normal, nas últimas 4 velas", "sim/não", "sim", "Wyckoff (selling climax): exaustão vendedora marca fundo", SIM, _q_clim)
def _q_wsp(F, S):
    sup = F["l"].rolling(20).min().shift(10); mn = F["l"].rolling(10).min()
    return cod((mn < sup) & (F["c"] > sup), nn(sup, mn, F["c"]))
Q("N35", "nova", "Houve spring de Wyckoff (perdeu o suporte das 20 velas e voltou) nas últimas 10 velas?", "Estrutura", "mínima das 10 últimas < mínima das velas [-30,-10] e fechamento atual acima dela", "sim/não", "sim", "Wyckoff: spring/teste do suporte", SIM, _q_wsp)
Q("N36", "nova", "A tendência é forte e a favor (ADX ≥ 25 com +DI > −DI)?", "Tendência/momentum", "ADX(14) ≥ 25 e +DI > −DI no M15", "sim/não", "sim", "Wilder: ADX mede força, DI o lado", SIM,
  lambda F, S: cod((F["adx"] >= 25) & (F["pdi"] > F["mdi"]), nn(F["adx"], F["pdi"], F["mdi"])))
Q("N37", "nova", "O índice direcional positivo está acima do negativo (+DI > −DI)?", "Tendência/momentum", "+DI(14) > −DI(14) no M15", "sim/não", "sim", "Wilder", SIM,
  lambda F, S: cod(F["pdi"] > F["mdi"], nn(F["pdi"], F["mdi"])))
Q("N38", "nova", "A MME50 do M15 está subindo e o preço acima dela?", "Tendência/momentum", "MME50 agora > MME50 3 velas atrás e fechamento > MME50", "sim/não", "sim", "Murphy: média inclinada + preço do lado certo", SIM,
  lambda F, S: cod((F["e50"] > F["e50"].shift(3)) & (F["c"] > F["e50"]), nn(F["e50"], F["c"])))
Q("N39", "nova", "Os últimos dois topos e os últimos dois fundos são ascendentes (Dow)?", "Estrutura", "fractais 2-2 confirmados: último topo > anterior e último fundo > anterior", "sim/não", "sim", "Teoria de Dow: tendência de alta = topos e fundos ascendentes", SIM,
  lambda F, S: cod((F["lsh"] > F["psh"]) & (F["lsl"] > F["psl"]), nn(F["lsh"], F["psh"], F["lsl"], F["psl"])))
Q("N40", "nova", "O preço subiu pelo menos 1 ATR nas últimas 16 velas (4 horas)?", "Tendência/momentum", "(fech. − fech. 16 velas atrás)/ATR M15 ≥ 1", "sim/não", "sim", "momentum de curto prazo (Jegadeesh-Titman, versão intradiária)", SIM,
  lambda F, S: cod((F["c"] - F["c"].shift(16)) / F["a"] >= 1, nn(F["c"], F["c"].shift(16), F["a"])))
def _q_div(F, S):
    l, r = F["l"], F["rsi"]
    l1, l0 = l.rolling(12).min(), l.rolling(12).min().shift(12); r1, r0 = r.rolling(12).min(), r.rolling(12).min().shift(12)
    return cod((l1 < l0) & (r1 > r0), nn(l1, l0, r1, r0))
Q("N41", "nova", "Há divergência altista entre preço e RSI?", "Momentum × reversão", "mínima de preço das 12 últimas < das 12 anteriores e mínima do RSI14 das 12 últimas > das 12 anteriores", "sim/não", "sim", "Murphy/Wilder: divergência de oscilador (já refutada no projeto)", SIM, _q_div)
Q("N42", "nova", "O RSI está em sobrevenda (≤ 30)?", "Momentum × reversão", "RSI(14) M15 ≤ 30", "sim/não", "sim", "Wilder: extremo do oscilador contra o lado = reversão", SIM,
  lambda F, S: cod(F["rsi"] <= 30, nn(F["rsi"])))
Q("N43", "nova", "O RSI está na zona de alta (acima de 50)?", "Momentum × reversão", "RSI(14) M15 > 50", "sim/não", "sim", "Cardwell/Brown: RSI > 50 = regime de alta (momentum, oposto da sobrevenda)", SIM,
  lambda F, S: cod(F["rsi"] > 50, nn(F["rsi"])))
Q("N44", "nova", "O preço fechou abaixo da banda inferior de Bollinger?", "Momentum × reversão", "fechamento < média 20 − 2 desvios (M15)", "sim/não", "sim", "Bollinger: fora da banda contra = reversão à média", SIM,
  lambda F, S: cod(F["c"] < F["s20"] - 2 * F["sd20"], nn(F["c"], F["s20"], F["sd20"])))
Q("N45", "nova", "O histograma do MACD é positivo e crescente?", "Tendência/momentum", "MACD(12,26,9) histograma > 0 e > valor anterior", "sim/não", "sim", "Appel: momentum positivo e acelerando", SIM,
  lambda F, S: cod((F["hist"] > 0) & (F["hist"] > F["hist"].shift(1)), nn(F["hist"])))
def _q_acc(F, S):
    c = F["c"]; l1 = c - c.shift(6); l0 = c.shift(6) - c.shift(12)
    return cod((l1 > 0) & (l1.abs() > l0.abs()), nn(l1, l0))
Q("N46", "nova", "A última perna é a favor e mais forte que a anterior (aceleração)?", "Força relativa", "variação das últimas 6 velas > 0 e maior em módulo que a das 6 anteriores", "sim/não", "sim", "Elliott/Dow: onda de impulso mais forte que a correção anterior", SIM, _q_acc)
Q("N47", "nova", "O retorno da primeira meia hora foi a favor?", "Sazonalidade intradiária", "fechamento das 2 primeiras velas (09:00–09:30) > abertura do dia (válido a partir das 09:30)", "sim/não", "sim", "Gao-Han-Li-Zhou 2018: a 1ª meia hora prevê o resto do dia", SIM,
  lambda F, S: cod(F["r30"] > 0, nn(F["r30"]) & (F["tod"].to_numpy() >= 2)))
Q("N48", "nova", "O preço está acima do fechamento de ontem?", "Níveis de referência", "fechamento > fechamento do pregão anterior", "sim/não", "sim", "referência clássica (Murphy); gap preenchido ou não", SIM,
  lambda F, S: cod(F["c"] > F["pdc"], nn(F["c"], F["pdc"])))
Q("N49", "nova", "O preço está colado (< 0,5 ATR) abaixo de um número redondo (múltiplo de 1.000 pontos)?", "Níveis de referência", "(próximo múltiplo de 1.000 ≥ fechamento − fechamento)/ATR M15 < 0,5", "sim/não", "não", "números redondos atraem ordens e funcionam como resistência (Grimes)", NAO,
  lambda F, S: cod((np.ceil(F["c"] / 1000) * 1000 - F["c"]) / F["a"] < 0.5, nn(F["c"], F["a"])))
Q("N50", "nova", "O dólar (WDO) caiu nas últimas 4 velas?", "Intermercado", "WDO@D M15: fechamento < fechamento 4 velas atrás (mesmo pregão)", "sim/não", "sim", "correlação inversa dólar × bolsa brasileira (Murphy, análise intermercados)", SIM,
  lambda F, S: cod(F["wdo"] < F["wdo"].shift(4), nn(F["wdo"], F["wdo"].shift(4)) & (F["tod"].to_numpy() >= 4)))

# ------------------------------------------------------------------ EXISTENTES (PERGUNTAS_DE_OPERACAO.md)
def _S(F): return pd.DataFrame(dict(pos=np.arange(len(F["c"])), lado=1))
Q("C1", "existente", "[D2] A tendência do tempo gráfico maior (H1) está a favor?", "Existente D2", "H1 fechado: fechamento×MME34 e MME9×MME21 a favor", "sim/não", "sim", "banco atual C1", SIM,
  lambda F, S: cod(F["h1"].to_numpy() == 1))
Q("C2", "existente", "[D3] O preço está do lado a favor da abertura do dia?", "Existente D3", "fechamento > abertura do pregão", "sim/não", "sim", "banco atual C2", SIM,
  lambda F, S: cod(F["c"] > F["dop"], nn(F["c"], F["dop"])))
Q("C3", "existente", "[D4] As médias rápida e lenta estão a favor? (MMS17 > MMS34)", "Existente D4", "MMS17 > MMS34 do fechamento M15", "sim/não", "sim", "banco atual C3", SIM,
  lambda F, S: cod(F["m17"] > F["m34"], nn(F["m17"], F["m34"])))
Q("C4", "existente", "[D5] A média longa está inclinada a favor? (MMS72 da abertura)", "Existente D5", "MMS72(open) agora > 3 velas atrás", "sim/não", "sim", "banco atual C4", SIM,
  lambda F, S: cod(F["m72o"] > F["m72o"].shift(3), nn(F["m72o"], F["m72o"].shift(3))))
Q("C5", "existente", "[D6∨D7] Preço não esticado (Estoc14<70) ou H4 neutro?", "Existente D6/D7", "estocástico 14 (suav. 3) < 70 a favor OU H4 neutro", "sim/não", "sim", "banco atual C5", SIM,
  lambda F, S: cod(filtros.sinal_bom(S["v"], _S(F))))
Q("C6", "existente", "[D11] O gap de abertura é menor que 1 ATR diário?", "Existente D11", "|abertura − fechamento de ontem|/ATR diário < 1", "sim/não", "sim", "banco atual C6", SIM,
  lambda F, S: cod(np.abs(F["gap"]) / F["ad"] < 1.0, nn(F["gap"], F["ad"])), lado=False)
Q("C7", "existente", "[Q16] O pregão já andou meio ATR diário?", "Existente Q16", "(máx. − mín. do dia)/ATR diário ≥ 0,5", "sim/não", "sim", "banco atual C7", SIM,
  lambda F, S: cod((F["dhi"] - F["dlo"]) / F["ad"] >= 0.5, nn(F["dhi"], F["dlo"], F["ad"])), lado=False)
Q("C8", "existente", "[X1] O contexto virou no H1 (H1 não está mais a favor)?", "Existente X1", "complemento de C1", "sim/não", "sim", "banco atual C8 (pergunta de saída)", SIM,
  lambda F, S: cod(F["h1"].to_numpy() != 1))
for t in ("T1", "T2", "T3", "T4"):
    Q(t, "existente", {"T1": "[D1] A estrutura de topos e fundos confirmou a virada a favor AGORA?", "T2": "[D12] A vela fechou fora da faixa das 20 anteriores (faixa ≤ 1,5 ATR diário) a favor AGORA?",
                         "T3": "A 1ª vela do dia fechou contra o gap AGORA?", "T4": "[D13] As médias 9/21/34 acabaram de se alinhar a favor?"}[t],
      "Existente gatilho", {"T1": "ZigZag 1,5 ATR: fundo acima do anterior", "T2": "fechamento fora da faixa de 20 velas", "T3": "1ª vela contra gap ≥ 5 pts", "T4": "MME9>21>34 e não na vela anterior"}[t],
      "sim/não", "sim", "banco atual " + t, SIM, None)
Q("D6", "existente", "[D6] O oscilador está longe do extremo a favor (estocástico < 70)?", "Existente D6", "estocástico 14 (suav. 3) < 70", "sim/não", "sim", "PERGUNTAS D6", SIM,
  lambda F, S: cod(F["stoch"] < 70, nn(F["stoch"])))
Q("D7", "existente", "[D7] O H4 está sem tendência (neutro)?", "Existente D7", "H4 MME9/21/34 neutro (fechados)", "sim/não", "sim", "PERGUNTAS D7", SIM,
  lambda F, S: cod(F["h4"] == 0, nn(F["h4"])), lado=False)
Q("D9", "existente", "[D9/Q40] Resta pregão suficiente (≥ 8 velas até o fim)?", "Existente D9/Q40", "velas restantes no pregão ≥ 8", "sim/não", "sim", "PERGUNTAS D9", SIM,
  lambda F, S: cod(F["nrest"] >= 8), lado=False)
Q("D11", "existente", "[D11] Há gap a favor (≥ 0,25 ATR diário) ainda não preenchido?", "Existente D11", "(abertura − fech. ontem) ≥ 0,25 ATR diário e fechamento > fech. de ontem", "sim/não", "sim", "PERGUNTAS D11", SIM,
  lambda F, S: cod((F["gap"] / F["ad"] >= 0.25) & (F["c"] > F["pdc"]), nn(F["gap"], F["ad"], F["pdc"])))
Q("D13", "existente", "[D13] As médias 9/21/34 do tempo próprio estão alinhadas a favor (estado)?", "Existente D13", "MME9 > MME21 > MME34 no M15", "sim/não", "sim", "PERGUNTAS D13", SIM,
  lambda F, S: cod((F["e9"] > F["e21"]) & (F["e21"] > F["e34"]), nn(F["e9"], F["e21"], F["e34"])))
Q("Q13", "existente", "[Q13] O mercado está em regime de tendência (ADX ≥ 25)?", "Existente Q13", "ADX(14) M15 ≥ 25", "sim/não", "sim", "PERGUNTAS 13", SIM,
  lambda F, S: cod(F["adx"] >= 25, nn(F["adx"])), lado=False)
Q("Q14", "existente", "[Q14] H1 e H4 concordam a favor?", "Existente Q14", "H1 a favor e H4 a favor", "sim/não", "sim", "PERGUNTAS 14", SIM,
  lambda F, S: cod((F["h1"] == 1) & (F["h4"] == 1), nn(F["h4"])))
Q("Q16", "existente", "[Q16] O dia está esgotado (já andou ≥ 0,75 ATR diário)?", "Existente Q16", "(máx. − mín. do dia)/ATR diário ≥ 0,75", "sim/não", "não", "PERGUNTAS 16", NAO,
  lambda F, S: cod((F["dhi"] - F["dlo"]) / F["ad"] >= 0.75, nn(F["dhi"], F["dlo"], F["ad"])), lado=False)
Q("Q18", "existente", "[Q18] O dólar confirma (WDO abaixo da abertura de hoje)?", "Existente Q18", "WDO@D M15: fechamento < abertura do dia do WDO", "sim/não", "sim", "PERGUNTAS 18", SIM,
  lambda F, S: cod(F["wdo"] < F["wdo_dop"], nn(F["wdo"], F["wdo_dop"])))
Q("Q19", "existente", "[Q19] Há algo anormal agora (vela ≥ 2 ATR ou volume ≥ 2× o normal, nas últimas 3 velas)?", "Existente Q19", "faixa ≥ 2 ATR ou volume relativo ≥ 2 em alguma das 3 últimas velas", "sim/não", "não", "PERGUNTAS 19", NAO,
  lambda F, S: cod((((F["h"] - F["l"]) >= 2 * F["a"]) | (F["rv"] >= 2)).astype(float).rolling(3).max() > 0, nn(F["rv"], F["a"])), lado=False)
Q("Q24", "existente", "[Q24] O preço está esticado acima da MME38 (≥ 2 ATR)?", "Existente Q24", "(fech. − MME38)/ATR M15 ≥ 2", "sim/não", "não", "PERGUNTAS 24", NAO,
  lambda F, S: cod((F["c"] - F["e38"]) / F["a"] >= 2, nn(F["c"], F["e38"], F["a"])))
Q("Q26", "existente", "[Q26] A volatilidade está acima do normal (ATR > 1,2× a média de 500 velas)?", "Existente Q26", "ATR14 M15 > 1,2 × média de 500", "sim/não", "sim", "PERGUNTAS 26", SIM,
  lambda F, S: cod(F["a"] > 1.2 * F["a"].rolling(500).mean(), nn(F["a"], F["a"].rolling(500).mean())), lado=False)
Q("Q27", "existente", "[Q27] O volume recente confirma o movimento (3 velas com volume ≥ 1,2× e preço a favor)?", "Existente Q27", "média do volume relativo das 3 últimas ≥ 1,2 e fech. > fech. 3 velas atrás", "sim/não", "sim", "PERGUNTAS 27", SIM,
  lambda F, S: cod((F["rv"].rolling(3).mean() >= 1.2) & (F["c"] > F["c"].shift(3)), nn(F["rv"].rolling(3).mean())))
def _q_sup(F, S):
    l, a, c = F["l"], F["a"], F["c"]; m40 = l.rolling(40).min(); cnt = (l <= m40 + 0.25 * a).astype(float).rolling(40).sum()
    return cod((cnt >= 3) & ((c - m40) < a), nn(m40, a, cnt))
Q("Q32", "existente", "[Q32] O suporte das últimas 40 velas foi testado 3 ou mais vezes e o preço está a menos de 1 ATR dele?", "Existente Q32", "velas com mínima ≤ mín.40 + 0,25 ATR ≥ 3 e fech. − mín.40 < 1 ATR", "sim/não", "sim", "PERGUNTAS 32", SIM, _q_sup)
def _q_prof(F, S):
    hh, ll, c = F["h"].rolling(20).max(), F["l"].rolling(20).min(), F["c"]; dep = (hh - c) / (hh - ll).replace(0, np.nan)
    return cat(dep, [0.33, 0.62], nn(dep))
Q("Q33", "existente", "[Q33] Qual a profundidade da correção atual dentro da faixa das últimas 20 velas?", "Existente Q33", "(máx.20 − fech.)/(máx.20 − mín.20); 0 = rasa (<0,33), 1 = média, 2 = funda (>0,62)", "faixa (3)", "rasa (0)", "PERGUNTAS 33", 0, _q_prof)
Q("Q39", "existente", "[Q39] O sinal acontece depois das 15h?", "Existente Q39", "hora da vela ≥ 15:00", "sim/não", "não", "PERGUNTAS 39", NAO,
  lambda F, S: cod(F["mins"].to_numpy() >= 900), lado=False)
Q("Q42a", "existente", "[Q42] Hoje é sexta-feira?", "Existente Q42", "dia da semana = sexta", "sim/não", "não", "PERGUNTAS 42", NAO,
  lambda F, S: cod(F["c"].index.dayofweek == 4), lado=False)
_VENC = pd.DatetimeIndex(dados.vencimentos())
def _q_venc(F):
    dias = F["c"].index.normalize(); dv = (_VENC.values[None, :] - dias.values[:, None]) / np.timedelta64(1, "D")
    return cod(((dv >= 0) & (dv <= 2)).any(axis=1))
Q("Q42b", "existente", "[Q42] A data está nos 2 dias úteis até a quarta de vencimento do WIN?", "Existente Q42", "dia ∈ {vencimento−2 dias, vencimento}", "sim/não", "não", "PERGUNTAS 42", NAO,
  lambda F, S: _q_venc(F), lado=False)
def _q_fimmes(F, S):
    dias = pd.Series(F["c"].index.normalize()); u = pd.Series(sorted(dias.unique()))
    ult = u.groupby(u.dt.to_period("M")).transform(lambda s: pd.Series(np.arange(len(s))[::-1], index=s.index))  # 0 = ultimo dia
    m = dict(zip(u, ult.values)); return cod(dias.map(m).to_numpy() <= 2)
Q("Q42c", "existente", "[Q42] Estamos nos 3 últimos pregões do mês?", "Existente Q42", "dia entre os 3 últimos pregões do mês", "sim/não", "não", "PERGUNTAS 42", NAO, _q_fimmes, lado=False)

IDS = [r["id"] for r in R]
EXTERNAS = {"T1", "T2", "T3", "T4"}
