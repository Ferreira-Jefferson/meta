import json
b = {x["dia"]: x for x in json.load(open("p5_negativos.json"))}
D = {
"2022-04-13": ("venda Falha da alta inicial 11:00 stopada; dia de rotacao (ef 0,02)", "no 11:30 a posicao vendida estava aberta (1 posicao por vez) e nenhuma FAZER de compra sinalizou; compra de 11:30 renderia +985 pts"),
"2022-05-17": ("compra recuo a media 8 (11:00) e venda F1 (12:15) contra um dia sem direcao; a F1 so entrou porque o A2 da v2 soltou o veto (v1 -120, v2 -193)", "venda das 09:45 (+1.405 pts): nenhuma FAZER sinalizou as 09:45"),
"2022-08-18": ("compra de suporte 10:15 stopada e venda pullback 11:30 zerada no fim; rotacao", "venda das 09:45 (+1.030 pts): nenhuma FAZER sinalizou as 09:45; o robo comprou 10:15 contra a queda"),
"2022-09-21": ("unica operacao: venda pullback EMA20 13:15 stopada (v1 nao operou; a v2 passou a operar por A2/pullback)", "compra das 15:15 (+1.960 pts): nenhuma FAZER de compra tardia; apos 13:15 o robo ficou sem ops por tempo e sem sinal"),
"2022-12-12": ("compra F1 09:30 e venda F1 12:30 stopadas; a venda so entrou pelo A2 (v1 -93, v2 -213)", "venda das 10:30 (+3.670 pts): FAZER nos dois lados (pullback venda x suporte compra), 'nao entra'"),
"2024-02-01": ("tres vendas stopadas (gap_fade, pullback, recuo EMA21) em dia de rotacao sem direcao (ef 0,03); C6/C7/C8 mudaram so 1,6 R$", "compra das 13:15 (+1.255 pts): posicao vendida aberta (pullback 12:30) e nenhuma FAZER de compra"),
"2024-04-26": ("gap_fade venda 09:45 stopado -82; o rompimento da 1a hora (C4, +30) amorteceu (v2 -82)", "compra das 09:15 (+1.870 pts): nenhuma FAZER sinalizou as 09:15; o robo entrou vendido as 09:45"),
"2024-07-30": ("gap_fade compra tres vezes em 30 min, os tres stops (-29, -19, -22): entra de novo no mesmo gap sem confirmacao", "venda das 09:15 (+980 pts): posicao comprada aberta (gap_fade contra o movimento)"),
"2024-09-05": ("F2 'vende falha da maxima matinal' 10:00 stopada; unica op", "compra das 09:45 (+835 pts): nenhuma FAZER sinalizou as 09:45; a unica FAZER foi de venda e foi contra"),
"2024-10-25": ("F2 matinal fechou +47,58 no alvo curto, depois pullback venda 13:30 stopado -87,89", "venda das 11:15 (+685 pts): nenhuma FAZER sinalizou as 11:15; o alvo curto da manha ja saira"),
"2025-06-20": ("F2 matinal +61,56 no alvo e depois F1 12:15 stopada -108,71, liberada pelo A2 (v1 +61,56, v2/v3 -39,16)", "venda das 09:15 (+2.025 pts): nenhuma FAZER sinalizou as 09:15; o alvo fixo de 1,5 ATR da F2 as 10:00 tirou +61 de uma queda de 2.025 pts"),
"2025-07-11": ("F2 gap de baixa preenche (compra 09:15) stopada -102 e F1 venda 12:45 stopada -106, esta liberada pelo A2 (v1 -102, v2 -208)", "venda das 09:15 (+1.085 pts): a compra F2 estava aberta (contra o movimento); o gap de baixa continuou"),
}
out = []
for d, (diag, mov) in D.items():
    x = b[d]
    out.append(dict(dia=d, tipo=x["tipo"], ef=x["ef"], v3_brl=x["brl"], v2_brl=x["v2"], v1_brl=x["v1"], diagnostico=diag,
                    maior_movimento_nao_pego=dict(hindsight=x["melhor"], por_que=mov), trades_v3=x["trades"]))
json.dump(out, open("ciclo3_negativos.json", "w"), indent=1, ensure_ascii=False)
print(len(out))
