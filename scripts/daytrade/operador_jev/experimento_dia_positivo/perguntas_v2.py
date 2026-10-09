"""Perguntas v2 do experimento "perguntas para o dia positivo" (formato do endpoint /api/alpha/decisions do Jev).

Consolidacao das propostas dos 4 agentes (analises/grupo_a..d.md), 20 dias de TREINO. Funde redundancias (varias liam "tendencia")
e descarta as "especificas" de 1-2 dias (reconquista da abertura, fundo/topo defendido, volatilidade contraindo, stop alem do pivo,
profundidade do recuo). TODOS os limiares numericos abaixo (0,25 ATRd; 60%; 0,15/0,30 de eficiencia; 1,5x e 1,2x de volume;
50% de devolucao; 12 e 8 velas...) foram escolhidos pelos agentes OLHANDO os dias de treino -- sao hipoteses, nao parametros
calibrados. A validacao (20 dias nunca vistos na criacao) e o unico teste que eles tem.

As perguntas leem as linhas "DERIVADOS" do pacote de mercado (mercado.montar_estado(derivados=True)); sem elas o Jev teria de
fazer a aritmetica de cabeca a partir da lista M15.

Estrutura: MERCADO_V2 (17 perguntas de contexto, independem da posicao), GESTAO_V2 (2, so com posicao), FINAIS (acao/stop/alvo/mao,
as mesmas do v1; a versao A acrescenta a frase que manda considerar as respostas da etapa 1), VOTOS (a regra do veto da versao B).
"""
from __future__ import annotations

SUF = " Responda só com o que as velas fechadas do estado mostram (use as linhas DERIVADOS quando ajudarem)."

