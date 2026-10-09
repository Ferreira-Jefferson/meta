# Base de decisões do WIN — análise de UM pregão

## Objetivo (do dono)

Você analisa **um pregão** e descobre:

- **5 maneiras diferentes de ganhar dinheiro nele** (o que FAZER);
- **5 maneiras de operar nele que dariam prejuízo** (o que NÃO fazer).

Cada maneira vira **código**: uma regra de decisão sim/não, que só usa o que existia até aquele momento. O que se busca é o lucro deste dia, de forma segura, lógica e replicável no sistema, com o caixa real (R$2.000, 1 a 2 contratos).

Você pode olhar o dia inteiro para descobrir as maneiras: é retrospectiva. A **regra**, porém, só pode usar o passado do instante da decisão. Para isso pode usar à vontade o mês, as semanas e os dias anteriores. Analise ponto a ponto: em cada vela, olhando para trás, qual decisão eu deveria ter tomado?

## Ferramentas (leia `base.py` inteiro antes de começar)

- `base.contextos(dia)` gera `(t, ctx)` para cada vela M15 fechada do dia. O `ctx` traz:
  - `m1` e `m15` até t, com ~40 pregões de histórico;
  - `diario`, só com os pregões anteriores;
  - `hoje`, as velas M15 de hoje até t;
  - `atr15` e `atrd`;
  - `posicao` e `ops_hoje`.
- `base.simula_dia(dia, regra, gerir=None, max_ops=None)` executa a regra com as regras fechadas de execução:
  - entrada limitada (enche se o preço passar 10 pts além, validade 45 min);
  - stop a mercado;
  - alvo limitado;
  - zera no fim do pregão;
  - custo de 10 pts por contrato.
- `base.resumo(trades)` devolve operações, R$ e a lista de trades.
- Python: `C:\Users\Jeffe\Documents\study\meta\.venv\Scripts\python.exe`. Rode a partir desta pasta.

## Regras das regras

1. **Função pura** `def regra(ctx) -> dict | None`, devolvendo `{"lado", "stop", "alvo" (ou None), "preco" (opcional), "contratos"}`. Se quiser, inclua também `def gerir(ctx, pos) -> novo_stop | None`, em que o stop só anda a favor.
2. **Universal:** sem data, sem preço absoluto, sem "se for o dia X".
   - Tudo relativo: ATR, abertura, máxima e mínima de ontem, médias, faixas, volume relativo, horário.
   - Horário pode, por exemplo "depois das 10:00".
3. **As 5 maneiras de ganhar precisam ser DIFERENTES na natureza**, não a mesma regra com outro parâmetro. Exemplos de naturezas: seguir o rompimento, recuo a favor da tendência, reversão em falha, rompimento da faixa da 1ª hora, gap, nível de ontem. Cada uma tem de dar **R$ > 0 no dia**, conferido com `simula_dia`.
4. **As 5 maneiras de perder** também são regras em código. Cada uma descreve um comportamento que parece razoável mas perdeu neste dia, por exemplo "comprar cada queda de 1 ATR", "vender a máxima nova" ou "entrar no rompimento sem volume". Cada uma tem de dar **R$ < 0 no dia**, conferido com `simula_dia`.
   - No docstring, escreva a **condição de mercado** que faz dela uma armadilha, para que depois possa virar um veto: "não faça X quando Y".
5. **Risco:** o stop de cada regra arrisca no máximo 6% do caixa (R$120, ou seja, 600 pts com 1 contrato). No máximo 2 contratos.
6. **Diga honestamente o quanto cada regra é geral:**
   - "provavelmente geral" se ela tem fundamento que vale em muitos dias;
   - "ajustada ao dia" se só funciona porque você viu o dia.
   - Não force: 5 maneiras de ganhar com "ajustada ao dia" valem menos que 3 gerais e 2 ajustadas, honestamente marcadas.

## Lições medidas no projeto (respeite)

- O WIN M15 é mais de **continuação** que de reversão: RSI ≤ 30 continua caindo.
- A maioria dos dias é de **rotação**: a eficiência direcional fica abaixo de 0,15 em ~80% dos pregões sorteados.
- A estratégia que funciona (a escada) **ganha deixando correr**: os 10% melhores trades fazem 174% do lucro.
- Depois das 15h os sinais pioram.
- Padrão de vela isolada, figura e Fibonacci não separaram nada.

## Entrega (só estes arquivos; não altere nenhum outro)

- **`regras/r_<AAAA_MM_DD>.py`**, com:
  - `FAZER = [(nome, regra, gerir_ou_None), ...]`, com 5 itens;
  - `NAO_FAZER = [(nome, regra, gerir_ou_None), ...]`, com 5 itens;
  - cada função com um docstring dizendo: a lógica, a condição de mercado, se é geral ou ajustada, e o resultado no dia.

  Ao rodar `python -m regras.r_<AAAA_MM_DD>` a partir desta pasta, o arquivo imprime o resultado de cada regra no dia.
- **`analises/<AAAA_MM_DD>.md`**, com:
  - o retrato do dia: tipo, tamanho em ATR do dia, gap, contexto da semana e do mês;
  - a leitura ponto a ponto dos momentos decisivos;
  - a tabela das 10 regras: nome, fazer/não fazer, natureza, R$, ops, geral/ajustada, condição.
