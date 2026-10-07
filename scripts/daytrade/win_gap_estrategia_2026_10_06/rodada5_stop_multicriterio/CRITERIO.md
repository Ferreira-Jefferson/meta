# Criterio de escolha do stop (WinGapBarra1) - escrito ANTES de calcular o ranking

Convencao: replay da pagina (port_win_gap_barra1.py), 1 contrato, R$1.000 inicial, R$2 por operacao, sem alvo.
Stops candidatos: 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500 pontos.
Janelas de selecao (5): 2022, 2023, 2024, 2025 (jan-set), cada uma recomecando em R$1.000; e 2026-01-02..2026-10-05 como conta continua.
Holdout (NAO tocado na selecao): 2025-10-01..2025-12-31.

Metricas por janela: operacoes liquidas do custo; saldo apos cada operacao fechada; "quebrou" = saldo <= 0 (a conta para ali, operacoes seguintes descartadas).
MaxDD = maior queda pico->vale da curva de saldo (pico inicial R$1.000), em R$ e em % do pico. Fator de recuperacao = liquido / MaxDD R$.

1. Eliminatorio: o stop nao pode quebrar a conta de R$1.000 em nenhuma das 5 janelas. Stop eliminado nao pode ser escolhido.
2. Pontuacao: cada metrica gera um ranking entre os 10 stops (1 = melhor, empates = posto medio); o score do stop e' a media ponderada dos postos:
   - fator de recuperacao, peso 2 (dividido em duas metricas de peso 1: liquido somado das 5 janelas / maior MaxDD R$ entre as janelas; e mediana dos fatores de recuperacao das 5 janelas);
   - profit factor agregado (soma dos ganhos / soma das perdas nas 5 janelas), peso 1;
   - win% agregado, peso 1;
   - numero de janelas positivas (de 5), peso 1 (maior melhor);
   - liquido da pior janela, peso 1 (maior melhor);
   - maximo de perdas consecutivas (maximo entre as janelas), peso 1 (menor melhor);
   - pior MaxDD % entre as janelas, peso 1 (menor melhor).
   Soma dos pesos = 8.
3. Suavizacao de plato: score final = media do score do stop e dos scores dos vizinhos imediatos (+-1 na lista de 10 stops; as pontas usam o unico vizinho). Escolhe-se o menor score final (melhor).
4. Desempate: o menor stop (menos risco por operacao).
Observacao de implementacao: os postos sao calculados entre os 10 stops (inclusive os eliminados, para mostrar onde 700 e 1200 caem); a suavizacao usa os vizinhos da lista original; o eliminatorio so' impede a escolha.