# --------------------------------------------------------------------------- perguntas de mercado (17)
# campos: id, tipo, rotulo (curto, p/ o texto da etapa 2), instructions, criteria, alvo (resposta-alvo -> decisao), origem, geral
M: list[dict] = [
    dict(id="v2_dia_tipo", tipo="choice", rotulo="Tipo de dia",
         texto=("Classifique o dia até agora. 'alta_dirigida': o deslocamento desde a abertura é de pelo menos +0,25 ATR diário E o valor absoluto do "
                "deslocamento é pelo menos 60% da amplitude do dia (máxima menos mínima desde a abertura). 'baixa_dirigida': o mesmo para baixo "
                "(deslocamento de pelo menos -0,25 ATR diário e pelo menos 60% da amplitude). 'rotacao': o dia já tem 8 ou mais velas M15 e não "
                "cumpre nenhuma das duas condições (o preço anda nos dois sentidos e devolve). 'indefinido': menos de 8 velas M15 fechadas hoje."),
         crit={"alta_dirigida": "deslocamento para cima nas duas condições", "baixa_dirigida": "deslocamento para baixo nas duas condições",
               "rotacao": "8+ velas e nenhuma das duas condições (anda e devolve)", "indefinido": "menos de 8 velas hoje"},
         alvo="alta_dirigida -> só comprar ou ficar fora; baixa_dirigida -> só vender ou fora; rotacao -> sem sinal a favor, não perseguir; indefinido -> fora",
         origem="gb_01 + gc1 + P02 + P04 (4 grupos; 5/5 dias no grupo_b)", geral="geral (falha no dia de faixa 06-25: 2 falsos positivos)"),
    dict(id="v2_eficiencia", tipo="score", rotulo="Eficiência direcional do dia",
         texto=("Qual a eficiência direcional do dia? Use a linha 'Eficiência direcional' dos DERIVADOS: valor absoluto de (último fechamento menos abertura) "
                "dividido pela soma das amplitudes (máxima menos mínima) de todas as velas M15 de hoje. Com menos de 8 velas hoje, responda nível 0. "
                "Nível 0 = abaixo de 0,15 (o preço anda e devolve); nível 1 = de 0,15 a 0,30; nível 2 = acima de 0,30 (anda numa direção e não devolve)."),
         crit=["0 = abaixo de 0,15 (anda e devolve)", "1 = de 0,15 a 0,30", "2 = acima de 0,30 (anda numa direção e não devolve)"],
         alvo="2 -> só a favor, sem alvo fixo, nunca fade; 0 -> rotação: ficar fora ou alvo curto; 1 -> seguir as demais",
         origem="gc1 (grupo_c; 5/5 dias)", geral="geral (separa o dia direcional; falha no início do dia em V)"),
    dict(id="v2_preco_vs_ref", tipo="choice", rotulo="Preço contra abertura e fechamento de ontem",
         texto=("Compare o último fechamento M15 com a abertura de hoje e com o fechamento de ontem (linha 'Gap' / 'Abertura do dia'). Onde está o preço?"),
         crit={"acima_de_ambos": "acima da abertura de hoje E acima do fechamento de ontem", "entre": "entre os dois (um acima e outro abaixo)",
               "abaixo_de_ambos": "abaixo da abertura de hoje E abaixo do fechamento de ontem"},
         alvo="acima_de_ambos -> só comprar; abaixo_de_ambos -> só vender; entre -> exige confirmação das outras perguntas",
         origem="P02 (grupo_d; 5/5) + P3/P5 do grupo_a", geral="geral"),
    dict(id="v2_rompe_ontem", tipo="choice", rotulo="Rompimento da máxima/mínima de ontem",
         texto=("A última vela M15 fechada fechou além da máxima ou da mínima de ontem (linha 'Ontem' dos DERIVADOS)? Se sim, o volume dela é pelo menos 1,5 vez "
                "a média das 20 velas anteriores (linha de volume dos DERIVADOS)? 'voltou_para_dentro': hoje o preço já passou a máxima ou a mínima de ontem, "
                "mas o último fechamento está de volta dentro da faixa de ontem. 'Nenhum rompimento' é uma resposta válida e comum."),
         crit={"acima_com_volume": "fechou acima da máxima de ontem com volume >= 1,5x a média das 20 anteriores",
               "abaixo_com_volume": "fechou abaixo da mínima de ontem com volume >= 1,5x a média",
               "sem_volume": "fechou fora da faixa de ontem, mas com volume abaixo de 1,5x",
               "voltou_para_dentro": "passou a máxima/mínima de ontem hoje, mas fechou de volta dentro",
               "nenhum": "dentro da faixa de ontem e sem ter passado dela hoje"},
         alvo="acima_com_volume -> lado comprador; abaixo_com_volume -> lado vendedor; voltou_para_dentro -> fora; demais -> sem sinal",
         origem="P1 (grupo_a; 4/5) + P03 (grupo_d; 3/5)", geral="geral"),
    dict(id="v2_rompe_dia", tipo="choice", rotulo="Rompimento da máxima/mínima do dia",
         texto=("A última vela M15 fechada fechou além da máxima (ou da mínima) de todas as velas de hoje até a vela anterior (linha 'ultima vela fechou alem da max/min do dia' "
                "dos DERIVADOS)? Se sim, o volume dela é pelo menos 1,2 vez a média das 10 velas anteriores?"),
         crit={"rompeu_alta_com_volume": "fechou acima da máxima do dia até a vela anterior, volume >= 1,2x a média das 10 anteriores",
               "rompeu_baixa_com_volume": "fechou abaixo da mínima do dia até a vela anterior, volume >= 1,2x a média das 10 anteriores",
               "rompeu_sem_volume": "rompeu a máxima ou a mínima do dia, mas com volume abaixo de 1,2x",
               "nenhum": "fechou dentro da faixa do dia"},
         alvo="rompeu_*_com_volume -> não operar contra o rompimento (não vender nova máxima, não comprar nova mínima); nenhum -> sem informação",
         origem="gb_02 + gc3 + P06 (3 grupos)", geral="geral (tira também alguns acertos de contra-tendência)"),
    dict(id="v2_seguimento", tipo="choice", rotulo="Seguimento do rompimento",
         texto=("Nas últimas 5 velas M15 fechadas (sem contar a última), alguma vela fechou além da máxima/mínima de ontem, da máxima/mínima do dia até então "
                "ou da faixa das 12 velas anteriores? Se sim, o fechamento da última vela ficou ALÉM do fechamento da vela do rompimento (seguiu) "
                "ou voltou para dentro/atrás dele (falhou)? Se não houve rompimento recente, 'sem_rompimento'."),
         crit={"seguiu": "rompimento recente e o fechamento atual segue além dele", "falhou": "rompimento recente e o preço voltou para dentro/atrás dele",
               "sem_rompimento": "nenhum rompimento nas últimas 5 velas"},
         alvo="seguiu -> a favor do rompimento; falhou -> contra o rompimento falho (ou fora); sem_rompimento -> sem sinal",
         origem="P8 (grupo_a; 5/5) + P09 (grupo_d; 3/5)", geral="geral"),
    dict(id="v2_faixa_rompida", tipo="noul", rotulo="Saída de faixa estreita",
         texto=("Hoje há pelo menos 13 velas M15 fechadas? Se sim: a faixa das 12 velas anteriores à última (linha 'Faixa das 12 velas' dos DERIVADOS) é menor que 1 ATR diário, "
                "a última vela fechou fora dessa faixa e a amplitude dela é pelo menos 1,5 vez o ATR M15? Se faltarem velas ou a vela não saiu da faixa, responda não."),
         crit=None,
         alvo="sim -> o movimento começou, o lado é o do fechamento; entrar a favor sem perseguir",
         origem="P2 (grupo_a; 3/5)", geral="geral"),
    dict(id="v2_lateral_morta", tipo="noul", rotulo="Mercado lateral e parado",
         texto=("Nas últimas 8 velas M15 fechadas, a faixa total (linha 'Últimas 8 velas' dos DERIVADOS) é menor que 0,5 ATR diário E o volume médio dessas 8 velas "
                "é menor que 70% do volume médio das velas de hoje? Se sim, o mercado está parado. Se não, responda não."),
         crit=None,
         alvo="sim -> ficar fora / não abrir; sair se estiver posicionado; não -> sem efeito",
         origem="P7 (grupo_a; 5/5) + P07 (grupo_d; 4/5)", geral="geral"),
    dict(id="v2_estrutura", tipo="choice", rotulo="Estrutura de topos e fundos de hoje",
         texto=("Compare os dois últimos fundos e os dois últimos topos relevantes de hoje (pontos de virada com pelo menos 2 velas de cada lado; as linhas de swing dos DERIVADOS "
                "ajudam). Use pelo menos as 8 últimas velas fechadas. Qual é a estrutura de preço de hoje?"),
         crit={"alta": "topos E fundos mais altos que os anteriores", "baixa": "topos E fundos mais baixos que os anteriores",
               "lateral": "sem sequência clara ou preço preso numa faixa", "indefinido": "poucas velas para decidir"},
         alvo="alta -> comprar/segurar compra, não vender; baixa -> vender/segurar venda, não comprar; lateral -> fora",
         origem="P01 (grupo_d; 5/5)", geral="geral (correlacionada com v2_dia_tipo)"),
    dict(id="v2_swing_rompido", tipo="choice", rotulo="Fechamento além do último topo/fundo de swing",
         texto=("Compare o último fechamento com o último topo de swing e o último fundo de swing de hoje (linha dos DERIVADOS). Ele fechou acima do último topo, "
                "abaixo do último fundo, ou nenhum dos dois?"),
         crit={"acima_do_topo": "último fechamento acima do último topo de swing de hoje", "abaixo_do_fundo": "último fechamento abaixo do último fundo de swing de hoje",
               "nenhum": "dentro da faixa entre o último fundo e o último topo (ou sem swing formado)"},
         alvo="acima_do_topo -> permite comprar com stop abaixo do último fundo; abaixo_do_fundo -> permite vender; nenhum -> fora",
         origem="gc5 (grupo_c; 4/5)", geral="geral (hipótese; depende da definição de swing)"),
    dict(id="v2_h1", tipo="choice", rotulo="Direção do H1",
         texto=("Olhe os H1 completos de hoje (últimas 3 horas fechadas): os fechamentos H1 vêm subindo, descendo ou sem direção? E a última vela M15 fechou do mesmo lado "
                "do fechamento H1 de 3 horas atrás? Só diga 'alta' ou 'baixa' se os dois concordam."),
         crit={"alta": "H1 subindo e M15 acima do fechamento H1 de 3 h atrás", "baixa": "H1 descendo e M15 abaixo do fechamento H1 de 3 h atrás",
               "misto": "não concordam, ou menos de 3 H1 completos hoje"},
         alvo="alta/baixa -> operar só na direção do H1; misto -> sem sinal",
         origem="P5 (grupo_a; 4/5)", geral="geral"),
    dict(id="v2_pullback", tipo="choice", rotulo="Pullback retomado a favor do dia",
         texto=("Em dia com direção (deslocamento desde a abertura de pelo menos 0,25 ATR diário em módulo e eficiência direcional de pelo menos 0,15), o preço recuou contra o dia "
                "por 1 a 3 velas M15 (entre 30% e 60% da última perna a favor), a última vela fechou de volta no sentido do dia (fechamento acima da própria abertura numa alta; "
                "abaixo numa baixa) e o preço não perdeu o último fundo (alta) ou topo (baixa) de swing de hoje nem a abertura do dia?"),
         crit={"retomada_alta": "dia de alta, recuo de 1-3 velas e a última vela retomou para cima sem perder o último fundo nem a abertura",
               "retomada_baixa": "dia de baixa, recuo de 1-3 velas e a última vela retomou para baixo sem perder o último topo nem a abertura",
               "nenhuma": "não há pullback retomado (ou o dia não tem direção)"},
         alvo="retomada_alta -> entrar comprando (limite no fechamento, stop no pivô, sem alvo); retomada_baixa -> entrar vendendo; nenhuma -> esperar",
         origem="gb_03 + gc6 (2 grupos; ~3/5)", geral="geral (é a entrada da escada v4.1 em forma de pergunta)"),
    dict(id="v2_gap", tipo="choice", rotulo="Situação do gap",
         texto=("Se hoje houve gap relevante (abertura diferente do fechamento de ontem em pelo menos 0,15 ATR diário), qual a situação dele agora (linha 'Gap' dos DERIVADOS)? "
                "Fração preenchida: 0% = preço na abertura, 100% = voltou ao fechamento de ontem, negativa = o preço se afastou do fechamento de ontem."),
         crit={"sem_gap": "gap menor que 0,15 ATR diário (ou inexistente)", "ampliando": "preço se afastou do fechamento de ontem (fração negativa)",
               "preenchendo": "preenchido entre 0% e 75%", "preenchido": "preenchido em 75% ou mais"},
         alvo="ampliando -> continuação, não buscar reversão (só no sentido do gap); preenchendo -> na direção do preenchimento; preenchido -> não entrar mais nessa direção",
         origem="P05 (grupo_d; 3/5) + gb_05 (grupo_b; 3/5)", geral="geral (evidência fraca para 'preenchido')"),
    dict(id="v2_extremo_novo", tipo="choice", rotulo="Extremo novo do dia nas últimas velas",
         texto=("O extremo do dia (máxima ou mínima) foi renovado nas últimas 6 velas M15 fechadas (linhas 'Máxima do dia ... há N velas' dos DERIVADOS: N menor que 6 = renovou)?"),
         crit={"renovou_maxima": "máxima do dia renovada nas últimas 6 velas", "renovou_minima": "mínima do dia renovada nas últimas 6 velas",
               "nenhum": "nenhum extremo novo nas últimas 6 velas"},
         alvo="renovou -> tendência ativa, seguir a favor (veto a operar contra); nenhum -> sinal tardio, ficar fora de entrada nova a favor",
         origem="P13 (grupo_d; 3/5) + gc8 (grupo_c; 5/5)", geral="geral só em dia direcional"),
    dict(id="v2_devolveu_50", tipo="noul", rotulo="Devolveu mais de 50% do deslocamento",
         texto=("O preço devolveu mais de 50% do deslocamento máximo que o dia fez a partir da abertura (linha 'Deslocamento máximo do dia' dos DERIVADOS)?"),
         crit=None,
         alvo="sim -> sair ou apertar o stop de posição na direção da manhã; não abrir novas posições nessa direção; não -> manter",
         origem="gb_04 (grupo_b)", geral="geral (inerte nos dias que seguem; decisiva nos que viram)"),
    dict(id="v2_perna_esgotada", tipo="noul", rotulo="Perna do dia esgotada",
         texto=("A perna do dia (deslocamento da abertura até o extremo do dia no sentido do deslocamento máximo) andou mais de 1 ATR diário (amplitude do dia nos DERIVADOS) "
                "E nas últimas 3 velas fechadas o extremo não foi renovado (velas desde o extremo >= 3)? Se uma das duas coisas não é verdade, responda não."),
         crit=None,
         alvo="sim -> perna parou depois de longa extensão: sair da posição a favor / apertar o stop; não abrir nova entrada na mesma direção",
         origem="P6 (grupo_a; 3/5) [adaptada: perna = abertura até o extremo do dia, em vez do último pivô de 8 velas]", geral="geral"),
    dict(id="v2_tendencia_limpa", tipo="noul", rotulo="Tendência limpa (segurar sem alvo)",
         texto=("O fechamento está a mais de 1 ATR diário da abertura, o H1 está na mesma direção e nenhuma das últimas 6 velas M15 fechou contra essa direção por mais de "
                "0,5 ATR M15 (diferença entre abertura e fechamento da vela)? Se sim, o dia é de tendência limpa."),
         crit=None,
         alvo="sim -> segurar a favor sem alvo fixo, só com stop de trailing; não -> sem efeito",
         origem="P9 (grupo_a; 2/5 sim, 'não' nos demais)", geral="geral (resposta 'não' nos dias sem tendência)"),
]

