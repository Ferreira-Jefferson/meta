# WinMaestro v2.1: segunda revisão do núcleo

Escopo: `WinMaestro_ARQUITETURA_v2.md` v2.1 ("desenho"), contra a revisão anterior (RV) e a especificação 1.0 ("spec"). Só CRÍTICO e ALTO.

**Veredito: ainda não está pronto para implementar.** São 6 ajustes, todos de definição: um CRÍTICO, cinco ALTOS. Nenhum muda a arquitetura.

## 1. Achados CRÍTICO e ALTOS da RV

| # | Estado | Conferido em |
|---|---|---|
| C-1 ticket 0 | **FECHADO** | §2.1 passo 1: casamento por `request_id`, `vivas[]` ∪ histórico em qualquer estado, sem preço para mercado. Depois, o deal pega o papel pela linha do mapa. Sobram dois buracos de severidade MÉDIA: o casamento não exclui tickets já gravados em outra linha, e um deal visível antes da sua ordem vira X depois de `CARENCIA_DEAL` |
| A-1 `em_espera` | **FECHADO** | §4.2, cabeçalho. Verifiquei X3, que exige sem A viva, sem E viva ou pendente e sem K, e E1, que exige sem E viva ou pendente. Nenhuma linha de baixo age no lugar da que espera |
| A-2 S sumida | **FECHADO** | SUMIDA com `sumida_msc`; `reduz_pend` inclui S; P1 exige "nenhuma S pendente ou sumida"; X3 exige `reduz_pend` falso |
| A-3 lado do nível | **FECHADO** | §4.3: cada candidato é conferido pelo lado e pelo preço |
| A-4 E2 / evento | **FECHADO** | `pode_entrar` único para P1 e E1; `id_entrada`; `ENTRADA_EXECUTADA` |
| A-5 laço depois de C+2 | **FECHADO** | §5.2: a tabela não roda e o passo 3 só age com `liquida` = 0. Ver N-4, ao lado |
| A-6 corte sem histórico | **FECHADO** | §1.1: a base não inclui o histórico; o motor de corte usa só a base |
| A-7 bloqueio × E vivas | **FECHADO** | §2.4 cancela as E de todos |
| A-8 nível atravessado | **PARCIAL** | A S de emergência existe, mas não é estável nem "sempre colocável": ela persegue o preço (N-2) e depende de bid/ask válidos (N-3) |

## 2. Mudanças de spec do §11

**A. S executada antes da E = TROCADA.** É segura. **Não sai duplicado.** Refiz os dois casos:
- *E limite viva, f = −1 aberta por S.* Ciclo 1: P1 manda a S de compra que protege o −1. Ciclo 2: X2 manda o K da E. X3 não age enquanto houver E viva ou pendente e enquanto houver K pendente. Daí:
  - se a E enche antes do K, o K resolve "executou antes", a ficha vai a 0 e nenhuma X sai. L3 cancela a S de compra no ciclo seguinte;
  - se o K vence, a E é provada cancelada e só então X3 compra 1.
- *C1, E a mercado PENDENTE.* A linha pendente deixa o robô não `provado`, portanto RESTRITO, e nada é enviado até o desfecho da E.

O resultado econômico é o mesmo da spec. Fica um risco novo, BAIXO: a S de compra criada para o −1 transitório pode disparar entre o fill da E e o L3, o que dá uma TROCADA de 1 contrato, que é corrigida.

**B. Nível atravessado → S de emergência.** A ideia é segura e melhor que a spec 9.3. A execução tem dois defeitos, N-2 e N-3.

**C. Prova por ausência também com ticket.** É aceitável. O pior caso é o mesmo da decisão 3: uma X que executou, mas ficou mais de 30 s fora do histórico, é reenviada, a ficha inverte em 1 contrato e I2 corrige. Como `f` sai dos deals, um desfecho errado só afeta as guardas e nunca a ficha. O texto precisa dizer que uma linha NAO_EXECUTADA que depois ganha deal passa a EXECUTADA. O dono deve ver isto, porque com ticket a chance de a ordem ter executado é maior que com ticket 0.

**D. PROTEGENDO corrige e zera.** É segura. Requisito de implementação: PROTEGENDO pode vir de tamanho de tick 0. Nesse caso nenhum caminho (piso, normalização da S, emergência) pode dividir pelo tick lido; use o tick do WIN como constante.

**E. `HB_TOMADA` de 60 s.** **Cria risco ALTO (N-5).**

## 3. Achados novos

