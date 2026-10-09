"""Pagina enxuta: regra atual (v3), metodo, versoes aprovadas com curvas, lista do que foi testado. Uso: pagina_final.py <saida.html>"""
import sys
import pandas as pd

C = pd.read_pickle("scripts/daytrade/topos_fundos/res_conf/curvas_versoes.pkl")
CORES = {"v1": "var(--c1)", "v2": "var(--c2)", "v3": "var(--c3)"}


def br(x, s=False):
    t = f"{x:+,.0f}" if s else f"{x:,.0f}"
    return t.replace(",", ".").replace("-", "−")


def svg(per, titulo):
    W, H, L, R_, T, B = 640, 260, 56, 16, 16, 28
    cur = {v: C[(per, v)]["curva"] for v in ("v1", "v2", "v3")}
    x0 = min(s.index.min() for s in cur.values()); x1 = max(s.index.max() for s in cur.values())
    ymin = min(0, min(s.min() for s in cur.values())); ymax = max(s.max() for s in cur.values())
    fx = lambda d: L + (d - x0) / (x1 - x0) * (W - L - R_)
    fy = lambda y: T + (ymax - y) / (ymax - ymin) * (H - T - B)
    g = []
    passo = 10000 if ymax > 20000 else 5000
    y = 0
    while y <= ymax:
        g.append(f'<line x1="{L}" x2="{W - R_}" y1="{fy(y):.1f}" y2="{fy(y):.1f}" class="grid"/><text x="{L - 6}" y="{fy(y) + 4:.1f}" class="ax" text-anchor="end">{br(y)}</text>')
        y += passo
    anos = pd.date_range(x0, x1, freq="YS") if (x1 - x0).days > 500 else pd.date_range(x0, x1, freq="QS")
    for a in anos:
        lab = a.strftime("%Y") if (x1 - x0).days > 500 else a.strftime("%m/%y")
        g.append(f'<text x="{fx(a):.1f}" y="{H - 8}" class="ax" text-anchor="middle">{lab}</text>')
    for v, s in cur.items():
        pts = " ".join(f"{fx(d):.1f},{fy(y):.1f}" for d, y in zip(s.index, s.values))
        g.append(f'<polyline points="{pts}" fill="none" stroke="{CORES[v]}" stroke-width="{2.2 if v == "v3" else 1.4}"/>')
    leg = " ".join(f'<span class="lg"><i style="background:{CORES[v]}"></i>{v} {br(C[(per, v)]["total"], True)} pts</span>' for v in cur)
    return f'<figure><figcaption>{titulo}</figcaption><svg viewBox="0 0 {W} {H}" role="img">{"".join(g)}</svg><div class="legenda">{leg}</div></figure>'


def linha(v, rot, motivo):
    a, o = C[("pesquisa", v)], C[("reserva", v)]
    return (f"<tr><th><b>{v}</b> {rot}</th><td>{a['n']}</td><td>{br(a['op'], True)}</td><td>{br(a['total'], True)}</td><td>{br(a['dd'])}</td>"
            f"<td>{o['n']}</td><td>{br(o['op'], True)}</td><td>{br(o['total'], True)}</td><td>{br(o['dd'])}</td><td class=l>{motivo}</td></tr>")