# --------------------------------------------------------------------------- gestao (so com posicao)
G: list[dict] = [
    dict(id="v2_estrutura_preservada", tipo="noul", rotulo="Estrutura a favor preservada",
         texto=("Para a posição aberta (linha POSICAO), desde a entrada: o último fundo M15 (compra) ou topo M15 (venda) formado depois da entrada continua sem ser perdido por "
                "nenhum fechamento E o preço fez novo extremo a favor nas últimas 8 velas M15 ou está a menos de 1 ATR M15 dele?"),
         crit=None,
         alvo="sim -> manter (sem alvo, deixar correr); não -> apertar o stop ao pivô ou zerar",
         origem="gb_06 + P11 + gc7 (3 grupos)", geral="geral (é o 'deixar correr, sair quando a estrutura quebra' da escada)"),
    dict(id="v2_g_acao", tipo="choice", rotulo="O que fazer com a posição",
         texto=("O que fazer com a posição aberta agora? 'manter': o preço está do lado certo da abertura do dia, o último fundo (compra) ou topo (venda) de swing formado depois da entrada "
                "não foi perdido por nenhum fechamento e a eficiência direcional do dia é de pelo menos 0,15. 'stop_pivo': perdeu UMA dessas três coisas (ou devolveu mais de 50% "
                "do deslocamento máximo do dia), mas a posição ainda tem lucro aberto: mover o stop para o último pivô a favor. 'zerar': perdeu DUAS ou mais, ou a eficiência do dia "
                "caiu abaixo de 0,15."),
         crit={"manter": "manter posição e stop como estão", "stop_pivo": "mover o stop para o último pivô a favor (compra: sobe; venda: desce)",
               "zerar": "zerar a posição"},
         alvo="manter / apertar stop (stop_pivo) / zerar conforme os três critérios",
         origem="gc7 (grupo_c; 4/5) + gb_04", geral="geral"),
]

