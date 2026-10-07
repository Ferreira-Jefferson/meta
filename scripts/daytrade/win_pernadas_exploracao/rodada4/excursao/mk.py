import pandas as pd
tq=open("tabelas_quantis.md",encoding="utf-8").read()
cd=pd.read_csv("candidatos_desc.csv"); cc=pd.read_csv("candidatos_conf.csv")
def md(df): return "| "+" | ".join(df.columns)+" |\n|"+"---|"*len(df.columns)+"\n"+"\n".join("| "+" | ".join(str(v) for v in r)+" |" for r in df.values)
head = """# WIN 2026 - mapa de excursoes apos o recuo (MFE/MAE) e superficie de esperanca

Dados: WIN@D M1, so 2026. Descoberta jan-jun (122 pregoes), confirmacao jul-ago (44), referencia set (21). Codigo e saidas brutas em `rodada4/excursao/` (`exc.py` motor de eventos e simulacao, `agg.py`, `stage0.py`/`stage1.py` real e nulo, `cand.py` bootstrap/plato, `mao.py` tamanho, `quantis_*.csv`, `candidatos_*.csv`).

## Metodo
- **Evento**: avanco A = do ultimo fundo (reinicia se o preco o perde) ate a maxima corrente, 150 <= A <= 2.000 pts. Recuo r = 10/20/30/38/50/62/78% de A, em tempo real, um evento por nivel por maxima. Os dois lados espelhados (alta e queda) no mesmo quadro "tendencia anterior = alta". Cortes: faixa de A (150-250, 250-400, 400-750, 750-2000), r, horario (<11h, 11-13h, >=13h), velocidade do recuo em pts/min (tercis congelados na descoberta: <55,6; 55,6-109; >109), ordem do recuo no movimento (1o, 2o, 3o+).
- **MFE/MAE**: a partir do ponto em que o recuo e atingido, maximo a favor da tendencia anterior (MFE) e maximo contra (MAE) em 15/30/60 min e ate o fim do pregao (15/30 em `quantis_*.csv`).
- **Nulo**: velas M1 embaralhadas em blocos de 30 min, mesmo codigo, 40 simulacoes por janela. Excesso = real - media do nulo; z = excesso / desvio entre simulacoes.
- **Execucao simulada** (desenho fechado): entrada por ordem-limite no nivel do recuo, prazo de 5 min; alvo por limite; stop a mercado com 5 pts de deslize; custo 2 pts/op; R$0,20/pt; fim do pregao = saida a mercado. Fill conservador: so enche se o preco negociar 1 tick (5 pts) alem do nivel (alvo idem); otimista: basta tocar. Alvo minimo 25 pts. Dois lados: **a favor** = comprar o recuo da alta (e vender o da queda); **contra** = vender o recuo da alta como inicio de virada (e comprar o da queda).
- **Geometrias** (25): pts fixos T x S em {75,150,300,600}^2 (16) e multiplos de A, alvo {0,25;0,5;1,0}A x stop {0,3;0,6;1,0}A (9).
- **Testes**: 136 celulas (12 cortes) x 2 lados x 25 geometrias x 2 fills = 13.600 combinacoes por janela; triadas 6.800 (fill conservador, n de operacoes >= 150) e 6.800 no otimista. IC por bootstrap de dias (2.000 reamostragens); plato = vizinhos de geometria (+-1 passo em T e S) e de r (+-1 nivel).

## 1. Mapa de excursoes: real contra nulo (descoberta; confirmacao abaixo)
Leitura (pts, por contrato, p50/p90 entre parenteses = nulo):

- A extensao a favor e a contra **nao dependem do tamanho de A nem de r**; dependem do horario e da volatilidade do dia. Em 60 min a mediana do MFE vai de ~430 a ~590 pts e a do MAE de ~335 a ~450, para qualquer A e r. Ate o fim do pregao: MFE mediano 770-1.010, MAE mediano 725-900.
- Em multiplos de A isso significa que o recuo "devolvido" pouco informa: para A de 150-250 o preco anda em mediana 2,4A a favor e 1,8A contra em 60 min; para A de 750-2000, 0,5A e 0,4A. O alcance e ~ constante em pontos, nao proporcional a A.
- **Real x nulo**: o MFE e igual ao nulo (diferencas de -8% a +5%, sem sinal consistente). O MAE real e **um pouco menor** que o nulo em A < 750 (mediana 335-400 contra 400-446, p90 ~1.100 contra ~1.300) na descoberta, e o mesmo na confirmacao em 150-250 (275-305 contra 335-354); em A >= 750 o MAE real e igual ou ate maior que o nulo. E um efeito de poucos %, que nao vira esperanca depois de custo (secao 2).
- Superficie por r: a favor, recuos rasos (r <= 30%) tem excesso medio de +1 a +5 pts sobre o nulo; recuos fundos (r >= 50%) tem -5 a -12. Contra (fade) e o espelho: -8 pts em r 10-20% e +4 a +8 em r >= 50%. O padrao reaparece na confirmacao com o mesmo sinal em r raso e r extremo, mas com magnitude de 1 a 10 pts contra um custo medio de 30-50 pts por operacao.

## 2. Superficie de esperanca (liquida, por operacao executada; descoberta, sem corte)
Esperanca liquida em pts (entre parenteses o nulo) e acerto/breakeven empirico em %, por geometria; a favor | contra, fill conservador; depois fill otimista.

| geometria | a favor, cons. | contra, cons. | a favor, otim. | contra, otim. |
|---|---|---|---|---|
"""
rows=open("fin_rows.txt",encoding="utf-8").read() if False else None
open("rep_head.md","w",encoding="utf-8").write(head)
open("rep_cd.md","w",encoding="utf-8").write(md(cd)); open("rep_cc.md","w",encoding="utf-8").write(md(cc))
