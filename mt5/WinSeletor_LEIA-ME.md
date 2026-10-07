# WinSeletor

EA unico para o mini indice (WIN) que reune os 5 robos atuais. O dono escolhe qual deles opera por um input. A logica e os padroes de cada robo sao os dos EAs avulsos; nada foi mudado nas regras de negociacao.

| # | Robo | Versao | Tempo do robo | Magic | Contratos |
|---|---|---|---|---|---|
| 1 | WinGapBarra1 | 1.01 | M5 | 80080601 | sempre 1 |
| 2 | WinCincoMedias | 2.05 | H2 (Supertrend H4) | 80080501 | `Lote` (1) |
| 3 | WinDeslocamentoMatinal | 1.31 | M1 (D1 para o ATR) | 80080101 | `Lote` (1), com teto de risco de 10% do saldo (ACCOUNT_BALANCE) |
| 4 | WinRetanguloEma34 | 1.07 | M15 ajustado | 20261005 | `Lote` (1) |
| 5 | Win_c1 | 2.07 | H1 (filtro H3) | 80080002 | `Lote` (1) |

Arquivos: `mt5/WinSeletor.mq5` (o EA) e `mt5/WinSeletor/*.mqh` (um modulo por robo, mais `Comum.mqh`).

## Como escolher o robo

Abra os inputs do EA, grupo **Seletor**, e escolha o robo no dropdown **Robo**. So o robo escolhido gera entradas. Ele continua escolhido ate o dono mudar o input. Todos os demais inputs ja vem com a regra adotada de cada robo: abrir e rodar.

Os inputs de cada robo ficam em grupos separados (`WinGapBarra1`, `WinCincoMedias`, `WinDeslocamentoMatinal`, `WinRetanguloEma34`, `Win_c1`), com a mesma ordem, o mesmo texto e os mesmos padroes do EA avulso. O unico acrescimo e um prefixo no nome tecnico (`GB_`, `CM_`, `DM_`, `RE_`, `C1_`), porque varios robos usam o mesmo nome (`MagicNumber`, `Lote`, `NaoOperarGapATR`) e o MT5 nao aceita nome repetido. Consequencia: arquivos `.set` salvos de um EA avulso nao carregam aqui; os padroes ja sao os adotados. Os inputs dos robos nao selecionados sao ignorados.

Rode no contrato real (por exemplo WINV26). No Testador, use WIN$N como os EAs avulsos.

## Regra de troca

A troca de robo so acontece sem posicao.

- Ao ligar ou reiniciar o EA (inclusive ao mudar o input **Robo**), o EA procura posicao aberta ou ordem pendente de cada um dos 5 robos, pelo magic de cada um, no simbolo do grafico.
- Se outro robo tem posicao ou ordem, a troca e **recusada**. O robo antigo continua rodando **somente para gerir e fechar o que e dele**: saidas, stop, zeragem de fim de pregao, break-even, validade das ordens. Ele nao abre entrada nova. O robo recem escolhido nao abre nada.
- O EA escreve um aviso (Alert e Diario) uma unica vez: "troca para X recusada ... pendente ate Y zerar".
- Quando o robo antigo fica sem posicao e sem ordem, o robo escolhido assume sozinho, no proximo tick, e o Diario registra "troca concluida".
- Nenhuma posicao e fechada por causa de uma troca.
- O robo ativo fica gravado numa GlobalVariable do terminal, chave `WinSeletor.<simbolo>.<MagicSeletor>`. Assim, depois de um reinicio, o EA sabe quem e o dono da posicao. (`MagicSeletor`, padrao 80080900, so serve para essa chave. No Testador a GlobalVariable nao e usada.)
- Se mudar o input de volta para o robo que ainda tem a posicao, o EA volta ao normal.

Limite conhecido, igual ao dos EAs avulsos: o estado em memoria de um robo nao sobrevive a um reinicio do EA. Duas consequencias:

- Uma ordem-alvo do WinRetanguloEma34 deixada no livro depois de um reinicio com posicao aberta nao e mais rastreada pelo robo. O Seletor continua enxergando essa ordem (pelo magic) e mantem a troca pendente. Apague a ordem a mao no MT5 se isso acontecer.
- O WinDeslocamentoMatinal depois de um reinicio com posicao aberta perde o stop controlado pelo EA (fica so o stop de reserva no servidor, que ele ja grava na conta real). Nesse caso o Seletor nao deixa o robo tratar o reinicio como "pregao novo" (o que zeraria a posicao).

## Tempo grafico recomendado

Qualquer um. **M1 serve.** Cada modulo le o proprio tempo (M5, H2 com Supertrend H4, M1/D1, M15, H1 com filtro H3) por `CopyRates`/`iMA`/`iTime` com o tempo explicito, nunca pelo periodo do grafico. O grafico e so visual (o WinRetanguloEma34 desenha o retangulo nele).

## Como conferir a equivalencia no Testador

Para cada robo X:

1. Rode o **WinSeletor** com `Robo` = X e todos os demais inputs no padrao.
2. Rode o **EA avulso X** (`WinGapBarra1`, `WinCincoMedias`, `WinDeslocamentoMatinal`, `WinRetanguloEma34` ou `Win_c1`) com os padroes.
3. Use as mesmas configuracoes nos dois: simbolo WIN$N, mesmo periodo de 2026, modelagem "todos os ticks com base em ticks reais", mesmo deposito, mesma alavancagem.
4. Compare a lista de negocios: data/hora, sentido, preco de entrada, preco de saida, lucro e numero de operacoes. Devem ser identicos.

Pontos de atencao: o periodo do grafico do Testador pode ser diferente entre os dois testes (nao deveria mudar nada, esse e justamente o objetivo do Seletor); se algo divergir, anote o robo, o dia e a primeira operacao diferente.

## O que muda em relacao aos EAs avulsos (so adaptacao de seletor)

- Cada robo vive num namespace proprio (`WGB1`, `WCM`, `WDM`, `WRE`, `WC1`) para nao colidir nomes.
- Avisos "grafico em X, mas o EA calcula em Y" foram removidos.
- Modo "so gerir": com a troca pendente, cada robo nao arma entrada nova (um `if(SoGerir) return;` antes de enviar o sinal); o resto da logica continua rodando.
- WinRetanguloEma34: ao encerrar, cancela a entrada ainda nao preenchida (o estado dela nao sobrevive a um reinicio e a ordem orfa encheria sem stop nem alvo). A deteccao de barra nova deixou de ser `static` para zerar a cada religacao.
- WinDeslocamentoMatinal: reinicio com posicao dele aberta no mesmo dia nao zera a posicao (ver acima).
- Win_c1: `OnTester` e o diagnostico de pico de equidade do Testador nao foram portados (nao negociam).