# --------------------------------------------------------------------------- perguntas finais (decisao)
_ACAO = "Qual a melhor ação agora, com ordem limitada no último fechamento (válida por 3 velas M15)?"
_A_EXTRA = (" O estado traz, depois do mercado, as RESPOSTAS DA ETAPA 1: probabilidades do Jev para perguntas sobre este mesmo estado (tipo de dia, estrutura, "
            "rompimentos, H1...). Leve essas respostas em conta.")
FINAIS: list[dict] = [
    dict(id="acao", tipo="choice", texto=_ACAO, crit={"comprar": "comprar com ordem limitada", "vender": "vender com ordem limitada", "fora": "ficar de fora"}),
    dict(id="stop", tipo="choice", texto="Se fosse operar, onde fica o ponto que, se atingido, prova que a tese estava errada?",
         crit={"0.5atr": "0,5 ATR M15 da entrada", "1atr": "1 ATR M15 da entrada", "1.5atr": "1,5 ATR M15 da entrada",
               "pivo": "no último pivô (fundo para compra, topo para venda) ou extremo recente"}),
    dict(id="alvo", tipo="choice", texto="Se fosse operar, qual o alvo?",
         crit={"sem_alvo": "sem alvo: deixar correr com stop seguindo", "1atr": "alvo de 1 ATR M15", "2atr": "alvo de 2 ATR M15", "3atr": "alvo de 3 ATR M15"}),
    dict(id="mao", tipo="choice", texto="Se fosse operar, quantos contratos (1 ou 2)?", crit={"1": "1 contrato", "2": "2 contratos"}),
]