**N-1 (CRÍTICO): o Δ externo virtual é disparado por atraso normal entre deal e posição.**
- **Mecanismo (§2.2).** Com todos os robôs provados e Δ_resto ≠ 0, a diferença "entra na regra 7.1 (absorção, bloqueio)". O MT5 não garante que `PositionSelect` e o histórico se atualizem juntos.
- **Caso.** A E de compra enche. O deal +1 já aparece no histórico e a `liquida` ainda está em 0. Isso dá Δ = −1 e um deal virtual que reduz abaixo de Σ fichas, ou seja, uma zeragem manual. Dentro do mesmo ciclo:
  - o +1 do robô é absorvido;
  - liga o **bloqueio com botão**, que fica persistido e vale até para o dia seguinte (spec 10.1);
  - as E de todos são canceladas;
  - L3 vê `f` = 0 provado e **cancela a S da posição recém-aberta**.
- **No ciclo seguinte** a posição se atualiza e a ficha volta a +1, mas sem S e com o pregão bloqueado.
- **Ajuste.** O deal virtual só depois de Δ_resto ≠ 0 estável por `PROVA` com conexão ok. Antes disso, todos os robôs ficam RESTRITOS, que é o comportamento da v2.0 nesse caso. Absorção por deal virtual nunca alimenta L3 nem L2.

**N-2 (ALTO): a S de emergência persegue o preço.**
- **Mecanismo.** A cadeia do §4.3 é recalculada a cada ciclo e termina em `bid − 1.200` (compra) ou `ask + 1.200` (venda). Ela não tem o passo "nível da S viva", que a spec 10.2 passo 8 tem, e a emergência não é gravada como nível pedido.
- **Efeito.** P3 manda `MOVE_S` a cada ½ tick. Numa compra, o stop desce junto com o bid e nunca é atingido: a proteção some. Além disso o `OrderModify` sai a cada 250 ms, o que pode levar a corretora a limitar a taxa. Aparece em (a), (d) e (l).
- **Ajuste.** A emergência é calculada uma vez e gravada como nível pedido. A cadeia inclui a S viva quando ela é válida. P3 não move uma S que está na emergência.

**N-3 (ALTO): a emergência usa bid/ask sem validar.**
- **Caso.** Na pré-abertura e no leilão, bid/ask podem estar em 0, velhos ou cruzados. O cenário (d) usa o "bid indicativo".
- **Efeito.** Com bid 0 nenhum candidato é válido e a emergência sai negativa (compra), o que dá recusa em laço. Do lado da venda, sai uma `BUY_STOP` muito abaixo do mercado. Se for aceita, ela dispara na abertura junto com a X3 das 09:00, e a ficha inverte.
- **Ajuste.** Só calcular nível com preço válido (bid > 0, ask ≥ bid, tick recente); sem isso, P1 espera. X3 não sai se houver uma S do robô num nível já cruzado pelo preço; nesse caso a S faz a saída.

**N-4 (ALTO): o deal do `C_CONTA` (magic MAESTRO) é tratado como externo.**
- **Mecanismo.** Pelo §1.3, um deal de magic que não é de robô é externo. O `C_CONTA` que fecha fichas de robô reduz a líquida abaixo de Σ fichas, o que é uma zeragem manual.
- **Efeito.** Liga o bloqueio com botão, persistido para o dia seguinte, com um ALERTA falso de zeragem manual. Se algum episódio passa a noite, a janela do dia seguinte inclui esse deal e cria **fichas fantasma**. Exemplo: CM +1 e RE −1 com a líquida em 0 recebem uma S e uma X cada uma, e a exposição passa a ser real.
- **Ajuste.** Deal MAESTRO é "encerramento": zera todas as fichas, não absorve e não bloqueia.

**N-5 (ALTO): `HB_TOMADA` de 60 s e o `ExpertRemove` na recusa (§1.6).**
- **Mecanismo.** Num crash ou reinício do MT5, o `OnDeinit` não roda e a trava fica com heartbeat recente. Se o `ChartID` mudar no reinício, o token muda junto.
- **Efeito.** Um reinício que leva menos de 60 s vê um "heartbeat alheio" com menos de `HB_TOMADA`, e o EA chama **`ExpertRemove`**. As fichas ficam sem corte e sem proteção, com o dono achando que o EA está no ar. Com 10 s esse caso era raro; com 60 s é o caso normal, que é justamente o cenário (h).
- **Ajuste.** A recusa não remove o EA: ele fica inerte e tenta de novo a cada 1 s. Só se o heartbeat alheio continuar avançando por mais de `HB_TOMADA` há uma segunda instância viva, e aí sim `Alert` e `ExpertRemove`. Conferir P-nova: o `ChartID` sobrevive a um reinício do terminal?

**N-6 (ALTO, de implementação): o `C_CONTA` recusado não tem retentativa definida.**
- **Mecanismo.** No §5.2, uma linha RECUSADA não é PENDENTE, e `em_espera` é por robô. O `C_CONTA` não tem nenhum dos dois freios.
- **Efeito.** O `C_CONTA` é reenviado a cada ciclo de 250 ms até F. É o mesmo padrão de tráfego que pode levar a corretora a recusar as outras ordens.
- **Ajuste.** `em_espera[MAESTRO]` com `RETENTA` e ALERTA, como no passo 6 do §3.

