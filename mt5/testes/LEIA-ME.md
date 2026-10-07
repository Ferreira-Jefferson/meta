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
