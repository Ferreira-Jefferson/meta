# WinMaestro — roteiro de teste

Ordem: 1 → 2 → 3. Cada passo só depois do anterior OK. Depois de cada passo, avise: o resultado é lido direto da pasta do MT5 (Diário/logs do Testador), não precisa copiar nada.

## 1. Testes unitários (EA de teste, ~1 min)

1. No MT5, abra um **segundo gráfico do WINV26** (qualquer tempo). Nenhum outro robô nele.
2. Arraste **WinMaestro_Teste** para esse gráfico → OK (permitir negociação algorítmica).
3. Ele roda os testes na hora e escreve no Diário (aba Experts) `PASSOU`/`FALHOU` por teste e um total no fim.
4. Pode remover o EA do gráfico depois.

Ele usa uma corretora simulada: **não envia nenhuma ordem real**. Não coloque no mesmo gráfico do maestro (substituiria o maestro).

Esperado: **137 verificações, todas `PASSOU`** (v2.02). Qualquer `FALHOU` → corrijo antes do passo 2.

## 2. Equivalência no Testador (cada robô sozinho)

Configuração igual em todos os testes:

| Campo | Valor |
|---|---|
| Símbolo | WINV26 |
| Período | 13/08/2026 a 30/09/2026 |
| Modelagem | Todos os ticks com base em ticks reais |
| Depósito | 1000 |
| Tempo gráfico | M1 |

Para cada robô, rode **dois** testes no mesmo período:

| # | EA | Inputs |
|---|---|---|
| a | WinMaestro | só `Ativo_GapBarra1 = true` (os outros 4 false) |
| b | WinMaestro | só `Ativo_CincoMedias = true` |
| c | WinMaestro | só `Ativo_DeslocamentoMatinal = true` |
| d | WinMaestro | só `Ativo_RetanguloEma34 = true` |
| e | WinMaestro | só `Ativo_Win_c1 = true` |
| f | WinMaestro | os 5 `true` |

E os avulsos correspondentes (WinGapBarra1, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, Win_c1) com os padrões, mesmo período — se ainda não estiverem no histórico do Testador.

Referência já medida para os avulsos nesse período (sem custo): Win_c1 3 ops +5 · WinCincoMedias 23 ops +500 · WinRetanguloEma34 5 ops +221 · WinDeslocamentoMatinal 11 ops +55.

Diferenças **aceitas** (decisões já tomadas): WinCincoMedias zera às 18:20 (era 18:24) e nasce com stop de reserva de 4.945 pts; stop do WinDeslocamentoMatinal fica no servidor. Qualquer outra diferença de entrada/saída eu investigo.

Esperado no (f): resultado de cada robô igual ao do teste sozinho dele (b–e); posição máxima até 4–5 contratos.

## 3. Conta demo (pregão real)

Só depois do 2. Roteiro dos cenários de falha (fechar o MT5 com posição, internet, zerar na mão, etc.) e as perguntas à corretora vêm depois do resultado do 2.