## 4. Cenários refeitos, ciclo a ciclo

**(b) X do C1 com TIMEOUT e ticket 0, 90 s sem internet.**
- Durante a queda o EA fica INVALIDO. Depois da volta continua INVALIDO até completar `CONEXAO` (10 s).
- **Se a X executou:** a ordem aparece `FILLED` e é casada; a X vira EXECUTADA e o deal ganha papel X, então `f` = 0. L3 cancela a S. Se o histórico atrasa em relação à posição, a linha pendente e o Δ_resto ≠ 0 deixam todos RESTRITOS até o deal chegar, e nada é enviado.
- **Se a X não chegou:** a NAO_EXECUTADA só sai depois de 30 s de conexão contínua. Até lá o C1 fica RESTRITO, e o `PRAZO_SAIR` só conta em ciclos confiáveis. Depois disso X3 reenvia.
- **Seguro.** O único risco é a S disparar enquanto o C1 está RESTRITO: isso dá uma TROCADA, que é corrigida (B6).

**(k) A S executa e o deal chega 3 s depois.**
- **Posição já em 0:** a S fica SUMIDA. O robô não está provado e Δ_resto = −1 deixa todos RESTRITOS por 3 s. Nenhum deles cumpre "lado inequívoco", porque o sinal da líquida difere, então nada sai. O deal chega, a ficha vai a 0 e a X3 não age.
- **Order FILLED sem deal:** Δ_resto = 0, então só o robô da S fica RESTRITO e os outros seguem.
- **Posição também atrasada:** a S fica SUMIDA, a contagem de 30 s parte de `sumida_msc`, e o deal chega antes disso.
- **Seguro.** Atenção: o caso inverso, deal antes da posição, é N-1.

**(l) Correção recusada repetidas vezes.**
- P1 põe a S; X3 é recusada e espera 5 s; as linhas de baixo dão Z.
- O ALERTA sai na 5ª recusa e depois a cada 5 min. Em C + 2 min, o `C_CONTA` assume.
- **Seguro só depois de N-2:** a S da TROCADA quase sempre cai na emergência, porque o nível da memória é do outro lado. Sem o N-2, ela é movida a cada ciclo e recua com o preço. Sem o N-6, o `C_CONTA` recusado vira rajada.

**(m) A corretora recusa por 20 min as ordens de um robô; os outros 4 operam.**
- **Robô sem posição:**
  - a S do P1 é recusada e espera 5 s;
  - o `PRAZO_ENTRAR` (10 s) vence e sai `ENTRADA_PERDIDA`;
  - sem `pode_entrar`, nada mais é tentado até o próximo sinal.
  
  Se a S passa e a E é recusada, o `id_entrada` já está consumido: sai `ENTRADA_RECUSADA` e L3 cancela a S. Não há laço.
- **Robô posicionado:**
  - a X3 recusada fica a cada 5 s; a `SAIDA_EXPIRADA` sai aos 60 s e o módulo reavalia;
  - um `MOVE_S` recusado mantém a S no nível antigo;
  - um A recusado espera.
- **Os outros quatro:** uma linha RECUSADA não é pendente, então não mexe em `provado`, Δ nem `confiavel`. Eles seguem intactos, e o O2 não enxerga as ordens recusadas.
- **Seguro, com uma ressalva conforme a spec, para o dono decidir:** se o que é recusado é a própria S, por exemplo por margem, e o robô está posicionado, a ficha fica 20 min sem stop. O desenho só dá ALERTA e não escala para uma saída.

## 5. Lista mínima antes do código

1. **N-1:** o Δ externo virtual só depois de `PROVA` estável; antes disso, todos RESTRITOS; nunca L2 ou L3 a partir de absorção virtual.
2. **N-2:** a emergência é calculada uma vez e gravada; a cadeia inclui a S viva; P3 não persegue.
3. **N-3:** preço válido para calcular nível; X3 não sai se houver uma S num nível já cruzado.
4. **N-4:** deal MAESTRO = encerramento, sem absorção e sem bloqueio.
5. **N-5:** a recusa da trava espera em vez de remover o EA; confirmar a estabilidade do `ChartID`.
6. **N-6:** retentativa e ALERTA no `C_CONTA`.

Com os seis, os 12 cenários do §8 e mais o (m) ficam seguros, e o desenho fica pronto para implementar. O dono ainda precisa aprovar as mudanças A a E do §11. Para a C, informe a ressalva acima; para a E, a mudança só vale com o ajuste 5.