# --------------------------------------------------------------------------- regra do veto (versao B)
# Cada pergunta de DIRECAO vota +1 (alta/compra) ou -1 (baixa/venda) numa categoria. Derivado das "resposta-alvo" dos agentes (campo `alvo` acima),
# NAO de olhar a validacao: onde a resposta-alvo diz "so comprar / nao vender", a categoria vota +1 (e vice-versa).
VOTOS: dict[str, dict[str, int]] = {
    "v2_dia_tipo": {"alta_dirigida": +1, "baixa_dirigida": -1},
    "v2_estrutura": {"alta": +1, "baixa": -1},
    "v2_h1": {"alta": +1, "baixa": -1},
    "v2_preco_vs_ref": {"acima_de_ambos": +1, "abaixo_de_ambos": -1},
    "v2_rompe_ontem": {"acima_com_volume": +1, "abaixo_com_volume": -1},
    "v2_rompe_dia": {"rompeu_alta_com_volume": +1, "rompeu_baixa_com_volume": -1},
    "v2_swing_rompido": {"acima_do_topo": +1, "abaixo_do_fundo": -1},
}
P_VETO = 0.5                       # P da categoria >= 0,5 conta como voto
FORA_SE_NOUL = {"v2_lateral_morta": 0.5}   # 'mercado parado' (P>=0,5) -> ficar fora (5/5 dias dos grupos a e d)
P_ESTRUTURA_PRESERVADA = 0.5       # gestao B: P(estrutura preservada) < 0,5 -> apertar o stop ao pivo


