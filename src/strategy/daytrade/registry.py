"""Registry de robôs de DAY TRADE.

Registry PRÓPRIO, não `strategy.registry` (ver docstring de
`strategy/daytrade/base.py`): `IntradayStrategy` não herda de `Strategy` de
propósito, então `discover_strategies()` nem varre o pacote `daytrade`, e um
robô de um símbolo só não pode competir no mesmo pódio que um robô diário de
carteira (capital/risco/instrumento incomparáveis). Por isso este catálogo é
uma lista EXPLÍCITA, não uma descoberta automática — cada entrada é uma
decisão deliberada de "este robô está pronto para aparecer no painel", não
"toda classe que existir em algum arquivo".

O SÍMBOLO é propriedade do ROBÔ, não do slot (`core.config.Slot` não declara
símbolo nenhum desde 2026-08-21): dois robôs registrados aqui podem operar
símbolos diferentes, e o slot só empresta o caixa/conta/processo — quem
decide o que negociar é a instância escolhida. Isto substitui três cópias do
mesmo mapa `{"gremah": Gremah}` que existiam soltas em `scripts/run_live.py`,
`dashboard/live_service.py` e `dashboard/live_control.py`: um catálogo
declarado em três lugares é um catálogo que diverge quando um robô novo
entra em só dois deles.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from core.instruments import economics_for
from strategy.daytrade.base import IntradayStrategy
from strategy.daytrade.lab.copa_win import CopaWin
from strategy.daytrade.lab.gremah import Gremah
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
from strategy.daytrade.lab.wdo_orb import WdoOrb

# A ORDEM DESTE DICIONÁRIO É O PÓDIO DE DAY TRADE — o primeiro é o TOP-1.
#
# Diferente do ranking de swing (recalculado a cada 6h a partir do diário de
# backtests, ver `journal.reader.top_strategies_by_final_capital`), aqui a
# ordem é DECLARADA. Não é preguiça: robôs de day trade não são comparáveis
# por "capital final" de uma run — nem sempre rodam a mesma granularidade de
# dado ou o mesmo instrumento, então não existe uma run em que apareçam lado
# a lado. Um ranking automático teria de comparar números medidos em bases
# diferentes, que é a comparação desonesta que este projeto evita.
#
# 2026-09-04, decisão do dono: medir `gremah` (M1) contra `gremah_tick`
# (motor tick) nos 9 símbolos que os dois calibravam separadamente,
# decidir qual sobrevive, eliminar o outro — a família tinha dois robôs
# disputando os mesmos ativos, e só um pode operar cada um ao vivo.
#
# RESULTADO -- `gremah_tick` ELIMINADA. `gremah` (M1) fica com o nome
# (por isso não há renomeação: `Gremah.name` já era `"gremah"`).
#
# Comparação de config de PRODUÇÃO (cada motor com a calibração já
# medida/confirmada por ele), histórico completo disponível, capital =
# `capital_minimo_brl` real por símbolo -- `gremah` M1 venceu nos 9 DE 9
# símbolos testados:
#   PMAM3   M1 R$   677,85  x tick R$   186,16
#   KLBN4   M1 R$ 2.085,72  x tick R$   568,41
#   CSAN3   M1 R$   157,39  x tick R$  -375,23  (tick foi NEGATIVA)
#   DASA3   M1 R$   644,49  x tick R$   202,80
#   PCAR3   M1 R$   688,63  x tick R$  -206,53  (tick foi NEGATIVA)
#   KLBN3   M1 R$ 1.463,54  x tick R$   565,48
#   GRND3   M1 R$ 1.464,53  x tick R$    79,77
#   LPSB3   M1 R$   875,54  x tick R$   530,94
#   BMGB4   M1 R$ 1.424,02  x tick R$   106,17
# Ressalva do próprio agente que mediu a tick: CSAN3/PCAR3 negativas podem
# ser efeito de janela mais longa que a testada antes (mesmo mecanismo de
# "capital preso no preço do 1º dia" já documentado na família) e
# mereceriam auditoria própria antes de tratar como decisão isolada -- mas
# a vitória do M1 não depende só dessas duas linhas.
#
# Confirmação com protocolo IS/OOS de verdade (não só histórico
# combinado), nos dois símbolos que hoje operam com dinheiro real:
#   PMAM3  M1   IS R$   480,88 / OOS R$  191,16  (R$  672,04 combinado)
#          tick IS R$   177,19 / OOS R$   54,96  (R$  232,15 combinado)
#          M1 vence por ~2,9x
#   KLBN3  M1   IS R$ 1.259,25 / OOS R$  197,81  (R$1.457,06 combinado)
#          tick IS R$   512,95 / OOS R$   60,04  (R$  572,99 combinado)
#          M1 vence por ~2,5x
#
# O que isso CONTRARIA, e precisa ser dito: a decisão original de
# 2026-08-22 (preservada como registro histórico logo abaixo) preferia a
# tick por argumento TEÓRICO de realismo de preenchimento (ordem só conta
# como tocada se alguém negociou no nível, contra o M1 que resolve stop-e-
# alvo-na-mesma-barra por "chute pessimista"). A medição não confirmou:
# a tick gera MAIS trades por símbolo em todos os casos (edge mais fino
# por trade, mesmo achado de `edge_subtick_familia_gremah` -- 18/18 pares
# abaixo de 1 tick de edge), e isso não compensa no líquido. Este projeto
# mede para decidir, não decide por argumento teórico quando a medição
# contraria -- ver CLAUDE.md.
#
# Mecanismos `defesa_recuo`/`corte_persistencia` (mesmo pedido do dono,
# mesma rodada): TESTADOS nos dois motores antes desta decisão --
# `defesa_recuo` degenerado ou prejudicial (alvo de 1 tick não deixa
# espaço pra "quase lá"), `corte_persistencia` com efeito real mas em
# combos DIFERENTES por símbolo (ver `scripts/daytrade/gremah_defesa_
# corte_sweep_2026_09_03.py`) -- AINDA NÃO ativado em produção, decisão
# pendente do dono (mesmo padrão do `copa_win` acima: só liga depois de
# decisão explícita, nunca por default silencioso).
#
# 2026-08-28, decisão do dono: `copa_win` entra no pódio como TOP-2,
# empurrando `gremah_tick` para TOP-3 e `gremah` para TOP-4. Por quê:
# recalibração de `alvo_vol`/`stop_vol` (varredura de 400 células,
# `run_copa_score.CALIBRACAO_IS["WIN@"]`) confirmada em OOS explícito —
# diferente da calibração antiga (que caía de R$62,24 para R$3,84/pregão
# fora da amostra), o par (19,12) MELHOROU no OOS: R$54,86 → R$61,80/pregão,
# Calmar OOS 3,04, IS+OOS combinado R$56,82/pregão (ver a memória
# `copa-win-recalibracao-alvo-stop-2026-08-28`). Os kwargs de instanciação
# default (`_KWARGS_PADRAO` abaixo) replicam essa calibração; `teto_contratos`
# usa o teto OFICIAL da Copa 2025 (15) só como CEILING regulatório — o
# dimensionamento real por pregão vem de `margin_per_contract_brl` (margem
# WIN do projeto, ver a tabela de capital mínimo no `CLAUDE.md`), que ativa a
# realocação por caixa (`CopaWin.quantidade_por_entrada`) e reproduz o
# tamanho (1 contrato) com que a calibração foi de fato medida/confirmada.
#
# 2026-08-27, decisão do dono: `wdo_grid_reload_maker` sobe a TOP-1. Por quê:
#   - é o único robô de day trade do projeto com confirmação OOS que
#     SUSTENTA: R$148,89/pregão combinado, 89% de retenção IS→OOS, 30/30
#     blocos de 4 pregões positivos (o critério da própria Copa BTG,
#     `backtest/intraday/copa_score.py`) — quando esta ordem foi decidida,
#     nenhum outro candidato medido (CopaWin, ORB, M5 pré-registrada) tinha
#     passado nesse crivo (a recalibração/confirmação OOS do `copa_win`
#     acima é de 2026-08-28, um dia depois desta decisão);
#   - é o único cujo edge NÃO depende de prever direção — depende de
#     execução (a ordem ser preenchida no toque), o que sobrevive mesmo à
#     conclusão de que prever direção no WIN/WDO não funciona (linha da
#     Copa BTG, encerrada por refutação em 2026-08-26).
# O que a ordem NÃO afirma, e precisa ser dito junto: o número inteiro
# depende de uma taxa de preenchimento passivo (ordem parada tocada no
# nível) que NUNCA foi medida com dado de livro real — só o teste ao vivo
# com 1 contrato resolve isso, e até lá o robô é TOP-1 por qualidade de
# medição sobre o dado disponível, não por validação em dinheiro real. Ver
# `WdoGridReloadMaker.plain_summary`.
#
# 2026-08-28, decisão do dono: o default de `stop_ticks` da classe mudou de
# 16 para 4 (varredura completa profit_ticks/stop_ticks 1..20, ver a
# memória `wdof1-grid-1a20-encerrada-2026-08-28`) — T1 S4 domina T1 S16 em
# todas as métricas no IS. A confirmação OOS citada acima (R$148,89/pregão,
# 89% de retenção) descreve especificamente T1 S16, NÃO o default de então:
# T1 S4 nunca foi medido fora da amostra.
#
# 2026-08-29, REVERTIDO de volta para 16 (default da classe voltou a ser
# `stop_ticks=16`): a ressalva acima se confirmou, e de forma mais grave do
# que "não foi medido fora da amostra" — rodando o histórico salvo INTEIRO
# (177 pregões) com CAIXA REAL (não nocional), T1 S4 nunca sobrevive ao
# próprio histórico com capital realista: trava (cai abaixo do piso de
# capital pra abrir 1 contrato — item 1.14/3.9 de `LICOES_DE_PRODUCAO.md` —
# e NUNCA recupera dali em diante) em todo nível de capital testado até
# R$20.000, e só sobrevive com R$30.000 — mesmo assim fechando em
# +R$4.586,87 (quase só devolvendo o capital, líquido de R$-25.413,13 sobre
# R$30.000). T1 S16 sobrevive com só R$5.000 e fecha estável em +R$2.671,80
# a partir daí (idêntico de R$5.000 a R$30.000). Win rate no mesmo teste:
# 65,7% (S4) contra 90,3% (S16) — S4 é estruturalmente pior (a razão
# risco:retorno 1:4 exige >80% de acerto pra empatar; 65,7% fica abaixo
# disso), não uma diferença de amostra. Ver `scripts/daytrade/wdof1_stress_
# capital_real_historico_completo.py` e a memória `wdof1-stop-ticks-4-
# producao-2026-08-28` (atualizada com a reversão). O robô segue TOP-1, e a
# confirmação OOS original (R$148,89/pregão, 89% de retenção) volta a
# descrever o default em produção.
#
# SUPERADO em 2026-09-04 -- ver o bloco no topo do arquivo: gremah_tick foi
# eliminada, a medição contrariou o argumento abaixo. Preservado como
# registro histórico da decisão original.
#
# 2026-08-22, decisão do dono (ordem original, agora TOP-3/TOP-4): entre
# `gremah_tick` e `gremah`, tick a tick não tem a ambiguidade "stop e alvo
# na mesma barra" que o M1 resolve por chute pessimista — um negócio tem um
# preço só; ao vivo, apaga a divergência de até 60s que `live/
# intraday_runtime.py` declara; e uma ordem-limite só é dada como tocada
# quando alguém NEGOCIOU no nível, em vez de bastar a faixa do minuto
# contê-lo. O que essa ordem não afirma: a `gremah_tick` tem medição
# própria em UM ativo (PMAM3) contra os dez da `gremah` — é por isso que
# `GremahTick.calibrated_setups()` oferece um só.
# 2026-09-10, ordem do dono ("coloque ela em produção"): `wdo_orb` entra no
# pódio como TOP-1, empurrando `wdo_grid_reload_maker` para TOP-2.
#
# Por quê a ORB sobe: ela é a ÚNICA candidata viva do projeto. A família
# maker — de que `wdo_grid_reload_maker` é o TOP-1 histórico — foi encerrada
# por refutação em 2026-09-10, quando a fila real do livro foi calibrada
# contra extrato (438/489, `backtest/intraday/fidelidade.py`): o bruto por
# operação cai para R$0,45 contra R$0,50 de corretagem, ou seja, o edge dela
# só existia com fila ZERO. Toda a confirmação OOS citada mais acima
# (R$148,89/pregão, 89% de retenção, 30/30 blocos) foi medida sob essa
# premissa, e portanto descreve um motor, não o mercado. Deixar um robô
# refutado em cima da única candidata viva faria o painel recomendar o
# errado, que é exatamente o que uma ordem DECLARADA existe para evitar.
#
# O QUE ESTA ORDEM NÃO AFIRMA, e tem de ser lido junto: a ORB **não** passou
# o crivo estatístico. Win 56,94% em 72 operações do IS, IC95%
# [45,4 ; 67,7], breakeven empírico 47,74% — o breakeven cai DENTRO do
# intervalo, então o veredito é INDEFINIDO, não positivo. Levar o limite
# inferior acima do breakeven pede ~150 operações; IS (72) + OOS (51) somam
# 123, e o OOS segue INTOCADO (ninguém gastou o teste cego). Ela é TOP-1 por
# ser a melhor medição viva sobre o dado disponível e por decisão explícita
# do dono ("já considero que ela está apta para ser promovida"), com 1
# contrato — não por validação em dinheiro real.
#
# O que a ORB tem e a família maker não tinha: o resultado dela NÃO depende
# de ganhar fila. Ela entra por limite esperando um RECUO (2 ticks atrás do
# rompimento) e aceita não ser preenchida — 19,4% dos pregões passam em
# branco de propósito. Fila alta não inverte o sinal dela; só reduz quantos
# pregões operam.
_ROBOTS: dict[str, type[IntradayStrategy]] = {
    WdoOrb.name: WdoOrb,
    WdoGridReloadMaker.name: WdoGridReloadMaker,
    CopaWin.name: CopaWin,
    Gremah.name: Gremah,
}

#: kwargs extras pra robôs cujo construtor exige parâmetro sem default
#: (`copa_win`: `teto_contratos` é obrigatório de propósito, ver a
#: docstring de `CopaWin.__init__` — herdar um número em silêncio ali seria
#: o mesmo erro que `Gremah` evita ao recusar símbolo sem calibração) OU que
#: precisam de dimensionamento dinâmico por caixa ligado explicitamente
#: (`wdo_grid_reload_maker`, ver abaixo). `cls()` sem isto explodiria (copa_win)
#: ou rodaria estático em 1 contrato pra sempre (wdo_grid_reload_maker) em
#: `list_daytrade_robots`/`get_daytrade_robot`/`symbols_for_robot`.
#:
#: `wdo_orb` NÃO aparece aqui de propósito: os defaults da CLASSE já são a
#: configuração de produção, número por número. É a mesma decisão tomada em
#: 2026-09-09 para o sem-prazo do `wdo_grid_reload_maker` ("não fica repetido
#: aqui", ver o comentário lá embaixo) — repetir um valor nesta tabela cria
#: duas fontes para o mesmo número, que é como um lado muda e o outro não. O
#: efeito colateral é o que se quer: script de laboratório, teste e sweep que
#: fazem `WdoOrb()` direto herdam a produção inteira, então backtest e robô
#: ao vivo descrevem o MESMO robô.
_KWARGS_PADRAO: dict[str, dict] = {
    # 2026-08-29, pedido do dono depois de descobrir que o CopaWin já escala
    # contratos com o caixa e a WDO F1 não ("wdo também tem que ser dinâmico,
    # conforme o capital cresce é natural aumentar os contratos"):
    # `WdoGridReloadMaker` SEMPRE pediu exatamente 1 contrato em produção
    # (`default_quantity=1` do perfil de futuro, `margin_per_contract_brl`
    # da estratégia nunca setado) — o modo dinâmico existe no construtor
    # desde 2026-08-27 mas era OPT-IN, nunca ligado aqui. `margin_per_
    # contract_brl=150.0` (margem real do WDO@) ativa a realocação por
    # caixa; `hard_cap_contratos=5` replica o teto REGULATÓRIO do perfil
    # (`profiles.py`, `max_open_contracts` do WDO@) — sem isto a estratégia
    # pediria mais contratos do que o motor aceita e toda entrada acima do
    # teto do motor seria recusada em silêncio (bug de setup já visto em
    # `wdof1_teto_por_risco_2026_08_29.py`, nunca reproduzir em produção).
    # `risco_pct_por_trade`/`point_value_brl` (item 3.9; o valor do ponto
    # vem de `core.instruments` -- ver o bloco acima): mesmo
    # mecanismo do `copa_win` abaixo, mas NÃO o mesmo NÚMERO — copiar 5% sem
    # medir fez o capital R$5.000 (antes o piso limpo, ver item 3.11) quase
    # zerar (líquido −R$4.753,12, equity mínima R$246,88) porque o stop
    # desta estratégia é FIXO em R$ (16 ticks × R$0,50 × R$10/ponto = R$80/
    # contrato, CONSTANTE, diferente do stop por volatilidade do CopaWin) —
    # 5% de R$5.000 já libera 2-3 contratos enquanto o caixa ainda está
    # perto do piso, amplificando a sequência de perdas normal antes de
    # existir folga de verdade. Varredura de {1%, 2%, 3%, 5%} em
    # `scripts/daytrade/wdof1_calibracao_risco_pct_2026_08_29.py` achou 1%
    # como o único valor que NUNCA regride nenhum nível de capital já
    # medido (R$3.000/R$5.000 saem IDÊNTICOS ao dimensionamento estático de
    # antes) e ainda ganha de verdade em capital alto: R$50.000 fecha em
    # +R$13.095,09 (dinâmico) contra +R$2.671,80 (o que o 1-contrato-fixo
    # SEMPRE dava, em qualquer capital, antes desta mudança). 1% é a escolha
    # mais conservadora testada — 2%/3% renderam mais em alguns níveis
    # intermediários sem regredir nenhum dos testados, mas com margem de
    # segurança menor; ver a memória `wdo-dinamico-producao-2026-08-29` se
    # quiser reconsiderar depois de mais medição.
    # 2026-09-08, ORDEM DO DONO: liga `fatiar_saida_alvo` em produção.
    # Contexto -- o alvo NATIVO (`target_fills_as_maker=True` sem fatia)
    # desliza SEMPRE contra (item 4.8/6.18 de LICOES_DE_PRODUCAO.md, secao
    # "O motor COBRA o deslize do TP" do CLAUDE.md): 10 de 11 saidas reais
    # mediram pior que o nivel pedido, e isso apagou o edge do T2/S16 (breakeven
    # sobe de 90% para 95%). `fatiar_saida_alvo=True` troca o gatilho a
    # mercado por ordem-limite REAL parada no livro -- mesmo mecanismo que a
    # `gremah` ja usa (`dividir_entrada`), agora ligado aqui pela primeira
    # vez. Previa de 10 pregoes do IS (capital R$375, T2/T3, script
    # `wdof1_fatiar_saida_alvo_previa_2026_09_08.py`) reverteu o quadro:
    # T2 +R$21.033,50 (vs -R$242,50 no alvo nativo), T3 +R$12.928,50 (vs
    # -R$229,00), 0 de 10 pregoes sem trade nas duas (antes 8-9 de 10).
    #
    # Risco que fica ABERTO com esta troca, sem medicao ainda (dono foi
    # avisado antes de mandar aplicar): (1) a previa e' so' 10 pregoes do IS
    # -- a janela cheia IS/OOS nao foi rodada; (2) o alvo fatiado nao tem
    # TP registrado na corretora (`live.intraday_runtime._alvo_atomico`
    # recusa amarrar TP em posicao fatiada de proposito -- so' o STOP fica
    # protegido no broker, o alvo depende do processo do robo mandando a
    # ordem-limite a cada barra); (3) `exit_ttl_bars=8` e' o default de
    # `WdoGridReloadMaker` (EMPRESTADO de `gremah.py::EXIT_TTL_BARS_PADRAO`,
    # calibrado para PMAM3/acao M1, NAO para o WDO F1) -- funcional (sem
    # ele a execucao real quebra com `AssertionError`), mas nao e'
    # calibracao propria.
    #
    # A ECONOMIA DO INSTRUMENTO NAO SE DIGITA AQUI (2026-09-09). Margem por
    # contrato e valor do ponto sao propriedade do INSTRUMENTO -- dois robos
    # no mesmo simbolo tem obrigatoriamente os mesmos numeros -- e vem de
    # `core.instruments.FUTUROS`, que e' a fonte da verdade tambem do
    # `SymbolProfile` do lado do `backtest/`.
    #
    # Ate 2026-09-09 estes numeros estavam REDIGITADOS aqui (150,0 e 10,0),
    # porque `strategy/` e' feature e nao pode importar `backtest/`
    # (AGENTS.md, regra 1), e o que impedia os dois lados de divergirem em
    # silencio era um teste de amarracao. Teste de amarracao e' rede, nao
    # conserto: avisa DEPOIS que o numero errado foi digitado, e so' se a
    # suite rodar. A saida ja estava escrita na propria regra 1 -- "se uma
    # feature precisa de dado de outra, o dado sobe para `core/`".
    #
    # O que continua digitado aqui e' o que NAO e' do instrumento:
    # `hard_cap_contratos=5` e' o teto REGULATORIO da Copa BTG 2025 (espelha
    # `SymbolProfile.max_open_contracts`, nao a economia -- ver a docstring
    # de `core.instruments`), e `risco_pct_por_trade` e' calibracao DESTE
    # robo (1%, medido; NAO os 5% do `copa_win` -- ver o bloco acima).
    WdoGridReloadMaker.name: dict(
        margin_per_contract_brl=economics_for("WDO@").margin_per_contract_brl,
        hard_cap_contratos=5,
        risco_pct_por_trade=0.01,
        point_value_brl=economics_for("WDO@").point_value_brl,
        fatiar_saida_alvo=True,
        # 2026-09-09, ORDEM DO DONO: "remova do codigo em producao o ttl".
        # A fatia do alvo deixa de ter prazo -- fica parada no livro ate' o
        # mercado PAGAR o alvo, e nunca mais sai a mercado por impaciencia.
        # O motivo, os numeros do dia real que motivaram e o porque de ser um
        # numero gigante em vez de `None` estao na constante, em
        # `wdo_grid_reload_maker.EXIT_TTL_BARS_SEM_PRAZO`. Em uma linha: 34
        # operacoes reais com prazo 60 deram -R$3,00 por operacao porque so'
        # 26% das saidas pegaram o alvo inteiro -- as outras estouraram o
        # prazo e sairam a mercado por 0 ou +-1 tick.
        #
        # NAO fica repetido aqui: 2026-09-09, segunda ordem do dono ("o
        # default deve ser sem prazo"), o proprio default da classe virou
        # `EXIT_TTL_BARS_SEM_PRAZO`. Repetir o valor nesta tabela criaria
        # duas fontes para o mesmo numero, que e' como um lado muda e o
        # outro nao. Quem constroi `WdoGridReloadMaker()` direto -- script
        # de laboratorio, teste, sweep -- passa a herdar o sem-prazo junto,
        # que e' o ponto: backtest e producao descrevendo o MESMO robo.
    ),
    CopaWin.name: dict(
        # `alvo_vol`/`stop_vol` e os demais campos abaixo são
        # `run_copa_score.CALIBRACAO_IS["WIN@"]` (recalibrado e confirmado em
        # OOS em 2026-08-28) — trocar aqui sem trocar lá (ou vice-versa) é o
        # catálogo divergindo da calibração que a memória documenta.
        # 2026-09-11, ORDEM DO DONO -- `alvo_vol` cai de 19,0 para 9,5 (50% do
        # que a calibracao de 2026-08-28 pedia) e o alvo passa a sair por
        # ORDEM-LIMITE REAL fatiada (`fatiar_saida_alvo=True`). Os dois andam
        # JUNTOS de proposito: o alvo menor so' vale medido no mecanismo de
        # execucao correto, e o mecanismo correto so' vale a pena com o alvo
        # que de fato e' alcancado. Ver a secao "Alvo por ORDEM-LIMITE REAL
        # fatiada" em `copa_win.py`.
        #
        # O QUE MOTIVOU -- diagnostico de excursao (`copawin_excursao_alvo_
        # stop_2026_09_11.py`, 321 trades): o alvo de 19,0 era alcancado por
        # 6,9% dos trades e a excursao favoravel MEDIANA parava em 31,6% dele.
        # Na pratica o robo nao tinha alvo, tinha RELOGIO: 56,1% das saidas
        # eram por achatamento de fim de pregao, e elas carregavam 114,1% do
        # lucro liquido -- o resultado era decidido por onde o dia fechou.
        #
        # O QUE MUDOU, medido (`copawin_alvo_menor_sweep_`, `copawin_alvo_
        # fatiado_fila_sensibilidade_` e `copawin_escada_x_alvo_cruzado_`,
        # todos 2026-09-11, IS 129 pregoes + OOS 55, veredito por IC95% do
        # win% contra o breakeven EMPIRICO):
        #
        #   capital R$3.000    alvo 19,0 (tp nativo)   alvo 9,5 (limite real)
        #   IS  liquido             +R$ 11.221,50            +R$  7.351,00
        #   OOS liquido             +R$  4.007,50            +R$  5.254,30
        #   OOS MaxDD                      -33,6%                   -17,1%
        #   OOS lucro/DD                      3,48                     5,64
        #   saida por alvo                     7,2%                    20,3%
        #   saida pelo sino                   56,7%                    39,1%
        #   lucro vindo do sino              109,9%                     ~3%
        #
        #   capital R$250 (o REAL)  alvo 19,0 (tp nativo)  alvo 9,5 (limite)
        #   IS                      ZEROU (caixa -R$7,10)    +R$ 7.191,10
        #   IS pregoes sem trade           116 de 129            0 de 129
        #   OOS                      -R$247,50 (1 trade)     +R$ 5.111,00
        #   OOS pregoes sem trade            54 de 55             0 de 55
        #
        # O IS PIORA e o OOS MELHORA, e isso e' o sinal que se quer ver: parte
        # do IS antigo vinha de otimismo de execucao que o mecanismo novo
        # removeu (o `tp` nativo preenchia no toque; a limite exige orcamento
        # de volume). A sensibilidade a FILA foi varrida ate' 2x o volume da
        # barra M1 mediana do WIN@ (49.924 contratos na nossa frente) e NAO
        # move o resultado -- o WIN@ gira 24.962 contratos/minuto contra 2.935
        # do WDO@, e a posicao deste robo vive HORAS, nao segundos. Confirmado
        # por teste de sanidade (a 25 milhoes de contratos o acerto do alvo
        # vai a zero, entao o modelo esta ligado -- ele so' nao morde aqui).
        #
        # A ESCADA DE PERDA POR TRADE (`teto_perda_abs_brl`, pedida pelo dono
        # na mesma data) NAO entra, e a razao e' medicao, nao esquecimento.
        # Cruzada com este alvo (`copawin_escada_x_alvo_cruzado_2026_09_11`,
        # 4 alvos x 4 tetos x 3 capitais x 2 janelas), a escada DESLIGADA
        # venceu em 8 de 8 combinacoes de alvo x janela no capital sem
        # censura. Com alvo 9,5 no IS a R$3.000: desligada +R$7.351,00,
        # teto R$200 +R$1.386,60, teto R$125 -R$2.936,80. O mecanismo e' o
        # que `wdo_orb.alvo_multiplo` ja documentava em sentido contrario --
        # com stop largo o perdedor sai pelo relogio com perda PEQUENA; com
        # stop apertado o MESMO trade sai no stop CHEIO. A escada continua
        # implementada e testada, opt-in, desligada.
        #
        # `alvo_vol` deixa de espelhar `run_copa_score.CALIBRACAO_IS["WIN@"]`
        # (que segue com 19,0, historico): aquela calibracao otimizou LIQUIDO
        # sobre o motor de ate 2026-09-08, que entregava o alvo maker de graca
        # e sem fila. Os demais campos abaixo continuam sendo ela.
        #
        # 2026-09-11 (MESMA DATA, RODADA SEGUINTE), ORDEM DO DONO "aplique a
        # recomendada em producao": `alvo_vol` 9,5 -> 7,6 e
        # `entrada_ttl_barras` 15 -> 5. Os dois JUNTOS, nunca separados --
        # ver o porque no fim deste bloco.
        #
        # O PEDIDO ERA OUTRO, e e' isso que define a escolha: "ganhadora mesmo
        # que pouco, mas constante". A funcao objetivo deixou de ser `liquido
        # R$` e passou a ser declarada ANTES de medir, em
        # `copawin_consistencia_diagnostico_2026_09_11.py` -- fracao de
        # pregoes positivos, de blocos ROLANTES de 20 pregoes positivos, de
        # meses positivos, concentracao nos 5 melhores dias, maior sequencia
        # negativa, e quanto do lucro depende do achatamento de fim de pregao.
        # Sem declarar isso antes, a varredura reotimizaria liquido e
        # devolveria o mesmo robo de tudo-ou-nada.
        #
        # O DIAGNOSTICO, que mudou o alvo da busca: a config de 9,5 JA ganhava
        # (+R$13.533,30 em 191 pregoes, 59% dos pregoes com operacao
        # positivos, 84% dos blocos de 20) e JA nao dependia do fechamento (o
        # achatamento carrega 2% do liquido, contra 114,1% da config
        # anterior). O que sobrou desequilibrado foi o TAMANHO do stop --
        # -R$437,77 por stop contra +R$267,74 por alvo, 1,64x.
        #
        # O QUE FOI MEDIDO E REFUTADO antes de sobrar estes dois parametros
        # (~1.400 simulacoes; scripts `copawin_grade_constancia_`,
        # `_freios_e_corte_`, `_robustez_por_data_de_inicio_2026_09_11.py`):
        #   * `trail_vol` ligado (2,0/4,0) -- win% desaba para 33-38% e cola
        #     no breakeven empirico em 40 de 40 celulas. O stop arrastado
        #     corta o vencedor antes de ele pagar o perdedor, e este robo vive
        #     de poucos trades grandes (docstring do modulo `copa_win`).
        #   * `stop_vol` mais curto (4/6/8/10) -- degrada monotonicamente, e
        #     12 e' OMBRO: 14/16/20 tambem pioram. Por isso `stop_vol` NAO
        #     muda aqui.
        #   * `corte_persistencia_frac_adverso` 0,6-0,9 -- o robo QUEBRA: 123
        #     a 150 dos 191 pregoes sem trade, caixa abaixo do portao.
        #   * `risco_pct_por_trade` 1%/2%/5% -- INERTE. A R$3.000 a quantidade
        #     fica presa em 1 contrato pelo piso de `quantidade_por_entrada`,
        #     entao NAO EXISTE hoje um dial de "ganhar menos e oscilar menos".
        #   * `max_entradas_dia`, `perda_max_dia_pontos`, mexer na
        #     `defesa_ativa`, `janela_rompimento` 5/20/30, `aquecimento_barras`
        #     30/60/90 -- todos piores, e os da defesa compram lucro com CAUDA
        #     (pior pregao de -R$1.469 para -R$2.166).
        #
        # O QUE O PAR NOVO ENTREGA, historico de 191 pregoes a R$3.000:
        #
        #                        liquido    MaxDD  lucro/DD  bl20+  mes+  pior dia
        #     9,5 / ttl15     13.533,30   -50,3%      2,68    84%   80%  -1.986,50
        #     7,6 / ttl5      18.322,40   -28,9%      6,70    97%  100%    -947,40
        #
        # E o teste que DECIDE, porque e' a unica forma medivel de "eu ganho
        # sempre?" que nao depende do sorteio das primeiras operacoes (mesma
        # metodologia que fixou `capital_minimo_recomendado_brl` em R$3.000):
        # 76 datas de inicio, horizonte FIXO de 40 pregoes cada --
        #
        #     9,5 / ttl15    89,5% das datas positivas, PIOR inicio -R$888,40
        #     7,6 / ttl5    100,0% das datas positivas, PIOR inicio +R$725,30
        #
        # POR QUE OS DOIS JUNTOS, e nunca so' um. O prazo curto SOZINHO, com o
        # alvo antigo (a9,5+ttl5), e' PIOR que a producao no criterio que
        # importa: 96,1% das datas, UMA morte, pior inicio -R$2.992,50. O alvo
        # sozinho (a7,6+ttl15) ja da 100%, mas com liquido de +R$14.271,90 e
        # MaxDD de R$2.702. O par e' que entrega os dois.
        #
        # `entrada_ttl_barras=5` NAO e' numero de grade justificado depois: o
        # mecanismo ja estava escrito no CLAUDE.md, medido no `wdo_orb` --
        # ordem-limite de entrada com prazo longo preenche horas depois do
        # sinal (269,7 minutos no caso medido) e "os fills atrasados foram
        # justamente os piores resultados". O `copa_win` rodava com 15 desde
        # sempre, herdado e NUNCA medido. A licao existia e nao tinha sido
        # varrida nas outras instancias -- e' o item novo de
        # LICOES_DE_PRODUCAO.md desta rodada.
        #
        # O CUSTO, dito junto (sem ele a tabela acima mente por omissao):
        #   1. PERDE NO OOS -- +R$3.206,00 contra +R$4.255,30 da config
        #      anterior, e o veredito la' cai de POSITIVO para INDEFINIDO
        #      (IC95% [47,2;62,2] atravessa o breakeven empirico de 48,47%).
        #      No IS e no historico inteiro segue POSITIVO.
        #   2. O OOS do WIN@ (>=2026-06-13) JA FOI GASTO varias vezes,
        #      inclusive nesta mesma data. NAO existe teste cego para este
        #      robo. O que sustenta a troca e' o PLATO no eixo do alvo (7,6 e
        #      8,55 dao os dois 100% das datas), os 100% das datas de inicio
        #      (robustez, nao cegueira), o mecanismo ser legivel nos dois
        #      parametros, e sobreviver a fila ate 4x o volume mediano da
        #      barra M1 (`copawin_candidato_a76_validacao_2026_09_11.py`).
        #   3. EXISTE VARIANTE QUE RENDE MAIS E FOI DESCARTADA: `a7,6 ttl8`
        #      da +R$23.812,70 e passa POSITIVO tambem no OOS, mas com MaxDD
        #      de 50,1% e pior pregao de -R$2.913,50. O eixo do prazo NAO tem
        #      plato de liquido (ttl 3/5/8/15 = 7,3k/18,3k/23,8k/14,3k --
        #      vizinhos discordando em 60%), entao escolher o 8 seria pegar o
        #      maior numero de um eixo ruidoso. `ttl5` e' a escolha pelo
        #      criterio DECLARADO; `ttl8` seria a escolha por liquido.
        janela_rompimento=10, alvo_vol=7.6, stop_vol=12.0, trail_vol=None,
        fatiar_saida_alvo=True,
        vol_min_ticks=8.0, fracao_entrada=1.0, aquecimento_barras=45,
        max_entradas_dia=10, entrada_maker=True, entrada_ttl_barras=5,
        # Teto OFICIAL da Copa 2025 (`run_copa_score.TETO_OFICIAL["WIN@"]`) —
        # regulamento, nunca medida; só entra como CEILING porque
        # `margin_per_contract_brl` abaixo já limita a entrada pelo caixa
        # real antes de chegar perto dele.
        teto_contratos=15,
        # Ativa a realocação por capital (ver a docstring da seção "Realocação
        # dinâmica por CAPITAL" em `copa_win.py`): sem isto o robô sempre
        # pediria `teto_contratos x fracao_entrada` contratos, ignorando o
        # caixa — os outros 3 robôs do pódio já escalam pelo caixa real
        # internamente, e o painel expõe robôs prontos pra dinheiro real, não
        # só pra competição. R$100 é a margem do WIN@ em
        # `core.instruments.FUTUROS["WIN@"]` (fonte da verdade desde
        # 2026-09-09; antes vinha redigitada aqui -- não confundir com o
        # WDO@, que é R$150; a tabela de capital mínimo do `CLAUDE.md` tinha
        # os dois trocados até 2026-08-28).
        # `MARGIN_BUFFER_FUTUROS` já é o default do robô. Com o caixa mínimo
        # real do WIN (R$200 = 2 lotes de margem), isto reproduz exatamente 1
        # contrato — o tamanho com que a calibração acima foi medida e
        # confirmada em OOS.
        margin_per_contract_brl=economics_for("WIN@").margin_per_contract_brl,
        # 2026-08-29, item 3.9 de LICOES_DE_PRODUCAO.md: o teto por CAPITAL
        # acima limita ALAVANCAGEM, não RISCO — medido com R$3.000 reais nos
        # 182 pregões salvos de WIN@, um dia bom escalou a entrada de 12 pra
        # 15 contratos, e o MESMO stop de sempre (agora sobre mais contratos)
        # perdeu R$3.457,50 num trade só: R$3.000,00 → R$68,50 (-97,7%), sem
        # nunca ficar negativa, quase zerando com margem/reserva funcionando
        # exatamente como desenhadas. `risco_pct_por_trade` é o SEGUNDO teto,
        # independente — a entrada usa o MENOR entre os dois (ver a docstring
        # de `CopaWin.__init__`). 5% É PROVISÓRIO: testado 2%-10% no mesmo
        # histórico (todos terminaram positivos, nenhum chegou perto de
        # zerar — ver `scripts/daytrade/copawin_dimensionamento_por_risco_
        # 2026_08_29.py`), mas nenhum valor específico passou por uma
        # varredura própria nem por confirmação OOS ainda.
        risco_pct_por_trade=0.05,
        # 2026-09-03, pedido do dono: liga os DOIS mecanismos de saída
        # antecipada testados nesta rodada (`scripts/daytrade/copawin_
        # corte_persistencia_sweep_2026_09_03.py`, seção `--bonus`) —
        # combinados, IS R$7.076,40 -> R$11.236,50 (+58,8%), OOS R$3.426,00
        # -> R$4.014,50 (+17,2%), no histórico completo de WIN@ com
        # R$3.000 de capital (o nível "de folga" onde o robô não trava por
        # caixa — ver a memória `copawin-e-gremah-piso-capital-2026-08-29`;
        # com o capital REAL do slot, R$434, o OOS tem 1 trade só e não da'
        # pra confirmar nada).
        # RESSALVA que fica registrada aqui por não ter sido resolvida antes
        # de ligar (decisão explícita do dono, ver LICOES_DE_PRODUCAO.md se
        # quiser o item completo): a janela OOS do WIN@ (>=2026-06-13) já
        # tinha sido usada uma vez antes pra confirmar `alvo_vol`/`stop_vol`
        # acima (2026-08-28) — não é mais um teste cego de verdade pra esta
        # estratégia, então o "+17,2% no OOS" acima e' evidência mais fraca
        # do que um OOS nunca visto. Também NÃO e' o candidato mais ROBUSTO
        # medido (esse seria `corte_persistencia_min_barras=20,
        # corte_persistencia_frac_adverso=0.6` sozinho, que melhora IS e OOS
        # de forma mais equilibrada e sem a ressalva de fragilidade vista em
        # `frac_adverso` 70%-80%) — o combo abaixo foi o que o dono pediu
        # explicitamente depois de ver os dois números lado a lado.
        corte_persistencia_ativo=True,
        corte_persistencia_min_barras=10,
        corte_persistencia_frac_adverso=1.0,
        defesa_ativa=True,
        defesa_gatilho_stop_pct=0.20,
        defesa_alvo_proximidade_pct=0.10,
    ),
}


@dataclass(frozen=True)
class DaytradeRobotInfo:
    """Metadata de exibição de um robô de day trade — para o select do
    painel, sem precisar do terminal MT5 nem de conta criada."""

    key: str
    label: str
    symbol: str
    version: str
    description: str
    #: Posição no pódio declarado (1 = TOP-1). Sai da ordem de `_ROBOTS`, e
    #: existe como CAMPO para o painel poder rotular a escolha — antes a ordem
    #: só existia implícita na lista, e uma ordem que ninguém enxerga não é
    #: uma recomendação, é um acaso de iteração.
    rank: int = 1
    #: `"m1"` ou `"tick"` — a granularidade em que este robô foi medido (ver
    #: `IntradayStrategy.feed_kind`). No painel é o que distingue dois robôs
    #: do mesmo desenho.
    feed_kind: str = "m1"
    #: Ver `IntradayStrategy.is_futuro`. Sai daqui (não de instanciar a
    #: classe de novo) para `dashboard/app.py` poder decidir a fórmula de
    #: capital mínimo (lote de ação x margem por contrato) sem importar a
    #: classe do robô.
    is_futuro: bool = False


def _description(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return f"Robô {cls.__name__} (sem docstring)."
    primeira = doc.strip().splitlines()[0].strip(" .")
    return primeira + "."


def list_daytrade_robots() -> list[DaytradeRobotInfo]:
    """Um `DaytradeRobotInfo` por robô registrado, na ordem do PÓDIO (TOP-1
    primeiro) — ver o comentário sobre `_ROBOTS` no topo do módulo.

    Instancia com os defaults de cada classe (mais `_KWARGS_PADRAO`, para quem
    exige parâmetro sem default) só para ler `.symbol` — leitura pura, sem
    I/O (mesmo espírito de `strategy.registry.list_strategies`)."""
    infos = []
    for posicao, (key, cls) in enumerate(_ROBOTS.items(), start=1):
        robo = cls(**_KWARGS_PADRAO.get(key, {}))
        infos.append(DaytradeRobotInfo(
            key=key, label=key, symbol=robo.symbol,
            version=getattr(robo, "version", "0.1"),
            description=_description(cls),
            rank=posicao,
            feed_kind=getattr(cls, "feed_kind", "m1"),
            is_futuro=getattr(cls, "is_futuro", False),
        ))
    return infos


def daytrade_robot_class(key: str) -> type[IntradayStrategy]:
    """A CLASSE do robô, sem instanciar nada.

    Existe para quem precisa só de um atributo DECLARADO na classe (hoje:
    `capital_minimo_recomendado_brl`, lido pelo painel em
    `dashboard.robot_view.capital_minimo_para`) sem pagar o preço de
    construir o robô -- e sem o risco de a construção falhar por um motivo
    que nada tem a ver com a pergunta feita (`Gremah.__init__` recusa símbolo
    sem calibração; `CopaWin.__init__` recusa combinações de execução
    inválidas). Perguntar "qual o piso de caixa deste robô?" não deve
    depender de o robô ser construtível com os kwargs daquele contexto.

    `KeyError` para chave desconhecida, mesma disciplina de
    `get_daytrade_robot` -- nunca um default silencioso.

    Não devolve `_ROBOTS` nem uma cópia dele de propósito: o catálogo
    continua fechado, e o acesso é sempre por chave declarada."""
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    return _ROBOTS[key]


def get_daytrade_robot(key: str, symbol: str | None = None) -> IntradayStrategy:
    """Resolve um robô de day trade por chave, com os PARÂMETROS DEFAULT da
    classe — quem precisa de parâmetros diferentes instancia direto.

    `symbol` escolhe o ativo. `None` usa o default da classe. Passar um ativo
    que o robô não aceita é erro DELE, não daqui: `Gremah.__init__` levanta
    `ValueError` para símbolo sem calibração própria, em vez de herdar a
    calibração de outro papel — é esse comportamento que impede o painel de
    ligar um robô num ativo nunca medido.

    Este parâmetro entrou em 2026-08-22, quando o painel passou a abrir N
    robôs de day trade (um por ativo): até então "o robô" e "o ativo" eram a
    mesma escolha, porque o registry só sabia instanciar com o default.

    `KeyError` (nunca um default silencioso) se a chave não existir: um id
    desconhecido chegando de form/CLI é catálogo desatualizado ou form
    adulterado, e escolher um robô por chute operaria dinheiro real com o
    robô errado."""
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    kwargs = dict(_KWARGS_PADRAO.get(key, {}))
    if symbol is not None:
        kwargs["symbol"] = symbol
    return cls(**kwargs)


def symbols_for_robot(key: str) -> tuple[str, ...]:
    """Ativos que este robô aceita operar, na ordem em que ele os declara.

    Sai de `calibrated_setups()` na CLASSE quando ela oferece esse método (é o
    caso da `gremah`: cada ativo tem alvo/stop medidos separadamente, e a
    ordem é lucro OOS decrescente). Um robô de ativo único simplesmente não
    define o método, e aqui ele vira a tupla de um elemento com o símbolo
    default — o painel não precisa saber qual dos dois casos é.

    Ordenar por capital mínimo é do CHAMADOR, não daqui: depende do preço de
    hoje, e `strategy/` não busca preço (regra 1 do AGENTS.md).
    """
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    setups = getattr(cls, "calibrated_setups", None)
    if callable(setups):
        return tuple(s.symbol for s in setups())
    return (cls(**_KWARGS_PADRAO.get(key, {})).symbol,)
