"""Confirmacao OOS da `CopaWin` (WIN@) -- 2026-08-27, decisao EXPLICITA do dono
de INCLUIR esta celula de novo, apesar da refutacao anterior registrada em
`copa_rompimento_oos_refutado_2026_08_26` (mesma calibracao IS, mesmo motivo
de refutacao: OOS positivo mas abaixo de 1x Danillo e negativo com 1 tick de
pedagio G7).

## Por que rodar de novo

O dono afirma que aquele teste simulava algo que NAO acontece no MetaTrader
real (nao especificou o que). Este script NAO tenta decidir se isso e'
verdade -- so' roda o CODIGO ATUAL do repo (2026-08-27) contra o mesmo OOS e
reporta os numeros crus, mais o MODELO DE CUSTO/PREENCHIMENTO que o motor usa
hoje, para o dono comparar com o que ele sabe do MT5 real.

Conferido ANTES de rodar (ver diff `git diff` de 2026-08-27 em `base.py`,
`profiles.py`, `copa_win.py`): as mudancas de hoje sao TODAS aditivas e
opt-in (`margin_per_contract_brl=None` por default preserva o comportamento
byte-a-byte de antes) -- ou seja, se os numeros abaixo divergirem da
refutacao de 08-26, a causa NAO e' mudanca de codigo nesta calibracao
especifica (`margin_per_contract_brl` nunca e' passado aqui).

## Destrava do OOS

`LockedBars.unlock(reason=...)` chamado explicitamente abaixo, com o motivo
documentado -- autorizacao explicita do dono para esta validacao final
(2026-08-27), nao um "so' espiar uma vez" acidental. Ja fora estava
GASTO por `run_copa_score.py --unlock-oos` em 2026-08-26
(`copa_oos_gasto_2026_08_26`) -- este script NAO reabre a trava para
escolher parametro nenhum, so' remede a mesma celula ja escolhida no IS.

Uso: `python -u scripts/daytrade/copa_win_confirmacao_oos_2026_08_27.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402

SYMBOL = "WIN@"
TETO_UNITARIO = 1  # per-contrato: liquido_brl aqui JA' e' liquido por contrato
                     # (P&L e' EXATAMENTE linear na quantidade -- ver copa_lab.py
                     # e a ressalva 1 de CALIBRACAO_IS["WIN@"]).
UNLOCK_REASON = (
    "Validacao final autorizada pelo dono em 2026-08-27 para consolidar "
    "capital/sinal antes de atualizar producao"
)

OUT_JSON = ROOT / "scripts" / "daytrade" / "copa_win_confirmacao_oos_2026_08_27_result.json"


def _pregoes(bars: pd.DataFrame) -> int:
    return len(set(bars.index.date))


def _relatorio_custo(cfg) -> dict:
    c = cfg.costs
    return {
        "fee_round_trip_brl_por_contrato": c.fee_round_trip_brl,
        "exchange_fee_pct_per_leg": c.exchange_fee_pct_per_leg,
        "slippage_ticks": c.slippage_ticks,
        "tick_size": c.tick_size,
        "point_value_brl": c.point_value_brl,
        "target_fills_as_maker": cfg.target_fills_as_maker,
        "limit_fill_capped_by_volume": cfg.limit_fill_capped_by_volume,
        "ambiguous_bar_resolution": cfg.ambiguous_bar_resolution,
        "queue_ahead_qty": cfg.queue_ahead_qty,
        "max_open_contracts": cfg.max_open_contracts,
        "session_end_policy": cfg.session_end_policy,
    }


def main() -> None:
    params = dict(CALIBRACAO_IS[SYMBOL])
    print(f"[confirmacao_oos] parametros CopaWin (CALIBRACAO_IS['{SYMBOL}']): {params}\n")

    # ------------------------------------------------------------------
    # destrava o OOS -- UMA instancia de LockedBars, reusada para is/oos/
    # combinado (cada chamada a `L.barras()` monta uma trava NOVA -- teria
    # que destravar de novo).
    # ------------------------------------------------------------------
    travadas = L.barras(SYMBOL)
    travadas.unlock(UNLOCK_REASON)
    ins = travadas.in_sample()
    oos = travadas.out_of_sample()
    combinado = pd.concat([ins, oos])

    print(f"[confirmacao_oos] IN-SAMPLE:  {L.descreve_janela(ins)}")
    print(f"[confirmacao_oos] OUT-OF-SAMPLE: {L.descreve_janela(oos)}")
    print(f"[confirmacao_oos] COMBINADO (IS+OOS): {L.descreve_janela(combinado)}\n")

    # ------------------------------------------------------------------
    # modelo de custo/preenchimento -- reportado uma vez (mesmo config para
    # todas as rodadas desta calibracao, so' o teto/pedagio mudam).
    # ------------------------------------------------------------------
    instancia_ref = L.robo(SYMBOL, TETO_UNITARIO, **params)
    cfg_ref = L.config(SYMBOL, TETO_UNITARIO, pernas_maker=int(getattr(instancia_ref, "pernas_maker", 1)))
    custo_info = _relatorio_custo(cfg_ref)
    print("[confirmacao_oos] MODELO DE CUSTO/PREENCHIMENTO (motor atual):")
    for k, v in custo_info.items():
        print(f"    {k} = {v}")
    print(f"    pernas_maker desta calibracao (entrada_maker={params['entrada_maker']}) = "
          f"{instancia_ref.pernas_maker} (1 alvo sempre maker; +1 se entrada_maker=True)")
    print()

    # ------------------------------------------------------------------
    # rodadas -- teto=1 contrato (numero direto = R$/contrato), com e sem
    # pedagio G7 de 1 tick por perna maker, nas 3 janelas.
    # ------------------------------------------------------------------
    rodadas = {}
    for rotulo, bars in (("IS", ins), ("OOS", oos), ("IS+OOS combinado", combinado)):
        r_base = L.rodar(SYMBOL, bars, TETO_UNITARIO, f"{rotulo} sem pedagio", **params)
        r_pedagio = L.rodar(SYMBOL, bars, TETO_UNITARIO, f"{rotulo} + pedagio G7 (1 tick/perna maker)",
                             pedagio_ticks=1.0, **params)
        n_preg = _pregoes(bars)
        rodadas[rotulo] = dict(
            pregoes=n_preg,
            trades=len(r_base.resultado.trades),
            liquido_brl=r_base.liquido_brl,
            liquido_por_pregao_brl=r_base.liquido_brl / n_preg if n_preg else float("nan"),
            liquido_brl_com_pedagio=r_pedagio.liquido_brl,
            liquido_por_pregao_brl_com_pedagio=r_pedagio.liquido_brl / n_preg if n_preg else float("nan"),
            recusas_pct=r_base.recusas_pct,
        )

    print("=== RESULTADO -- R$/contrato (teto_contratos=1), motor/custo ATUAIS ===")
    print(f"{'janela':<20}{'pregoes':>9}{'trades':>9}{'liquido R$':>16}{'R$/pregao':>14}"
          f"{'liquido c/ped.':>16}{'R$/pregao c/ped.':>18}")
    print("-" * 102)
    for rotulo, d in rodadas.items():
        print(f"{rotulo:<20}{d['pregoes']:>9}{d['trades']:>9}"
              f"{('R$'+num_br(d['liquido_brl'])):>16}{num_br(d['liquido_por_pregao_brl']):>14}"
              f"{('R$'+num_br(d['liquido_brl_com_pedagio'])):>16}"
              f"{num_br(d['liquido_por_pregao_brl_com_pedagio']):>18}")

    print("\n=== COMPARACAO EXPLICITA contra a memoria `copa_rompimento_oos_refutado_2026_08_26` ===")
    memo_is = 62.24
    memo_oos = 3.84
    atual_is = rodadas["IS"]["liquido_por_pregao_brl"]
    atual_oos = rodadas["OOS"]["liquido_por_pregao_brl"]
    atual_oos_ped = rodadas["OOS"]["liquido_por_pregao_brl_com_pedagio"]
    print(f"IS  memoria (08-26): R$ {num_br(memo_is)}/pregao  | IS  agora (08-27, mesmo codigo aditivo): "
          f"R$ {num_br(atual_is)}/pregao  | delta: R$ {num_br(atual_is - memo_is)}")
    print(f"OOS memoria (08-26): R$ {num_br(memo_oos)}/pregao  | OOS agora (08-27): "
          f"R$ {num_br(atual_oos)}/pregao  | delta: R$ {num_br(atual_oos - memo_oos)}")
    print(f"OOS + pedagio G7 (1 tick/perna maker) agora: R$ {num_br(atual_oos_ped)}/pregao "
          f"({'positivo' if atual_oos_ped > 0 else 'negativo/zero'})")
    print("\nSEM VIES: os numeros acima sao reportados como saem. Ver a secao final da resposta "
          "para a leitura (bate/nao bate) -- este script nao decide isso por conta propria.")

    OUT_JSON.write_text(json.dumps({
        "symbol": SYMBOL, "params": params, "unlock_reason": UNLOCK_REASON,
        "modelo_custo": custo_info,
        "janelas": {
            "IS": L.descreve_janela(ins), "OOS": L.descreve_janela(oos),
            "combinado": L.descreve_janela(combinado),
        },
        "rodadas": rodadas,
        "memoria_2026_08_26": {"is_por_pregao_brl": memo_is, "oos_por_pregao_brl": memo_oos},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[confirmacao_oos] resultado salvo em {OUT_JSON}")


if __name__ == "__main__":
    main()