# --------------------------------------------------------------------------- montagem para a API
def _q(texto, tipo, crit, extra=""):
    q = {"type": tipo, "instructions": texto + extra}
    if tipo == "choice":
        q["criteria"] = dict(crit)
    elif tipo == "score":
        q["criteria"] = list(crit)
    return q


QUESTOES_MERCADO_V2 = {d["id"]: _q(d["texto"], d["tipo"], d["crit"], SUF) for d in M}
QUESTOES_GESTAO_V2 = {d["id"]: _q(d["texto"], d["tipo"], d["crit"], SUF) for d in G}
QUESTOES_GESTAO_B = {"v2_estrutura_preservada": QUESTOES_GESTAO_V2["v2_estrutura_preservada"]}
# B: mercado v2 + finais numa chamada so
QUESTOES_B = {**QUESTOES_MERCADO_V2, **{d["id"]: _q(d["texto"], d["tipo"], d["crit"], SUF) for d in FINAIS}}
# A etapa 2: finais (acao com a frase das respostas) + gestao completa
QUESTOES_FINAIS_A = {d["id"]: _q(d["texto"], d["tipo"], d["crit"], (_A_EXTRA if d["id"] == "acao" else "") + SUF) for d in FINAIS}
QUESTOES_GESTAO_A = dict(QUESTOES_GESTAO_V2)

