# Bateria de testes do WinMaestro no Testador

Onze testes, todos com WINV26, M1, de 13/08/2026 a 30/09/2026, depósito de R$1.000, "Todos os ticks" (ticks gerados) e sem atraso:

| Teste | O que roda | Para quê |
|---|---|---|
| `M_GB`, `M_CM`, `M_DM`, `M_RE`, `M_C1` | WinMaestro com um robô ligado | o robô dentro do Maestro |
| `M_TODOS` | WinMaestro com os 5 ligados | a convivência na mesma conta |
| `A_GB`, `A_CM`, `A_DM`, `A_RE`, `A_C1` | EA avulso de cada robô, inputs padrão | a referência |

O que se espera:
- cada `M_xx` repete o `A_xx` (as diferenças aceitas estão no `../WinMaestro_ROTEIRO_TESTE.md`);
- no `M_TODOS`, cada robô repete o `M_xx` dele, com no máximo 4 ou 5 contratos.

**Não use "ticks reais".** O histórico de ticks reais do WINV26 na Rico descarta 85% dos minutos.

## Como rodar

1. **Feche o MT5 da Rico** fora do pregão e sem posição aberta. Com o terminal aberto, o teste não roda. Fechar o terminal também derruba os robôs Python ligados a ele.
2. Na raiz do repositório:
   ```
   .\.venv\Scripts\python.exe mt5\testes\gera_ini.py
   powershell -ExecutionPolicy Bypass -File mt5\testes\rodar_testes.ps1
   .\.venv\Scripts\python.exe mt5\testes\compara.py
   ```
   - Para rodar só alguns: `rodar_testes.ps1 M_GB A_GB`.
   - Cada teste abre o MT5, testa, salva o relatório e fecha sozinho.
   - No fim, o MT5 é reaberto normalmente.
3. Os relatórios (`.htm`) e o Diário do Testador ficam em `mt5\testes\resultados\`.

## Como ler o `compara.py`

- **Resultado por robô** = fluxo de caixa dos negócios dele (vende − compra) × R$0,20, sem custo. Na conta NETTING, o "Lucro" do relatório é da posição líquida, não de cada robô.
- **"entradas iguais"** = entradas em comum / só no primeiro teste / só no segundo, comparando minuto e lado.
- **Negócios sem dono:** os negócios do corte da conta (sem comentário `MAE|<robô>|`) aparecem contados à parte no `M_TODOS`.

## Resultado de 2026-10-07 (WinMaestro v2.02)

| Robô | Avulso | Maestro, só ele | Maestro, os 5 | Entradas |
|---|---|---|---|---|
| WinGapBarra1 | 19 ops, +340 | 19 ops, +340 | 19 ops, +340 | idênticas |
| WinCincoMedias | 22 ops, +528 | 22 ops, +596 | 22 ops, +596 | idênticas |
| WinDeslocamentoMatinal | 10 ops, +156 | 10 ops, +94 | 10 ops, +94 | idênticas |
| WinRetanguloEma34 | 6 ops, +325 | 6 ops, +325 | 6 ops, +325 | idênticas |
| Win_c1 | 3 ops, +2 | 3 ops, +2 | 3 ops, +2 | idênticas |

Com os 5 robôs ligados, a conta terminou em **+1.357**, que é a soma exata dos robôs. A posição líquida máxima foi de 3 contratos, e não houve nenhum negócio sem dono.

Todas as diferenças entre o avulso e o Maestro vêm de decisões já documentadas:
- **WinCincoMedias:** o Maestro zera às 18:20, e o avulso às 18:24.
- **WinDeslocamentoMatinal:** o teto de risco do Maestro é calculado sobre R$1.000 fixos (decisão B9), enquanto o avulso usa o saldo da conta, que vai crescendo. Por isso o stop do Maestro sai mais curto. Em 16/09, por exemplo, ficou em 500 pts contra 790 pts no avulso.

Dois cuidados ao rodar:
- **O Maestro é lento no Testador:** cerca de 32 minutos por teste, contra 0,6 minuto do avulso.
- **Inputs:** o `gera_ini.py` grava todos os inputs com os padrões do código. Sem isso, o Testador usa o último `.set` salvo. No primeiro teste, o avulso do Retângulo rodou com `MinutoZerar=50`.
