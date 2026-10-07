# Briefing comum — refazer os estudos do WIN contaminados pelos leilões

Pedido do dono (2026-10-06): refazer os CSVs com os dados corretos e refazer os estudos afetados.
Leia antes: `scripts/daytrade/win_fases_correlacao_2026_10_06/auditoria_leiloes/AUDITORIA.md` (o seu estudo está lá, com os números a recalcular).

## O problema

Nas bases M1 do WIN:
- A **última barra do dia** (18:24, ou 17:54 quando o pregão acabava 17:55) contém o **call de fechamento**: o close é o preço do call e o volume inclui o do call.
- A **1ª barra** (ou a 2ª, em 2022–25) contém o **leilão de abertura**.
- Nenhum dos dois leilões é negociável como o contínuo.

O motor intradiário (`src/backtest/intraday/machine.py`) usa o perfil WIN@, que tem o corte de zeragem em UTC (21:20). Numa base em BRT esse corte nunca chega, e a zeragem cai no fallback "última barra do dia", que é o call.

## Ferramenta única (use, não reimplemente)

`src/market_data_intraday/win_sem_leiloes.py`:
- `carrega_win_m1_sem_leiloes(base, inicio, fim, tf, ...)` devolve `.barras` e `.dias`.
  - Nas `.barras`, a última barra do contínuo tem close = último negócio contínuo, e o volume sai sem leilão e sem call. A reamostragem vem depois do ajuste.
  - Existe `ultima_continua` por barra e `dias.ultima_barra_continua` por dia: **zere nela**, nunca em `c[-1]`.
  - Antes de abr/2026 (sem ticks) os ajustes são aproximados e vêm marcados com `proxy=True`.
- `filtra_ticks_continuo(t, p, v)` tira dos `.npz` os negócios do leilão de abertura e de ≥ fim do pregão.
- Grade oficial por data: `data/b3_grade_horaria_win.csv`. O pregão acaba 18:25, ou 17:55 nos períodos de horário de verão dos EUA antes de 2024-03-11.

## Regras

1. **NÃO altere** `src/backtest/intraday/machine.py` nem `profiles.py`. O motor é o mesmo da produção, e a correção dele é decisão pendente do dono.
   - Nos estudos que rodam no motor, corrija **no script**: passe um `session_end_time` coerente com o fuso do dado (base BRT → 18:20; base `WIN_A_` em UTC → 21:20) ou alimente o motor com as barras do carregador.
   - Confirme medindo que a zeragem **não cai mais** na barra do call: conte em quantos trades a saída foi na última barra do dia, antes e depois.
2. **NÃO sobrescreva** scripts nem resultados antigos. Crie versões novas com sufixo `_semleilao` (ou uma pasta `refeito_2026_10_06/` ao lado) e mantenha o antigo para comparação.
3. Para cada número que a auditoria listou: tabela **antes × depois × diferença**, com n de trades e a % de saídas no call antes e depois. Use a tabela padrão (`backtest/intraday/report.py`) quando o estudo for de robô de day trade.
4. Diga explicitamente se o **veredito** do estudo muda ou não. Não dê veredito novo de "bom/vale a pena": números e se a conclusão anterior se mantém.
5. Testes em paralelo (`.venv\Scripts\python.exe -m pytest`): se mexer em código de `src/`, rode a suíte inteira e reporte o resultado real.
6. Sweeps: `ProcessPoolExecutor` com submit/as_completed, um print por unidade com `flush=True`, e cada worker carregando só o que precisa. A RAM é limitada (31 GB, outra sessão pode estar rodando): no máximo ~10 GB no total.
7. Entregue no fim: o que foi refeito, onde estão os scripts e resultados novos, a tabela antes/depois e o que fica pendente.
