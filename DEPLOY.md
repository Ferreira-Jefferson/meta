# Operação ao vivo — deploy num servidor Windows

Este documento cobre só a **operação autônoma** (`live/` + `scripts/run_live.py`).
Para rodar o dashboard de estudo/backtest localmente, veja o `README.md`.

## Por que Windows, não Linux/Docker

Se você for usar **MetaTrader 5** como corretora (`--mode mt5`), o pacote
`MetaTrader5` do Python só fala com um terminal MT5 **já aberto e logado na
mesma máquina**, via IPC do Windows — não existe suporte oficial em
Linux/Docker. Por isso o "servidor" aqui é uma **VPS Windows** (Contabo, Vultr,
Azure/AWS com Windows Server, etc.), não um container Linux.

O único modo de execução que existe é MT5 — o robô decide e executa sozinho,
sem confirmação humana em nenhum momento — então este guia assume Windows do
início ao fim.

## 1. Preparar a VPS

1. Suba uma VPS Windows (Windows Server 2019+ ou Windows 10/11).
2. RDP nela, instale o **MetaTrader 5** da sua corretora, faça login na conta
   e deixe o terminal aberto — o `MT5Broker` fala com ele, não com a nuvem da
   corretora diretamente.
3. Instale o **Python 3.11+** (mesma versão do seu ambiente de desenvolvimento).
4. Copie o repositório inteiro para a VPS (git, zip, o que for mais simples).
5. Rode `.\dev.bat` uma vez **manualmente** — ele cria o `.venv`, instala
   dependências, inicializa o banco e baixa o histórico. Pare com `Ctrl+C`
   depois que o dashboard subir (não precisa dele rodando 24/7 na VPS, só
   validando que o setup funcionou).

## 2. Configurar segredos como variável de ambiente do SISTEMA

**Nunca** passe token/senha como argumento de linha de comando — fica visível
no histórico do shell e na lista de processos. Configure como variável de
ambiente do Windows (Painel de Controle → Sistema → Variáveis de Ambiente, ou
`setx` no PowerShell **como administrador**, que persiste entre reboots):

```powershell
setx TELEGRAM_BOT_TOKEN "123456:ABC-seu-token"
setx TELEGRAM_CHAT_ID "987654321"

# opcional, além ou no lugar do Telegram:
setx SMTP_HOST "smtp.seuprovedor.com"
setx SMTP_PORT "587"
setx SMTP_USER "seu-usuario"
setx SMTP_PASSWORD "sua-senha-de-app"
setx SMTP_TO "voce@example.com"
```

`setx` só afeta **novos** processos — feche e reabra o terminal (ou o serviço,
na seção 3) depois de configurar.

## 3. Rodar como serviço persistente (sobrevive a reboot e a fechar o RDP)

`python scripts/run_live.py loop` já faz o trabalho — ele só age em dia e
horário de pregão (o resto do tempo fica ocioso, verificando o relógio). O que
falta é mantê-lo rodando sem depender de uma janela de terminal aberta.

**Recomendado: [NSSM](https://nssm.cc/)** (Non-Sucking Service Manager) —
grátis, uma ferramenta, sem instalação:

```powershell
# baixe nssm.exe (site oficial) e rode como administrador:
nssm install MetaLiveTrading "C:\caminho\para\meta\.venv\Scripts\python.exe" `
    "C:\caminho\para\meta\scripts\run_live.py" `
    --mode mt5 --capital SEU_CAPITAL --daily-loss-limit 0.05 --monthly-loss-limit 0.15 loop --seconds 60

nssm set MetaLiveTrading AppDirectory "C:\caminho\para\meta"
nssm set MetaLiveTrading AppExit Default Restart   # reinicia sozinho se cair
nssm set MetaLiveTrading Start SERVICE_AUTO_START  # sobe com o Windows

nssm start MetaLiveTrading
```

Log do serviço: redirecione stdout/stderr com `nssm set MetaLiveTrading
AppStdout ...` / `AppStderr ...`, ou confie no diário (`live_events`, visível
em `/operacao` e `/operacao/historico`) — o loop já registra ali toda decisão,
execução e erro.

**Alternativa mais simples, sem instalar nada:** Agendador de Tarefas do
Windows, um gatilho "ao iniciar o sistema", ação = o mesmo comando acima, "Executar
estando o usuário conectado ou não", com "Reiniciar a cada X minutos" em caso
de falha, nas configurações da tarefa.

## 4. Antes de operar dinheiro real: valide o encanamento sem capital em risco

**Não pule esta etapa.** O deploy inteiro (serviço, agendamento, variáveis de
ambiente, conexão MT5) é uma superfície nova que nunca rodou sem supervisão.
Como não existe mais um modo de simulação em produção, valide o serviço
(sobrevive a reboot? os alertas chegam? o disjuntor dispara quando deveria?)
com uma conta DEMO da sua corretora no MT5 antes de logar na conta real —
`MT5Broker` fala com qualquer terminal já aberto e logado, real ou demo,
sem diferença de código.

Complementar: `python scripts/run_live_sim.py --years 5` reproduz anos de
histórico real através do MESMO `LiveRuntime`, em minutos, e compara com o
backtest oficial da mesma janela — é a forma rápida de verificar que a
maquinaria (ordem entra, stop dispara) continua fiel depois de qualquer
mudança de código, sem esperar meses de pregão real.

## 5. Antes de trocar para MT5 de verdade

`live/broker_mt5.py` **não foi validado contra um terminal MT5 real** — não
havia ambiente disponível para isso durante o desenvolvimento. Antes de
confiar nele operando sem supervisão:

1. Abra o MT5, confira no Market Watch o **nome exato** dos símbolos das ações
   da sua watchlist (pode não ser igual ao ticker + `.SA`) — configure
   `--mt5-symbol-map` se for diferente.
2. Confira `volume_step`/`volume_min` do símbolo (clique direito → Especificação)
   para saber a relação ação↔lote da SUA corretora — configure
   `--mt5-shares-per-lot`.
3. Rode `scripts/run_live.py execute` (ou `step`) manualmente, em horário de
   pregão, com o **menor capital possível**, observando o terminal MT5 ao vivo
   — confirme que a ordem realmente chegou, no símbolo certo, na quantidade
   certa.
4. Só depois disso deixe o serviço (`loop`) rodando sem supervisão.

## 6. Circuit breaker e alertas — o que esperar

Com `--daily-loss-limit`/`--monthly-loss-limit` configurados: uma queda de
patrimônio acima do limite **veta abertura de posição nova** (nunca força
venda, nunca mexe em stop, nunca trava saque). A trava diária volta sozinha no
dia seguinte; a mensal exige `python scripts/run_live.py unfreeze` depois de
você revisar o que aconteceu — isso é proposital (ver `live/riskguard.py`).

Com Telegram/e-mail configurado: toda decisão relevante, execução, stop
disparado e erro do loop chegam pelo canal, filtrados por `--notify-min-level`
(default `warn` — não manda todo evento `info` do dia a dia). O diário
(`live_events`, sempre visível no dashboard) grava tudo, sem filtro,
independente do que sai pelo canal externo.
