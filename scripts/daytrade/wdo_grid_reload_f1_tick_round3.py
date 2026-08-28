"""Frente F1-wdo-consolidacao, RODADA 3 -- fecha a bateria pendente sobre a
leitura TICK do candidato "T1 S16 x1".

`wdo_grid_reload_f1_tick_lab.py` (escrito numa passada anterior desta mesma
frente) ja tinha os itens 2/3/4 da bateria (teste de metade, nulo sign-flip,
curva de pedagio) implementados, mas a execucao foi lancada em background e
MORTA antes de terminar (motor puro-Python marcando patrimonio por TICK,
~2,8 milhoes de pontos em 72 pregoes) -- nenhum numero real chegou a sair
dali. Este arquivo:

  1. IMPORTA (nao reescreve) as funcoes ja prontas de `wdo_grid_reload_f1_
     tick_lab.py` e efetivamente RODA a bateria completa ate' o fim, uma
     unica vez, reaproveitando o MESMO `tick_bars` buscado (custo de fetch
     no MT5 e' local e rapido -- ~2,8M ticks em segundos; o custo caro e' o
     motor, entao cada corrida completa do motor e' evitada quando possivel).
  2. ADICIONA o item pendente da missao desta rodada que nao existia em
     nenhum arquivo anterior desta frente: checagem EXPLICITA do artefato
     de bonus de preco no fill de ALVO (`_exit_fill_price`, `machine.py`
     linhas 407-417) que matou F3 em M1 -- mede o tamanho do bonus isolado
     em leitura TICK, com e sem, mesmo metodo de F3 (roda com e sem,
     compara o liquido).

NAO EDITA `machine.py` -- so' MONKEYPATCHA a funcao module-level em tempo de
execucao (`backtest.intraday.machine._exit_fill_price`), sempre restaurada
no `finally`. `_exit_fill_price` e' chamada como nome NU dentro do proprio
`machine.py` (`ref_price = _exit_fill_price(pos, bar, "stop")`, no' de
resolucao global do modulo, nao um atributo de instancia) -- troca de
atributo do modulo muda o comportamento de TODA chamada interna sem tocar
uma linha do arquivo. Restaurado sempre via `try/finally`, inclusive se o
motor lancar excecao no meio.

Uso: `python -u scripts/daytrade/wdo_grid_reload_f1_tick_round3.py`
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

import backtest.intraday.machine as machine_mod  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from wdo_grid_reload_f1_lab import CAPITAL_NOCIONAL, montar_config, rodar  # noqa: E402
from wdo_grid_reload_f1_tick_lab import (  # noqa: E402
    BALLPARK_POR_PREGAO_BRL,
    carregar_tick_bars,
    curva_de_pedagio,
    nulo_sign_flip,
    teste_de_metade,
    validar_projecao,
)

# Referencia ORIGINAL da funcao de fill de saida, capturada ANTES de
# qualquer monkeypatch -- e' o que `_exit_fill_price_com_log` chama por
# baixo (comportamento IDENTICO ao motor real) e o que o `finally` restaura.
_ORIGINAL_EXIT_FILL_PRICE = machine_mod._exit_fill_price

# Acumulador do bonus medido durante a run INSTRUMENTADA (item 3) -- uma
# entrada por chamada de `_exit_fill_price` com `kind == "target"`, o UNICO
# lado onde a formula da' preco MELHOR que o nivel (`max`/`min` na direcao
# favoravel -- ver `machine.py:407-417`; o lado `stop` e' o pior caso,
# conservador, nao e' o artefato sob teste aqui, mesmo recorte que F3 usou).
_bonus_log: list[dict] = []


def _exit_fill_price_com_log(pos, bar, kind):
    """Wrapper de DIAGNOSTICO -- devolve EXATAMENTE o mesmo preco que
    `_exit_fill_price` original devolveria (comportamento do motor
    inalterado), so' que registra o tamanho do bonus de alvo em
    `_bonus_log` no caminho. Usado na run 'com bonus' (a headline de
    verdade) para nao precisar de uma run extra so' para medir."""
    preco = _ORIGINAL_EXIT_FILL_PRICE(pos, bar, kind)
    if kind == "target":
        level = pos.current_target
        bonus_pts = (preco - level) if pos.side == "long" else (level - preco)
        _bonus_log.append({"side": pos.side, "level": level, "bar_open": bar.open,
                            "fill": preco, "bonus_pts": bonus_pts})
    return preco


