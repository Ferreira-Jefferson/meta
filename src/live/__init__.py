"""Camada de operacao ao vivo — o ambiente que acopla os robos ao mercado real.

Tres pecas, fronteira explicita:

    ambiente (aqui)      relogio de pregao, dado fresco, estado real da conta,
                         ciclo de vida de ordem, persistencia, supervisao.
    robo de investimento `strategy/` — decide comprar/vender/mover stop.
    robo de saque        `backtest/withdrawal.py` — decide quanto retirar.

Os dois robos sao os MESMOS objetos que o backtest usa. Ver
`core/live_models.py` para o contrato e o porque.
"""
