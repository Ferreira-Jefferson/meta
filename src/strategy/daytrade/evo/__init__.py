"""Pecas PURAS do robo evoluido: banco de features, genoma e politica.

Tudo aqui e' `OHLCV que ja fechou -> numeros`, sem I/O, sem banco, sem
relogio de parede e sem olhar uma barra que o robo ainda nao teria visto ao
vivo. A razao e' a de sempre (AGENTS.md): a logica de sinal vai ser portada
para MQL5, e o que nao for puro nao viaja.

Aqui a pureza tem uma segunda funcao, que e' o motivo deste subpacote
existir separado do robo: **uma busca evolutiva encontra qualquer folga de
causalidade que sobrar**. Se uma feature pudesse espiar uma barra adiante, a
evolucao nao "cometeria o erro" -- ela CONVERGIRIA para o erro, porque olhar
o futuro e' a melhor estrategia que existe. Por isso o banco de features nao
tem acesso ao DataFrame completo: ele so' recebe barra por barra, na ordem,
pelo mesmo caminho que o robo ao vivo recebe do feed.
"""
