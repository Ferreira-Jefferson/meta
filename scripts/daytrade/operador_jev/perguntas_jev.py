"""Perguntas de PERGUNTAS_DE_OPERACAO.md convertidas para o formato do endpoint /api/alpha/decisions (Jev).

Tipos: noul = P(sim) em [0,1]; choice = probabilidades por categoria; score = valor esperado do nivel (0..n-1).
Ids estaveis: b<bloco>_q<numero no arquivo> (bloco 0 = "Antes de aceitar qualquer conclusao"), d<n>[_c|_v] = perguntas
de decisao D1..D13 (_c = para uma COMPRA, _v = para uma VENDA), e/s/a = execucao/stop/alvo, g_* = gestao com posicao.
As perguntas sao abertas: "nao" e uma resposta tao boa quanto "sim"; nada aqui diz qual resposta libera qual acao.
"""
from __future__ import annotations

SUF = " Responda só com o que as velas fechadas do estado mostram."

# (id, tipo, ref no arquivo, texto, criteria)  -- criteria: dict (choice) | list (score) | None (noul)
_C, _V = "COMPRA", "VENDA"


def _par(base_id, ref, texto):
    """Mesma pergunta para uma compra e para uma venda; {X} = COMPRA/VENDA."""
    return [(f"{base_id}_c", "noul", ref, texto.replace("{X}", _C), None),
            (f"{base_id}_v", "noul", ref, texto.replace("{X}", _V), None)]


