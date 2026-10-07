# C2 - Volume na saida e como contexto (WinCincoMedias v2, M30, 2026)

Baseline reproduzido exatamente pela copia de `simula`: +7.349,90 / 12 de 14 janelas / pior -117,00 / PF 1,63 / 241 trades / DD 781,50 / sem setembro 6.896,40.
Volume so de velas fechadas (decisao em j, execucao na abertura de j+1). Normalizacao: v / mediana do mesmo horario nos 20 pregoes anteriores (`_rel`) e versao crua (`_cru`); limiar = quantil expandido do passado. So 2026. Total: 162 variantes (+ baseline). Tabela completa: `c2_resultados.csv`, log: `c2_volume_saida_contexto_stdout.log`.

## Resultado por familia (melhor linha / controle de preco)
| familia | melhor volume | liq | jan+ | pior | DD | meses melhor | controle preco (mesma regra, range) | veredito |
|---|---|---|---|---|---|---|---|---|
| clímax CONTRA v_rel q90 | | 7.805 | 13/14 | -117 | 781,5 | 5 | r_rel q90: 7.691, 12/14, 3 meses | diferenca +114, dentro do ruido |
| clímax CONTRA v_cru q90 | | 8.511 | 13/14 | -117 | 580,9 | 6 | r_cru q90: 8.052; r_cru q80: 8.464, DD 518 | preco puro faz igual; nao e platô (q80 pior -282, q95 7.624) |
| clímax FAVOR (exaustao) | v_cru q95 7.974 | | 12/14 | -117 | 908 | 7 | r_cru q80 8.398, r_cru q95 7.813 | DD piora; preco iguala |
| secagem queda k3 v_rel | | 7.677 | 13/14 | -67 | 781,5 | 7 | r_rel k3: 6.690 (abaixo da base) | unico onde volume > preco, mas k2 6.480 / k4 6.861 (abaixo da base): sem platô |
| secagem abaixo-de-limiar | todas | 7.272-7.342 | 12/14 | -117 | 781,5 | 0-2 | - | inerte |
| contexto do dia (acumulado) | melhor baixo>=1,2: 7.834 (pior -358) | | 12/14 | -358 | 803 | 4 | - | todas as 36 linhas <= base em liquido; "so dia movimentado/parado" piora (menos trades) |
| contexto do mes | filtro so em mes alto 0,9: 8.523 | | 12/14 | -117 | 781,5 | 1 | r_mes 0,9: 7.803 | ganho de 1 mes so; 1,0=7.755, 1,1=7.027 (nao e platô); controle de preco parecido |

Notas: climax contra, escopo "favor" e "todos" dao resultado identico (operacoes neutras quase nunca disparam). Secagem por limiar absoluto (<0,6/<0,8) praticamente nao muda nada. No mes, comeco do ano (sem 15 pregoes anteriores) e primeiros 3 pregoes do mes = NaN = sem restricao.

## Mes a mes (janela: base | climax v_rel q90 | climax r_rel q90 | climax v_cru q90 | secagem v_rel k3)
01-07: 2985 | 3056 | 3048 | 2977 | 2562; 02-01: 816|816|816|952|942; 03-01: 42|42|42|337|340; 05-01: 928|996|910|956|866; 07-01: 208|292|200|208|245; 08-01: 18|37|239|205|369; 08-18: -50|183|-50|215|-67; 09-01: 454|435|537|916|412; 10-01: -117|-117|-117|-117|24,5; demais iguais.
O ganho do clímax v_rel q90 vem de 08-18 (+232), 05-01 (+68), 07-01 (+83), 01-07 (+71); perde 20 em 09-01. Sao mudancas pequenas em poucas barras.

## Conclusao
Volume na saida e como contexto NAO acrescenta de forma robusta. O que melhora (clímax contra, secagem k3) ou e igualado pelo controle de preco (range) ou nao tem platô na vizinhanca; contexto do dia piora tudo; contexto do mes depende de 1 mes e o controle de preco da quase o mesmo. Se algo for levado a validacao 2025, a unica linha com plateau em q (80/90/95 todas >= base em liquido, 13/14 janelas, DD igual) e o clímax contra normalizado, mas com vantagem sobre o controle de ~+100 a +400 e 5 vs 3 meses melhores: fraca.

## Candidata congelada (1, fraca) - `c2_candidatas.py`
`c2a_climax_contra_vrel_q90`: `saida_fn=fn_climax("v_rel", 0.90, "contra")`, `saida_escopo="todos"`; v_rel = v / mediana do mesmo horario dos 20 pregoes anteriores (min 5), quantil 90 expandido do passado (min 100 barras, shift 1). Resultado 2026: +7.805,20, 13/14, pior -117, PF 1,68, 248 trades, DD 781,50, sem setembro 7.370,70, 5 meses melhores. Controle de preco r_rel q90 = +7.691,20, 12/14, 3 meses melhores.
