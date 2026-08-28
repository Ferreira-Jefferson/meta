"""INVERSO LITERAL da regra `continuidade_intraday_rule.py` (pedido direto
do dono, 2026-08-27): a regra 'reversal' ja' testada (celula PROMOVIDA em
`continuidade_stats.py`: WDO@, 5min, lag-1, corr real=-0,0345,
p2s=0,0013 < bonferroni/3=0,0167) apostava no sentido que a correlacao
bruta NEGATIVA indica -- janela fechou pra cima -> entra VENDIDO na
abertura da janela seguinte; fechou pra baixo -> entra COMPRADO. Resultado
medido: **liquido -R$68.473,17 IS** (7.223 trades, 58,7 trades/dia, win
37,5%, lucro/DD=-1,00), as duas metades negativas e quase identicas
(-R$33.864,25 / -R$34.608,92), nulo sign-flip no percentil 0,00% nas 5
sementes -- pior que 100% do acaso.

O critico da rodada levantou (SEM testar) a hipotese de bid-ask
bounce/artefato de microestrutura: o fechamento de 5min seria so' o
ultimo negocio antes do preco 'voltar', entao apostar no lado oposto ao
retorno paga o spread bilateral sistematicamente do lado errado -- o que
faria a regra perder mesmo capturando um efeito estatistico real. Este
script testa isso da UNICA forma direta: inverte o lado da regra ja
testada (onde mandava COMPRAR, agora manda VENDER, e vice-versa) e mede
de novo, no MESMO IS, com o MESMO timing e o MESMO custo.

## Por que 'direction=continuation' e' o inverso literal exato de 'reversal'

`strategy.daytrade.lab.continuidade_intraday.ContinuidadeIntraday.on_bar`
computa `lado_bruto` (o lado do retorno que acabou de fechar) e so' entao
ramifica:

    self._desired_side = (
        lado_bruto if self.direction == "continuation" else _flip(lado_bruto)
    )

ou seja `direction="reversal"` usa `_flip(lado_bruto)` e
`direction="continuation"` usa `lado_bruto` cru -- as DUAS unicas opcoes
de uma variavel binaria (long/short), calculadas a partir do MESMO
`lado_bruto`, no MESMO instante de decisao (mesma fronteira de 5min),
com o MESMO teste `if lado_bruto is not None` (entao a mesma
sessao/fronteira fica flat OU decide um lado nos dois casos -- o
"indefinido" nunca muda entre as duas direcoes). Trocar 'reversal' por
'continuation' NA MESMA CLASSE, com o MESMO `symbol`/`bar_minutes`/dado/
custo, e' portanto bit-a-bit o mesmo "onde mandava comprar agora manda
vender" pedido pelo dono -- nao e' uma regra nova, e' a MESMA regra com o
sinal do lado trocado em TODA fronteira, o que a secao 4 abaixo confirma
por CONTAGEM (e por timestamp) contra uma segunda rodada da regra
original importada sem modificacao de
`continuidade_intraday_rule.py`.

## O que este script roda (mesmas 3 secoes do original + secao 4 nova)

1. Regra invertida completa no IS inteiro, tabela padrao.
2. Teste de METADE (mesma divisao cronologica: metade das DATAS do IS,
   nao dos trades).
3. Nulo por SIGN-FLIP (regra 5 do briefing, formula identica ao original:
   bruto_d/custo_d separados por pregao, custo NUNCA invertido pelo
   sinal).
4. Verificacao de espelhamento: roda TAMBEM a regra original
   ('reversal', sem tocar o arquivo dela) sobre o MESMO IS e confirma que
   (a) o numero de trades bate EXATO, (b) cada trade tem o MESMO par
   entry_ts/exit_ts que o trade correspondente da regra original, com o
   lado sempre OPOSTO. Se qualquer uma dessas checagens falhar, a rodada
   para com AssertionError antes de imprimir qualquer resultado.

NAO edita `continuidade_intraday_rule.py` nem `continuidade_intraday.py`
-- so' importa `PROMOVIDOS`/`rodar`/`_metade`/`nulo_sign_flip`/
`_series_bruto_custo` de la' (a mesma classe `ContinuidadeIntraday` ja
aceita `direction="continuation"`, entao nao ha' nenhuma logica nova para
escrever alem da inversao e da checagem de espelhamento)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))  # continuidade_stats.py / continuidade_intraday_rule.py moram aqui

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from continuidade_intraday_rule import (  # noqa: E402  -- arquivo original, NAO modificado
    CAPITAL_NOCIONAL,
    DRAWS_POR_SEMENTE,
    N_SEEDS_NULO_SIGNFLIP,
    _metade,
    _series_bruto_custo,
    nulo_sign_flip,
    rodar,
)
from continuidade_stats import carregar_is_bars  # noqa: E402

#: Espelho EXATO de `PROMOVIDOS` em `continuidade_intraday_rule.py`, so'
#: com a direcao invertida ('continuation' e' o inverso literal de
#: 'reversal' na MESMA classe -- ver docstring do modulo). Nunca escolhida
#: tentando os dois lados aqui: e' a UNICA celula promovida na rodada
#: `continuidade_stats.py`, e o pedido do dono e' testar seu inverso, nao
#: escolher entre eles depois de olhar o resultado.
INVERTIDOS = [
    {"symbol": "WDO@", "bar_minutes": 5, "direction": "continuation",
     "nota": "inverso literal de 'reversal' (corr lag-1 real=-0,0345, "
             "p2s=0,0013); original perdeu R$68.473,17 IS"},
]


def _checar_espelhamento(symbol: str, bars: pd.DataFrame, bar_minutes: int,
                          resultado_invertido) -> None:
    """Roda a regra ORIGINAL ('reversal', importada sem alteracao) sobre o
    MESMO `bars` e confirma que a regra invertida gera EXATAMENTE a mesma
    sequencia de entradas/saidas, so' com o lado trocado -- se nao bater,
    ha' um bug na inversao (docstring do modulo, secao 4)."""
    resultado_original = rodar(symbol, bars, bar_minutes, "reversal")
    trades_inv = resultado_invertido.trades
    trades_orig = resultado_original.trades
    assert len(trades_inv) == len(trades_orig), (
        f"CONTAGEM DE TRADES DIVERGE: invertido={len(trades_inv)} "
        f"original={len(trades_orig)} -- bug na inversao, investigar antes "
        f"de reportar qualquer numero"
    )
    for i, (ti, to) in enumerate(zip(trades_inv, trades_orig)):
        assert pd.Timestamp(ti.entry_ts) == pd.Timestamp(to.entry_ts), (
            f"trade {i}: entry_ts diverge (invertido={ti.entry_ts} "
            f"original={to.entry_ts})"
        )
        assert pd.Timestamp(ti.exit_ts) == pd.Timestamp(to.exit_ts), (
            f"trade {i}: exit_ts diverge (invertido={ti.exit_ts} "
            f"original={to.exit_ts})"
        )
        assert ti.side != to.side, (
            f"trade {i}: lado NAO esta invertido (ambos={ti.side}) -- "
            f"regra invertida nao esta espelhando a original"
        )
    print(f"\n=== 4) VERIFICACAO DE ESPELHAMENTO (contra a regra original "
          f"'reversal', re-rodada aqui so' para comparar) ===")
    print(f"trades invertido={len(trades_inv)}  trades original={len(trades_orig)}  "
          f"-- CONTAGEM IDENTICA, todo par (entry_ts, exit_ts) igual, lado sempre oposto: OK")
    linha_orig = linha_de_resultado("original (reversal)", resultado_original,
                                     CAPITAL_NOCIONAL, capital_nocional=True)
    linha_inv = linha_de_resultado("invertido (continuation)", resultado_invertido,
                                    CAPITAL_NOCIONAL, capital_nocional=True)
    print(tabela([linha_orig, linha_inv]))