html = f"""<title>Escada WIN M15</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root {{ --bg:#f6f5f1; --fg:#1c1d1f; --mut:#6b6b66; --line:#dcdad2; --card:#fff; --acc:#c23a2b; --c1:#9a9a92; --c2:#2f7fbf; --c3:#c23a2b; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#0e0f10; --fg:#e4e2dc; --mut:#8e8c86; --line:#2a2b2d; --card:#161719; --acc:#ff6b5a; --c1:#6c6c66; --c2:#5aa6e6; --c3:#ff6b5a; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#0e0f10; --fg:#e4e2dc; --mut:#8e8c86; --line:#2a2b2d; --card:#161719; --acc:#ff6b5a; --c1:#6c6c66; --c2:#5aa6e6; --c3:#ff6b5a; color-scheme:dark; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.55 "IBM Plex Sans", system-ui, sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding-inline:16px; padding-block:24px 48px; }}
h1 {{ font-size:1.6rem; margin:0 0 4px; }} h2 {{ font-size:1.1rem; margin:30px 0 8px; }}
p, li {{ max-width:75ch; }} .m {{ color:var(--mut); }}
.regra {{ background:var(--card); border-left:3px solid var(--acc); padding:10px 18px; }}
.regra ol {{ margin:6px 0; padding-left:20px; }}
.tw {{ overflow-x:auto; }}
table {{ border-collapse:collapse; font-family:"JetBrains Mono", ui-monospace, monospace; font-size:12.5px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:5px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
th:first-child, .l {{ text-align:left!important; font-family:"IBM Plex Sans", system-ui, sans-serif; }}
td.l {{ white-space:normal; min-width:220px; }}
thead th {{ color:var(--mut); font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; }}
.graf {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:20px; }}
figure {{ margin:0; min-width:0; }} figcaption {{ font-size:13px; color:var(--mut); margin-bottom:4px; }}
svg {{ width:100%; height:auto; display:block; }}
svg .grid {{ stroke:var(--line); stroke-width:1; }} svg .ax {{ fill:var(--mut); font:11px "JetBrains Mono", monospace; }}
.legenda {{ display:flex; flex-wrap:wrap; gap:14px; font:12px "JetBrains Mono", monospace; margin-top:4px; }}
.lg i {{ display:inline-block; width:14px; height:3px; vertical-align:middle; margin-right:5px; }}
ul.t li {{ margin:3px 0; }}
</style>
<main>
<h1>Escada de topos e fundos: WIN M15</h1>
<p class=m>Estudo de 08/10/2026 · WIN$N sem leilões · IS jan/2022–set/2025 · OOS out/2025–out/2026 · pts por 1 contrato, já com 10 pts de custo por operação</p>

<h2>Regra atual (v4.1, adotada em 08/10/2026)</h2>
<div class="regra"><ol>
<li><b>Escada:</b> ZigZag de 1,5 ATR(14) no M15. Compra quando um fundo confirmado fica acima do fundo anterior (estágio ≥ 1). Venda no espelho.</li>
<li><b>Filtros a favor:</b> H1 fechado com close acima da MME34 e MME9 acima da MME21 · close acima da abertura do dia · MMS17 acima da MMS34 (close, M15) · MMS72 do open subindo (agora acima de 3 barras atrás). Na venda, tudo invertido.</li>
<li><b>Sinal bom (v4):</b> só entra se o Estocástico 14 (suav. 3) estiver abaixo de 70 a favor (acima de 30 na venda) OU o H4 estiver neutro. <b>2 contratos</b> em toda entrada.</li>
<li><b>Entrada:</b> limitada no fechamento da barra de confirmação, válida por 3 barras.</li>
<li><b>Stop (v4.1):</b> no fundo confirmado; se a MME38 do M15 estiver entre o fundo e a entrada, sobe para 0,2 ATR abaixo dela. Depois, subindo a cada novo fundo. Sem alvo. Zera no fim do pregão. Uma posição por vez.</li>
</ol></div>

<h2>Como testamos</h2>
<ul class=t>
<li><b>IS e OOS:</b> escolha só no IS; o OOS foi aberto uma vez para confirmar. Uma mudança só fica se melhorar o total E os pts por operação nos dois.</li>
<li><b>Vizinhança:</b> o parâmetro vizinho precisa dar resultado parecido. Pico isolado é descartado.</li>
<li><b>Funil de dias pequenos:</b> 10 dias ruins, depois outros dias ruins e bons. Serve para levantar candidatos, não para decidir: em 50 sorteios, a própria MMS17 só passaria em 14%.</li>
<li><b>Regra dos ramos:</b> 3 ramos com dias diferentes; o filtro só conta se aparecer em pelo menos 2.</li>
<li><b>Controles:</b> placebo (sorteios do mesmo tamanho) e "só o filtro sem a escada" (−37 pts por operação). O ganho exige a escada.</li>
<li><b>Execução realista:</b> uma posição por vez; a ordem limitada só enche se o preço passar 2 ticks além dela.</li>
</ul>

<h2>Versões aprovadas</h2>
<div class="tw"><table>
<thead><tr><th>versão</th><th>IS ops</th><th>pts/op</th><th>total</th><th>queda máx.</th><th>OOS ops</th><th>pts/op</th><th>total</th><th>queda máx.</th><th class=l>por que entrou</th></tr></thead>
<tbody>
{linha("v1", "escada + H1 + abertura do dia", "Os dois filtros, juntos, separam +23 de −20 pts por operação; confirmado no OOS (+86 ± 46 nos sinais do M5); placebo p &lt; 0,0002; 48/48 vizinhos positivos.")}
{linha("v2", "+ MMS17×34 close", "Única de 306 médias que passou funil, IS e OOS; está no centro do platô 16–18 × 30–36. Mesmo total com menos operações.")}
{linha("v3", "+ MMS72 open inclinada", "Toda a faixa 66–78 reduz a queda no OOS; queda −14% no IS e −28% no OOS; 2024 passa de +705 para +3.245.")}
</tbody></table></div>
<div class="graf">
{svg("pesquisa", "Evolução no IS (jan/22–set/25), pts acumulados")}
{svg("reserva", "Evolução no OOS (out/25–out/26), pts acumulados")}
</div>

<h2>Confirmação em período nunca usado (out–dez/2021)</h2>
<p>O MT5 da corretora só tem WIN a partir de 08/10/2021. Os 56 pregões até 30/12/2021 nunca tinham entrado em nenhum teste. A base foi montada do mesmo jeito (sem leilões) e as regras foram congeladas antes de rodar.</p>
<div class="tw"><table>
<thead><tr><th>out–dez/2021</th><th>ops</th><th>total pts</th><th>pts/op</th><th>queda máx.</th><th>R$</th></tr></thead>
<tbody>
<tr><th>v3 (todas, 1 contrato)</th><td>32</td><td>+535</td><td>+17</td><td>1.785</td><td>+107</td></tr>
<tr><th>v4 (só bons, 2 contratos)</th><td>21</td><td>+2.170</td><td>+103</td><td>2.950</td><td>+434</td></tr>
<tr><th>v4.1 (+ aperto MME38)</th><td>21</td><td>+2.443</td><td>+116</td><td>2.942</td><td>+489</td></tr>
</tbody></table></div>
<p class=m>A direção se repete: v4 &gt; v3 e v4.1 ≥ v4. Mas são só 21 operações em 2,5 meses, pouco para provar alguma coisa, e a redução de queda da v4.1 não aparece num trecho tão curto. Não existe mais dado histórico virgem. A próxima confirmação honesta é a operação em sombra, daqui para frente.</p>
<h2>Já testado e não adotado</h2>
<ul class=t>
<li><b>Escada de 2 topos e 2 fundos sem filtro (M5–D1):</b> igual ao acaso em todo tempo gráfico; a chance de vir mais um degrau é de 30–40%.</li>
<li><b>13 hipóteses de "meio do caminho"</b> (retração, duração, velocidade, volume, impulso, EMA, hora, rompimento, stop, regime): só H1 e abertura do dia se repetiram, e viraram a v1.</li>
<li><b>Variações da v1:</b> alvo fixo 2R/3R, entrada no rompimento, M5, K = 3. Todas rendem menos.</li>
<li><b>Quartas de vencimento:</b> 76 testes, nada passa a correção; o dia é mais amplo, mas sem direção.</li>
<li><b>Volume</b> (47: relativo, horário, OBV, CMF, VWAP, clímax): CMF20 é pico isolado; OBV e VWAP desabam no OOS.</li>
<li><b>Osciladores</b> (89: IFR, Estocástico, CCI, MFI, MACD, ROC, ADX, Bollinger): só o IFR14 &gt; 50 passa, e é empate (+1%).</li>
<li><b>Candles</b> (28) e <b>figuras</b> (13), sozinhos e combinados (728): nenhum concorda entre ramos. O veto de inside bar depende de 21 operações.</li>
<li><b>Stop (rodada 15, sobre a v4, 41 variações):</b> colchão além do fundo, stop pelo ATR (1–3), mais apertado ou mais folgado de pivô/ATR, mínima da barra, estrutura mais rápida, chandelier, zero a zero, seguir MME21/34, aperto por tempo, aperto por Estocástico &gt; 80 ou por preço esticado. Apertar perde total e alargar aumenta a queda. Só "não mover o stop" passa nos dois períodos, mas é empate: +3% no IS e +0,6% no OOS. O ganho vem de deixar o dia correr até o fim.</li>
<li><b>Stop em níveis do gráfico (rodada 16, 69 variações):</b> fundo anterior e topo rompido do M15, fundo do H1 e do H4, mínima do dia e do dia anterior, abertura, MME34/72 do M15, MMS72 do open, MME34 do H1, cada um como "abaixo do nível", "proteção extra até 1 ATR" e "aperto", e pular quando o risco passa de 2 a 3 ATR. Nada passa nos dois períodos. Pôr o stop abaixo de um nível mais distante aumenta a queda em todos os casos. O único efeito consistente é apertar o stop até a MME34 do M15: a queda cai 28% no IS e 13% no OOS, mas o total cai de 1% a 9%. É troca de risco por lucro, não melhora.</li>
<li><b>Outras médias</b> sobre a v2 (306): 0% de concordância entre ramos.</li>
<li><b>Outros tempos gráficos</b> (M5, M30, H1, H4; 14 hipóteses de concordância e discordância): a discordância com o H1 perde (−0,08 ATR no IS, −0,22 no OOS) e nenhum fator ao redor a salva. Como filtro na v3, nada passa.</li>
<li><b>Autópsia das melhores contra as piores operações</b> (94 características: candles, médias de vários tempos, volume, níveis, horário): efeitos pequenos (o maior foi 0,20). A regra "entrada perto da MMS17" dobra os pts/op no IS e falha no OOS.</li>
</ul>
<h2>v4: operar só nos sinais bons (adotada)</h2>
<p><b>Sinal bom</b> = Estocástico 14 (suav. 3) abaixo de 70 na compra (acima de 30 na venda) <b>ou</b> H4 neutro (o H1 já virou, o H4 ainda não). Ele surgiu do funil que começa pelos dias bons. O próprio sinal já mede a probabilidade: com ele o robô acerta 51% no IS e 62% no OOS, contra 39% e 40% sem ele, e perde menos quando erra. As operações fora do sinal bom têm média negativa nos dois períodos.</p>
<div class="tw"><table>
<thead><tr><th></th><th>IS ops</th><th>IS total</th><th>IS queda</th><th>IS total/queda</th><th>OOS ops</th><th>OOS total</th><th>OOS queda</th><th>OOS total/queda</th></tr></thead>
<tbody>
<tr><th>v3 (todas, 1 contrato)</th><td>562</td><td>+31.190</td><td>3.740</td><td>8,3</td><td>138</td><td>+26.860</td><td>6.295</td><td>4,3</td></tr>
<tr><th>2 contratos nos bons, 1 nos outros</th><td>562</td><td>+71.315</td><td>6.245</td><td>11,4</td><td>138</td><td>+54.485</td><td>6.825</td><td>8,0</td></tr>
<tr><th><b>só sinais bons, 1 contrato</b></th><td>387</td><td><b>+38.285</b></td><td><b>3.370</b></td><td>11,4</td><td>99</td><td><b>+29.135</b></td><td><b>1.990</b></td><td><b>14,6</b></td></tr>
<tr><th>só sinais bons, 2 contratos</th><td>387</td><td>+76.570</td><td>6.740</td><td>11,4</td><td>99</td><td>+58.270</td><td>3.980</td><td>14,6</td></tr>
</tbody></table></div>
<p class=m>Testado e descartado nesta rodada: <b>afastar o stop</b> nos sinais bons (0,25 a 1 ATR) piora o total e a queda nos dois períodos; a mão vale mais que o stop. <b>Modelo de probabilidade com 15 fatores</b> (regressão logística, treino 2022–23 e teste 2024–25): inverteu no teste (o quartil "mais provável" deu −13 pts/op), e reduzir de 2 para 1 contrato pela probabilidade baixou o total no IS e no OOS. Vizinhança do filtro: com o limite 70, os períodos 9, 14 e 21 superam a v3 no IS e reduzem a queda no OOS. Os limites 60 e 80 perdem total no IS.</p>
<h2>Painel de segurança (período inteiro, jan/22–out/26)</h2>
<div class="tw"><table>
<thead><tr><th></th><th>v3</th><th>v4 original (2 bons / 1 outros)</th><th>só bons, 1 contrato</th><th>só bons, 2 contratos</th></tr></thead>
<tbody>
<tr><th>total</th><td>+R$ 11.610</td><td>+R$ 25.160</td><td>+R$ 13.484</td><td><b>+R$ 26.968</b></td></tr>
<tr><th>fator de lucro</th><td>1,45</td><td>1,67</td><td>2,03</td><td>2,03</td></tr>
<tr><th>acerto</th><td>47%</td><td>47%</td><td>52%</td><td>52%</td></tr>
<tr><th>maior queda</th><td>R$ 1.259</td><td>R$ 1.365</td><td>R$ 674</td><td>R$ 1.348</td></tr>
<tr><th>maior queda no OOS</th><td>R$ 1.259</td><td>R$ 1.365</td><td>R$ 398</td><td>R$ 796</td></tr>
<tr><th>pior mês</th><td>−R$ 613</td><td>−R$ 743</td><td>−R$ 325</td><td>−R$ 650</td></tr>
<tr><th>meses positivos</th><td>72%</td><td>78%</td><td>79%</td><td>79%</td></tr>
<tr><th>Sharpe / Sortino (anual)</th><td>1,56 / 3,12</td><td>2,00 / 4,65</td><td>2,24 / 5,64</td><td>2,24 / 5,64</td></tr>
<tr><th>pior tempo para recuperar</th><td>102 pregões</td><td>107</td><td>112</td><td>112</td></tr>
<tr><th>capital mínimo (queda + margem)</th><td>R$ 1.359</td><td>R$ 1.565</td><td>R$ 774</td><td>R$ 1.548</td></tr>
</tbody></table></div>
<p class=m>Com o mesmo máximo de 2 contratos, "só bons" ganha mais que a v4 original e melhora o fator de lucro, o Sharpe, o pior mês e a queda no OOS, porque as operações fora do sinal bom perdem dinheiro. O ponto fraco que continua: em 2024 o robô ficou ~5 meses (112 pregões) abaixo do topo anterior.</p>
<h2>E se tivesse começado no pior momento?</h2>
<p>Simulei começar em cada um dos 1.189 pregões, de jan/2022 a set/2026, com 2 contratos fixos. <b>Em nenhuma data a banca quebra</b>, nem com R$ 1.548. O pior começo possível (12/08/2024, logo antes da maior queda) leva R$ 1.548 até R$ 200, exatamente a margem de 2 contratos: no limite. Com R$ 3.000, o pior saldo seria R$ 1.652. Depois de 3 meses, 90% das datas de início estão positivas (pior: −R$ 1.090). Depois de 6 meses, 98% (pior: −R$ 456). Depois de 12 meses, 100% (pior: +R$ 354; mediana: +R$ 5.084). Ressalva: o futuro pode ter uma queda maior que a do histórico. A prudência é ter capital para 1,5 a 2 vezes a pior queda: R$ 2.200 a R$ 2.900.</p>
<p class=m>Próximo eixo: saída (parcial, trailing por ATR, horário, stop no zero a zero). Scripts em scripts/daytrade/topos_fundos/.</p>
</main>"""
open(sys.argv[1], "w", encoding="utf-8").write(html)
print("ok", len(html))
