# decisoes_dia — base de decisões do WIN em código

Pedido do dono, 2026-10-09: para cada pregão sorteado, 5 maneiras de ganhar (FAZER) e 5 de perder (NAO_FAZER), todas em código (`regras/r_<dia>.py`), analisadas dia a dia, ponto a ponto, só com o passado de cada instante. Depois as regras de todos os dias são testadas juntas em dias novos.

- `base.py`: dados por pregão, contexto sem look-ahead, simulador (limitada, stop a mercado, alvo limitado, custo 10 pts).
- `sorteio.py` / `dias.json`: os 10 dias (IS, seed 20261009).
- `INSTRUCOES.md`: protocolo de cada análise.

**Dados reservados — NÃO usar em estudo nem em teste intermediário:** os últimos 6 meses (abr/2026–out/2026) ficam guardados só para a confirmação FINAL (ordem do dono, 2026-10-09). Testes intermediários usam o restante do OOS (out/2025–mar/2026) e o IS.