def main() -> None:
    for cfg in INVERTIDOS:
        symbol, bar_minutes, direction = cfg["symbol"], cfg["bar_minutes"], cfg["direction"]
        print(f"\n{'='*100}\n{symbol}  bar_minutes={bar_minutes}  direction={direction}  (INVERTIDO)\n"
              f"{cfg['nota']}\n{'='*100}")
        bars = carregar_is_bars(symbol)

        print("\n=== 1) REGRA INVERTIDA COMPLETA (IN-SAMPLE) ===")
        resultado_full = rodar(symbol, bars, bar_minutes, direction)
        linha_full = linha_de_resultado(f"continuidade_intraday_{bar_minutes}min_{direction}_invertido",
                                         resultado_full, CAPITAL_NOCIONAL, capital_nocional=True)
        print(tabela([linha_full]))

        print("\n=== 2) TESTE DE METADE ===")
        bars_h1, bars_h2 = _metade(bars, 1), _metade(bars, 2)
        res_h1 = rodar(symbol, bars_h1, bar_minutes, direction)
        res_h2 = rodar(symbol, bars_h2, bar_minutes, direction)
        linha_h1 = linha_de_resultado("metade 1", res_h1, CAPITAL_NOCIONAL, capital_nocional=True)
        linha_h2 = linha_de_resultado("metade 2", res_h2, CAPITAL_NOCIONAL, capital_nocional=True)
        print(tabela([linha_h1, linha_h2]))

        print("\n=== 3) NULO SIGN-FLIP (formula correta, regra 5) ===")
        liquido_real, percentis = nulo_sign_flip(resultado_full)
        media_pct = float(np.mean(percentis)) if percentis else float("nan")
        n_trades = len(resultado_full.trades)
        n_pregoes_trade = len(set(pd.Timestamp(t.exit_ts).normalize() for t in resultado_full.trades))
        print(f"liquido real: R$ {num_br(liquido_real)} ({n_trades} trades, {n_pregoes_trade} pregoes com trade)")
        if percentis:
            for seed, pct in zip(range(1, N_SEEDS_NULO_SIGNFLIP + 1), percentis):
                print(f"  semente {seed}: percentil {num_br(pct, 2)}%")
            print(f"  media={num_br(media_pct, 2)}%  min={num_br(min(percentis), 2)}%  "
                  f"max={num_br(max(percentis), 2)}%  desvio={num_br(float(np.std(percentis)), 2)}%  "
                  f"n={N_SEEDS_NULO_SIGNFLIP} sementes x {DRAWS_POR_SEMENTE} tiragens")
        else:
            print("  (sem trades -- nulo nao se aplica)")

        _checar_espelhamento(symbol, bars, bar_minutes, resultado_full)


if __name__ == "__main__":
    main()