ROTULO = {d["id"]: d["rotulo"] for d in M + G}
# compat com gera_viewer (id, tipo, ref, texto)
MERCADO = [(d["id"], d["tipo"], d["origem"], d["texto"], d["crit"]) for d in M] + [(d["id"], d["tipo"], "decisao", d["texto"], d["crit"]) for d in FINAIS]
GESTAO = [(d["id"], d["tipo"], d["origem"], d["texto"], d["crit"]) for d in G]


def texto_respostas(resp: dict, ids=None) -> str:
    """Respostas da etapa 1 em texto para o estado da etapa 2: pergunta -> resposta/probabilidade (versao A)."""
    L = ["RESPOSTAS DA ETAPA 1 (probabilidades do Jev sobre este mesmo estado; 1 = certeza):"]
    for d in M:
        qid = d["id"]
        if ids is not None and qid not in ids:
            continue
        r = (resp or {}).get(qid)
        if r is None:
            L.append(f"- {d['rotulo']}: sem resposta")
        elif d["tipo"] == "noul":
            L.append(f"- {d['rotulo']}? P(sim) = {float(r):.2f}")
        elif d["tipo"] == "choice":
            pr = ", ".join(f"{c} {p:.2f}" for c, p in sorted(r["p"].items(), key=lambda x: -x[1]))
            L.append(f"- {d['rotulo']}: {r['c']} (P = {r['p'].get(r['c'], 0.0):.2f}) [{pr}]")
        else:
            L.append(f"- {d['rotulo']}: nível esperado {r['s']:.2f} (de 0 a {len(d['crit']) - 1})")
    return "\n".join(L)


def vetos(rm: dict) -> dict:
    """Regra do veto da versao B (pura). Devolve {'comprar': [motivos], 'vender': [motivos], 'fora': [motivos]}.
    Voto contra a acao = categoria de DIRECAO oposta com P >= P_VETO; 'fora' = pergunta de mercado parado com P >= limiar."""
    out = {"comprar": [], "vender": [], "fora": []}
    for qid, cats in VOTOS.items():
        r = (rm or {}).get(qid)
        if not isinstance(r, dict):
            continue
        for cat, sinal in cats.items():
            p = float(r.get("p", {}).get(cat, 0.0))
            if p >= P_VETO:
                out["vender" if sinal > 0 else "comprar"].append(f"{qid}={cat} (P {p:.2f}) contra")
    for qid, lim in FORA_SE_NOUL.items():
        r = (rm or {}).get(qid)
        if isinstance(r, (int, float)) and float(r) >= lim:
            out["fora"].append(f"{qid} P(sim) {float(r):.2f}")
    return out