MERCADO: list[tuple] = [
    # ---- bloco 0: em que condicoes a leitura vale ----
    ("b0_q1", "noul", "0.1", "O M15 e o H1 contam a mesma história neste momento (não há divergência entre tempos gráficos)?", None),
    ("b0_q2", "choice", "0.2", "A volatilidade de agora (amplitude das velas M15 e do dia) está acima, normal ou abaixo do histórico recente?",
     {"alta": "acima do normal", "normal": "normal", "baixa": "abaixo do normal"}),
    ("b0_q9", "choice", "0.9", "O contexto atual favorece mais compra, mais venda, ou os dois lados igualmente?",
     {"compra": "favorece compra", "venda": "favorece venda", "igual": "os dois lados igualmente"}),
    ("b0_q14", "noul", "0.14", "O movimento recente pode ser só um efeito de horário ou de volume, e não de direção?", None),
    # ---- bloco 1: antes do pregao ----
    ("b1_q2", "noul", "2", "O gap de abertura de hoje foi grande (acima de 1 ATR diário)?", None),
    ("b1_q5", "choice", "5", "Que tipo de dia os sinais da abertura até agora sugerem?",
     {"tendencia_alta": "tendência de alta", "tendencia_baixa": "tendência de baixa", "lateral": "lateral",
      "reversao_do_gap": "reversão do gap", "indefinido": "indefinido"}),
    # ---- bloco 2: contexto ----
    ("b2_q13", "choice", "13", "Em que regime o mercado está agora?",
     {"tendencia": "tendência", "lateral": "lateral", "alta_volatilidade": "alta volatilidade", "baixa_liquidez": "baixa liquidez",
      "indefinido": "indefinido"}),
    ("b2_q14", "noul", "14", "Os tempos gráficos maiores (H1 e diário) concordam com a direção das últimas velas M15?", None),
    ("b2_q15", "choice", "15", "Onde o preço está dentro da faixa feita hoje (entre a mínima e a máxima do dia)?",
     {"perto_da_maxima": "perto da máxima do dia", "meio": "no meio da faixa", "perto_da_minima": "perto da mínima do dia"}),
    ("b2_q16", "score", "16", "Quanto do ATR diário o dia já andou (máxima menos mínima desde a abertura)?",
     ["0 = menos de 0,25 ATR diário", "1 = de 0,25 a 0,5", "2 = de 0,5 a 0,75", "3 = de 0,75 a 1", "4 = mais de 1 ATR diário"]),
    ("b2_q17", "choice", "17", "A estrutura de topos e fundos do M15 está ficando mais forte para qual lado?",
     {"alta": "topos e fundos ascendentes", "baixa": "topos e fundos descendentes", "misto": "misto/indefinido"}),
    ("b2_q19", "noul", "19", "Há algo fora do normal hoje (volume, amplitude, velocidade, buracos no gráfico) que torne o histórico menos parecido com o presente?", None),
    ("b2_q21", "noul", "21", "O diário e o M15 contam histórias opostas?", None),
    # ---- bloco 3: medias, indicadores, osciladores ----
    ("b3_q24", "noul", "24", "O preço está esticado em relação à média das últimas 20 velas M15?", None),
    ("b3_q25", "choice", "25", "Algum oscilador (tipo estocástico/RSI de 14 velas M15) estaria em extremo?",
     {"sobrecomprado": "extremo de alta", "sobrevendido": "extremo de baixa", "neutro": "neutro"}),
    ("b3_q27", "noul", "27", "O volume recente confirma o movimento (o movimento tem participação)?", None),
    ("b3_q28", "noul", "28", "Existe divergência entre preço e volume (ou entre preço e um oscilador) nas últimas velas?", None),
    ("b3_q30", "choice", "30", "Olhando só o preço, sem indicador nenhum, o que ele mostra agora?",
     {"alta": "alta", "baixa": "baixa", "lateral": "lateral"}),
    # ---- bloco 4: estrutura, figuras, padroes ----
    ("b4_q31", "choice", "31", "Existe uma estrutura de preço recente (figura, canal, retângulo, falha de rompimento) que mude a decisão? Ela favorece qual lado?",
     {"compra": "favorece compra", "venda": "favorece venda", "neutra": "não há estrutura relevante ou é neutra"}),
    ("b4_q32", "noul", "32", "O preço está perto de um nível onde já reagiu várias vezes (hoje ou nos dias anteriores)?", None),
    ("b4_q35", "choice", "35", "A última perna do preço mostra força, cansaço ou é igual às anteriores?",
     {"forca": "força", "cansaco": "cansaço", "igual": "igual às anteriores"}),
    ("b4_q37", "noul", "37", "Há algo no gráfico que contradiz a continuação do movimento da última perna?", None),
    ("b4_q38", "noul", "38", "Houve uma falha de rompimento recente (preço rompeu um nível e voltou)?", None),
    # ---- bloco 5: horario e calendario ----
    ("b5_q39", "choice", "39", "Em que fase do pregão estamos?",
     {"abertura": "até 10:00", "manha": "10:00 a 12:00", "almoco": "12:00 a 14:00", "tarde": "14:00 a 16:00", "fim": "depois das 16:00"}),
    ("b5_q42", "noul", "42", "O dia tem característica de calendário (vencimento, véspera, início/fim de mês) que costume mudar o comportamento?", None),
    ("b5_q43", "noul", "43", "A primeira barra do dia ou o leilão de abertura estão contaminando a leitura (estamos perto da abertura)?", None),
    # ---- bloco 6: o sinal e a decisao de entrar ----
    ("b6_q52", "noul", "52", "Existe algum sinal de aviso (horário, volume, estrutura) que mande não entrar ou entrar menor?", None),
    ("b6_q53", "choice", "53", "Se outra pessoa mostrasse este gráfico sem dizer o lado, qual lado você escolheria?",
     {"compra": "compra", "venda": "venda", "nenhum": "nenhum dos dois"}),
    # ---- perguntas de decisao D1..D13 em forma universal (uma por lado) ----
    *_par("d1", "D1", "A estrutura de topos e fundos já confirmou uma virada a favor de uma {X}?"),
    *_par("d2", "D2", "A tendência do tempo gráfico maior (H1), com a vela fechada, está contra uma {X} ou indefinida?"),
    *_par("d3", "D3", "O preço está do lado contrário à abertura do dia para uma {X}?"),
    *_par("d4", "D4", "As médias rápida e lenta do tempo da operação (M15) estão contra uma {X}, ou empatadas?"),
    *_par("d5", "D5", "A média longa do M15 está inclinada contra uma {X}, ou plana?"),
    *_par("d6", "D6", "O preço já está esticado a favor de uma {X} (oscilador perto do extremo na direção da operação)?"),
    *_par("d11", "D11", "O gap de abertura está a favor de uma {X}?"),
    ("d7", "noul", "D7", "O tempo gráfico ainda maior (H4) está sem tendência?", None),
    ("d9", "noul", "D9", "Resta pregão suficiente para uma operação se desenvolver?", None),
    ("d10", "noul", "D10", "O horário atual é parte de uma tese (uma janela típica do dia, como a abertura)?", None),
    ("d11b", "noul", "D11", "O gap de abertura já foi preenchido?", None),
    ("d12", "noul", "D12", "Há algum padrão próprio (retângulo, faixa, rompimento) confirmado e com tamanho típico em ATR?", None),
    ("d13", "choice", "D13", "A tendência do M15 está a favor de qual lado?",
     {"compra": "alta", "venda": "baixa", "nenhum": "sem tendência"}),
    # ---- execucao / stop / alvo (S2, A1) ----
    ("s2", "noul", "S2", "Existe uma referência (média) entre o ponto em que a tese estaria errada e a entrada, longe o bastante da entrada?", None),
    ("a1", "noul", "A1", "O ganho provável de uma operação aqui vem de deixar correr até o fim do dia (e não de um alvo fixo)?", None),
    # ---- a decisao em si (so as 4 perguntas finais; o motor converte) ----
    ("acao", "choice", "decisao", "Qual a melhor ação agora, com ordem limitada no último fechamento (válida por 3 velas M15)?",
     {"comprar": "comprar com ordem limitada", "vender": "vender com ordem limitada", "fora": "ficar de fora"}),
    ("stop", "choice", "S1", "Se fosse operar, onde fica o ponto que, se atingido, prova que a tese estava errada?",
     {"0.5atr": "0,5 ATR M15 da entrada", "1atr": "1 ATR M15 da entrada", "1.5atr": "1,5 ATR M15 da entrada",
      "pivo": "no último pivô (fundo para compra, topo para venda) ou extremo recente"}),
    ("alvo", "choice", "A1", "Se fosse operar, qual o alvo?",
     {"sem_alvo": "sem alvo: deixar correr com stop seguindo", "1atr": "alvo de 1 ATR M15", "2atr": "alvo de 2 ATR M15", "3atr": "alvo de 3 ATR M15"}),
    ("mao", "choice", "75", "Se fosse operar, quantos contratos (1 ou 2)?",
     {"1": "1 contrato", "2": "2 contratos"}),
]