def _exit_fill_price_sem_bonus_alvo(pos, bar, kind):
    """Mesma assinatura de `_exit_fill_price` original, com o `max(bar.open,
    level)`/`min(bar.open, level)` do ALVO REMOVIDO -- fill do alvo sempre
    EXATAMENTE no nivel, nunca melhor (a leitura CONSERVADORA que F3 usou
    para isolar o artefato em M1). O lado STOP fica byte-a-byte igual ao
    original (pior caso, `min`/`max` na direcao desfavoravel) -- nao e' o
    artefato sob teste, remove-lo so' adicionaria ruido a comparacao."""
    if kind == "target":
        return pos.current_target
    return _ORIGINAL_EXIT_FILL_PRICE(pos, bar, kind)


def item1_headline_instrumentada(tick_bars: pd.DataFrame, n_pregoes: int):
    """Item 1 da bateria (headline) + captura dos dados de bonus no MESMO
    passe -- resultado IDENTICO ao headline puro (o wrapper so' loga, nunca
    muda o preco devolvido), entao serve tanto de headline oficial quanto de
    fonte de dado para o item extra (3b, bonus)."""
    print(f"\n=== 1. headline (leitura tick, {n_pregoes} pregoes disponiveis de 123 IS, "
          f"INSTRUMENTADA p/ log de bonus -- resultado identico ao motor original) ===")
    cfg = montar_config()
    machine_mod._exit_fill_price = _exit_fill_price_com_log
    try:
        t0 = time.time()
        resultado = rodar(tick_bars, cfg)
        dt = time.time() - t0
    finally:
        machine_mod._exit_fill_price = _ORIGINAL_EXIT_FILL_PRICE
    print(f"[timing] run headline (instrumentada): {dt:.1f}s para {len(tick_bars)} ticks")
    item = linha_de_resultado(f"wdo_grid_reload T1 S16 x1 (TICK, {n_pregoes}/123 pregoes IS)",
                               resultado, CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item))
    taxa = item.liquido_brl / n_pregoes if n_pregoes else 0.0
    print(f"R$/pregao: {num_br(taxa)}  |  ballpark conhecido (123 pregoes completos): "
          f"{num_br(BALLPARK_POR_PREGAO_BRL)}  |  fracao do ballpark diario: "
          f"{num_br(100.0 * taxa / BALLPARK_POR_PREGAO_BRL, 1)}%")
    return resultado