def gera_md() -> str:
    L = ["# Perguntas v2 - experimento \"perguntas para o dia positivo\"", "",
         "Consolidação das propostas dos 4 agentes (`analises/grupo_a..d.md`, 20 dias de TREINO). Fundidas as redundantes; descartadas as "
         "'específicas' de 1-2 dias (reconquista da abertura, fundo/topo defendido, volatilidade contraindo, stop além do pivô, profundidade do recuo).", "",
         "**Aviso sobre os limiares:** todos os números (0,25 ATRd; 60% da amplitude; eficiência 0,15/0,30; volume 1,5x e 1,2x; 50% de devolução; 12 e 8 velas) foram "
         "escolhidos pelos agentes olhando os dias de treino. Foram mantidos como estão (ajustar agora seria olhar a validação) e são hipóteses, não parâmetros calibrados. "
         "Duas adaptações: P6 `perna_esgotada` usa a perna 'abertura até o extremo do dia' (o pivô de 8 velas não está no pacote) e P8 `seguimento` olha rompimentos das últimas 5 velas "
         "(sem contar a última) para haver velas seguintes.", "",
         "As perguntas leem as linhas **DERIVADOS** do pacote (`montar_estado(derivados=True)`).", "",
         "## Perguntas de mercado (17, independem da posição)", "",
         "| id | tipo | categorias / níveis | resposta-alvo -> decisão | origem | geral/específica |", "|---|---|---|---|---|---|"]
    for d in M:
        c = d["crit"]
        cs = "P(sim)" if c is None else ("; ".join(f"`{k}`" for k in c) if isinstance(c, dict) else "; ".join(c))
        L.append(f"| `{d['id']}` | {d['tipo']} | {cs} | {d['alvo']} | {d['origem']} | {d['geral']} |")
    L += ["", "### Instructions completos", ""]
    for d in M + G:
        L.append(f"**`{d['id']}`** ({d['tipo']}): {d['texto']}")
        if isinstance(d["crit"], dict):
            L.append("  - " + "; ".join(f"`{k}`: {v}" for k, v in d["crit"].items()))
        elif isinstance(d["crit"], list):
            L.append("  - níveis: " + "; ".join(d["crit"]))
        L.append("")
    L += ["## Gestão (só com posição)", "",
          "| id | tipo | resposta-alvo -> decisão | origem |", "|---|---|---|---|"]
    for d in G:
        L.append(f"| `{d['id']}` | {d['tipo']} | {d['alvo']} | {d['origem']} |")
    L += ["", "## Perguntas finais (iguais às do v1)", "",
          "`acao` {comprar, vender, fora}, `stop` {0.5atr, 1atr, 1.5atr, pivo}, `alvo` {sem_alvo, 1atr, 2atr, 3atr}, `mao` {1, 2}. Limiar 0,3 (P da escolha), versão `jev-1.13-20260917`. "
          "Na versão A a pergunta `acao` acrescenta: \"" + _A_EXTRA.strip() + "\"", "",
          "## Regra do veto (versão B), derivada das respostas-alvo", "",
          f"A ação do Jev (comprar/vender, com P >= limiar 0,3, como no v1) só é aceita se nenhuma pergunta de DIREÇÃO votar contra ela. "
          f"Voto = categoria com P >= {P_VETO}:", "",
          "| pergunta | vota COMPRA (+1) | vota VENDA (-1) |", "|---|---|---|"]
    for qid, cats in VOTOS.items():
        mais = ", ".join(c for c, s in cats.items() if s > 0)
        menos = ", ".join(c for c, s in cats.items() if s < 0)
        L.append(f"| `{qid}` | `{mais}` | `{menos}` |")
    L += ["",
          "- comprar é vetado se QUALQUER pergunta acima votar venda; vender é vetado se qualquer votar compra (sinais mistos -> os dois vetados -> fica de fora).",
          f"- `v2_lateral_morta` com P(sim) >= {FORA_SE_NOUL['v2_lateral_morta']} veta as duas ações (mercado parado: ficar fora).",
          "- `v2_dia_tipo = rotacao` NÃO veta: os agentes divergem (grupo_b: sem direção -> fora; grupo_c: em rotação o fade é permitido).",
          f"- Gestão: se P(`v2_estrutura_preservada`) < {P_ESTRUTURA_PRESERVADA}, o motor aperta o stop ao último pivô a favor (só a favor); senão mantém. O stop móvel de 'deixar correr' "
          "(posição sem alvo) segue rodando como no v1. A chamada de gestão do B traz só essa pergunta; o `g_acao` não é usado.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    from pathlib import Path
    out = Path(__file__).with_name("perguntas_v2.md")
    out.write_text(gera_md(), encoding="utf-8")
    print(out, len(M), "perguntas de mercado,", len(G), "de gestao")