# chamada extra, so com posicao aberta (o estado inclui a linha POSICAO)
GESTAO: list[tuple] = [
    ("b11_q81", "noul", "81", "O cenário que justificou a entrada ainda existe?", None),
    ("b11_q82", "choice", "82", "Se você estivesse fora agora, entraria?",
     {"mesma_direcao": "entraria na mesma direção da posição", "direcao_oposta": "entraria na direção oposta", "nao_entraria": "não entraria"}),
    ("b11_q83", "noul", "83", "A operação está se comportando como as boas do histórico?", None),
    ("g_acao", "choice", "S3", "O que fazer com a posição agora?",
     {"manter": "manter posição e stop como estão",
      "stop_pivo": "mover o stop para o último pivô a favor (compra: sobe; venda: desce)",
      "zerar": "zerar a posição"}),
]

TIPOS = {q[0]: q[1] for q in MERCADO + GESTAO}
REF = {q[0]: q[2] for q in MERCADO + GESTAO}
TEXTO = {q[0]: q[3] for q in MERCADO + GESTAO}


def monta_questions(lista) -> dict:
    out = {}
    for qid, tipo, _ref, texto, crit in lista:
        q = {"type": tipo, "instructions": texto + SUF}
        if tipo == "choice":
            q["criteria"] = dict(crit)
        elif tipo == "score":
            q["criteria"] = list(crit)
        out[qid] = q
    return out


QUESTOES_MERCADO = monta_questions(MERCADO)
QUESTOES_GESTAO = monta_questions(GESTAO)