def item3b_bonus_de_preco_no_alvo(tick_bars: pd.DataFrame, headline_result, n_pregoes: int) -> None:
    """Item extra desta rodada (pendente na missao): confirma/mede o
    artefato de `_exit_fill_price` equivalente ao que matou F3 em M1, na
    leitura TICK. Duas evidencias, as DUAS reportadas:

    (a) distribuicao do bonus por trade, medida na propria run headline
        (sem custo extra de motor -- ja veio do log da run instrumentada);
    (b) rerun COMPLETO do motor com o bonus de alvo REMOVIDO
        (`_exit_fill_price_sem_bonus_alvo`), liquido comparado lado a lado
        com o headline -- mesmo metodo de isolamento que F3 usou em M1
        ("rodar com e sem o bonus, comparar")."""
    print("\n=== 3b. artefato de bonus de preco no fill do ALVO "
          "(`_exit_fill_price`, machine.py:407-417) -- leitura TICK ===")
    print("evidencia de codigo: `_exit_fill_price` e' a MESMA funcao (mesmo modulo, mesmo\n"
          "arquivo `backtest/intraday/machine.py`) usada pelo motor tanto em M1 quanto em\n"
          "TICK -- o motor (`engine.py::run_intraday_backtest`) e' identico nos dois casos,\n"
          "so' o QUE se passa para `bars` muda (M1 real vs 1-tick-por-linha, ver\n"
          "`wdo_grid_reload_f1_tick_probe.py::buscar_ticks`, que monta cada 'barra' com\n"
          "`open=high=low=close=df['last']`, o preco do NEGOCIO individual).")

    if not _bonus_log:
        print("[AVISO] log de bonus vazio -- nenhum trade fechou por ALVO na run headline "
              "(nao deveria acontecer com win rate ~99%, mas reportado por honestidade).")
    else:
        bonus_arr = np.array([b["bonus_pts"] for b in _bonus_log])
        n_com_bonus = int((bonus_arr > 1e-9).sum())
        print(f"trades fechados por ALVO: {len(bonus_arr)} | com bonus > 0: {n_com_bonus} "
              f"({num_br(100.0 * n_com_bonus / len(bonus_arr), 1)}%)")
        print(f"bonus por trade (pontos de indice, ANTES de x point_value_brl): "
              f"media={num_br(float(bonus_arr.mean()), 4)}, "
              f"mediana={num_br(float(np.median(bonus_arr)), 4)}, "
              f"max={num_br(float(bonus_arr.max()), 4)}, "
              f"desvio={num_br(float(bonus_arr.std()), 4)}")
        # POR QUE a granularidade tick nao ZERA o artefato por construcao:
        # cada 'barra' tick e' open==high==low==close (1 negocio so'), entao
        # o bonus so' pode vir de um GAP genuino entre o negocio anterior
        # (fora do nivel) e o negocio que primeiro cruza o nivel -- nao de
        # agregacao de 1 minuto em varios negocios. `tick_size` do WDO@ e'
        # 0,5: um bonus de exatamente 1 tick (0,5 pt) e' o caso ja
        # ESPERADO/estrutural (o negocio que cruza o alvo pula 1 tick em vez
        # de tocar EXATO -- livro discreto), bonus > 1 tick e' o sinal de
        # gap MAIOR (evidencia de mais de 1 nivel pulado num negocio so').
        tick_size = 0.5
        bonus_em_ticks = bonus_arr / tick_size
        maior_que_1_tick = int((bonus_em_ticks > 1.0 + 1e-9).sum())
        print(f"bonus em TICKS (0,5pt): media={num_br(float(bonus_em_ticks.mean()), 3)} tick, "
              f"mediana={num_br(float(np.median(bonus_em_ticks)), 3)} tick, "
              f"max={num_br(float(bonus_em_ticks.max()), 2)} tick | "
              f"trades com bonus > 1 tick: {maior_que_1_tick} "
              f"({num_br(100.0 * maior_que_1_tick / len(bonus_arr), 2)}%)")
        point_value_brl = montar_config().costs.point_value_brl
        bonus_total_brl = float(bonus_arr.sum()) * point_value_brl
        print(f"bonus TOTAL acumulado no liquido reportado (item 1): "
              f"R${num_br(bonus_total_brl)} (point_value_brl={num_br(point_value_brl)})")

    # (b) rerun completo SEM o bonus de alvo -- comparacao liquido-a-liquido.
    print("\n--- rerun completo com o bonus de ALVO removido (mesmo metodo de isolamento do F3) ---")
    cfg = montar_config()
    machine_mod._exit_fill_price = _exit_fill_price_sem_bonus_alvo
    try:
        t0 = time.time()
        resultado_sem_bonus = rodar(tick_bars, cfg)
        dt = time.time() - t0
    finally:
        machine_mod._exit_fill_price = _ORIGINAL_EXIT_FILL_PRICE
    print(f"[timing] run sem-bonus: {dt:.1f}s")

    item_com = linha_de_resultado(f"COM bonus de alvo (headline, {n_pregoes} pregoes)",
                                   headline_result, CAPITAL_NOCIONAL, capital_nocional=True)
    item_sem = linha_de_resultado(f"SEM bonus de alvo ({n_pregoes} pregoes)",
                                   resultado_sem_bonus, CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item_com))
    print(linha(item_sem))
    taxa_com = item_com.liquido_brl / n_pregoes if n_pregoes else 0.0
    taxa_sem = item_sem.liquido_brl / n_pregoes if n_pregoes else 0.0
    print(f"R$/pregao -- COM bonus: {num_br(taxa_com)}  |  SEM bonus: {num_br(taxa_sem)}  |  "
          f"diferenca: {num_br(taxa_com - taxa_sem)}/pregao "
          f"({num_br(100.0 * (taxa_com - taxa_sem) / abs(taxa_com), 1) if taxa_com else '—'}% do liquido com bonus)")
    print(f"trades -- COM: {len(headline_result.trades)}  |  SEM: {len(resultado_sem_bonus.trades)} "
          f"(deveria ser IGUAL -- a sequencia de decisao nao muda so' de trocar o PRECO do fill; "
          f"se diferente, e' sinal de bug no monkeypatch: {'OK, igual' if len(headline_result.trades) == len(resultado_sem_bonus.trades) else 'DIVERGIU -- investigar'})")
    print(f"liquido sem bonus ainda positivo? {item_sem.liquido_brl > 0}")


def main() -> None:
    dias, tick_bars = carregar_tick_bars()
    n_pregoes = len(dias)

    headline = item1_headline_instrumentada(tick_bars, n_pregoes)

    teste_de_metade(dias, tick_bars)
    nulo_sign_flip(list(headline.trades))
    ok = validar_projecao(tick_bars, headline)
    curva_de_pedagio(headline, valida=ok)

    item3b_bonus_de_preco_no_alvo(tick_bars, headline, n_pregoes)

    print("\n=== 5. tabela padrao (linha unica, candidato completo, leitura tick, config padrao) ===")
    item = linha_de_resultado(f"wdo_grid_reload T1 S16 x1 (TICK, {n_pregoes}/123 pregoes IS)",
                               headline, CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item))


if __name__ == "__main__":
    main()
