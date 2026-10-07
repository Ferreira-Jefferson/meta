# LarryWilliams.mq5 — como usar

Contrato: `scripts/larry_williams/ESPECIFICACAO.md`. Decisões: `scripts/larry_williams/DECISOES.md` e `DECISOES_EA.md`.

## Instalar
1. Copie `mt5/LarryWilliams.mq5` para `<pasta de dados do MT5>\MQL5\Experts\` (Rico: `C:\Users\Jeffe\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B\MQL5\Experts\`).
2. Abra no MetaEditor e compile (F7), ou: `MetaEditor64.exe /compile:LarryWilliams.mq5 /log:LarryWilliams_compile.log`.

## Testador do MT5
- Modelo: **Todos os ticks com base em ticks reais**. Símbolo: `WIN@D`/`WDO@D` ou o contrato vigente; ações/ETFs (ex. BITH11) direto.
- Período D1 do gráfico irrelevante (o EA lê D1 sozinho). Use IS/OOS combinados com o relatório do motor Python.
- Conta **NETTING** (necessário para TRES_BARRAS). Ajuste `HoraAbertura/HoraFim` ao horário do SERVIDOR (futuros 9:00–17:50; ações costumam abrir 10:00).
- `Lote` e tick/volume vêm do símbolo; sem portão de capital/margem.

## Ligar setups
Um `bool` por setup (`UsarVB`, `UsarOops`, `UsarSmash`, `UsarHiddenSmash`, `UsarOutside`, `UsarGSV`, `UsarWR`, `UsarUO`, `UsarTDM`, `UsarTDW`, `UsarTresBarras`). Com vários ligados vale a prioridade VB > OOPS > SMASH > HSMASH > OUTSIDE > GSV > WR > UO > TDM > TDW (para comparar com o Python, rode um setup por vez). `PermiteCompra`/`PermiteVenda` ligam os lados; `ModoSaida` escolhe a saída (BAILOUT, FECHAMENTO, TEMPO_N, REVERSAO, ABERTURA_SEGUINTE, ALVO_RR, INDICADOR). Defaults = livro/especificação; os recomendados entram depois (mapa em `DECISOES_EA.md`).

## Comparar com o Python
O EA grava `LW_trades_<simbolo>_<setup>.csv` (`data;lado;entrada;saida;motivo;pnl_pts`) em `Common\Files` (`LogComum=true`, padrão; com `false` vai para `MQL5\Files` do agente do Testador). Apague o CSV antes de cada teste (o EA acrescenta ao fim). Compare com o CSV de referência do motor: junte por `data`+`lado` e confira diferença de `entrada`/`saida`/`pnl_pts`. Diferenças esperadas: o EA usa ticks reais e slippage real; o motor usa convenções de barra (pior caso, M1 nos futuros).
