# -*- coding: utf-8 -*-
"""PASSO 1 do mandato (G23): valida, de forma simples, se o folego da cesta
de acoes liquidas tem ALGUMA relacao com o desfecho de uma pernada NASCENTE
do WIN -- ANTES de montar qualquer estrategia completa (ORQUESTRACAO.md,
"Fase 3", item 5).

Metodo (post-hoc, estratificacao de trades ja' ocorridos -- mesmo molde
abencoado pelo item 6.50 de LICOES_DE_PRODUCAO.md: UMA UNICA passada sem
filtro, rotula cada evento com a metrica candidata, so' DEPOIS separa em
grupos): para cada combinacao pequena de (`janela_min`, `nascente_pontos`),
percorre o IS (jan-jun/2026) dia a dia (reset por sessao), usa
`RastreadorPernadaNascente` (a MESMA classe que a estrategia real usa em
`on_bar` -- nunca uma segunda implementacao do mesmo zigzag) para achar toda
pernada NASCENTE, mede a concordancia `folego[ts] * direcao_nascente` no
instante do nascimento, e rotula o desfecho: a MESMA perna chegou a
`pernada_pontos=750` (CONFIRMOU) antes de reverter `nascente_pontos` a
partir do extremo provisorio (NAO CONFIRMOU)?

Corta a concordancia em tercis (dentro do IS) e reporta taxa de confirmacao
por tercil -- testa as DUAS leituras do mandato na mesma tabela: tercil alto
(folego concorda fortemente) testa "confirmacao"; tercil baixo/negativo
(folego diverge fortemente) testa se a divergencia prediz FALHA (que also
sustentaria uma aposta de "divergencia" -- entrar CONTRA a pernada nascente).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g23_amplitude_ibov/g23_validacao_causal.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import g23_base as b  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
from strategy.daytrade.lab.win_busca_lucro_g23_amplitude_ibov import (  # noqa: E402
    RastreadorPernadaNascente, PERNADA_PONTOS, _caminho_da_barra,
)

JANELAS_MIN = [5, 15]
NASCENTES_PONTOS = [250.0, 375.0]


def _eventos_nascentes(dias: list, janela_min: int, nascente_pontos: float) -> list[dict]:
    """UMA passada pelo IS (dia a dia, reset por sessao) gerando a lista de
    eventos (ts, direcao, concordancia, confirmou). `folego` e' pre-computado
    UMA VEZ para a janela inteira (CAUSAL -- cada minuto so' usa <= aquele
    minuto, ver `folego_ibov`); a estratificacao por tercil acontece DEPOIS,
    fora desta funcao."""
    win = b.carrega_win()
    folego = b.computa_folego(dias, janela_min=janela_min).to_dict()
    eventos: list[dict] = []
    for dia in dias:
        barras = win[win.index.date == dia]
        if barras.empty:
            continue
        rastreador = RastreadorPernadaNascente(nascente_pontos, PERNADA_PONTOS)
        idx_ativo: int | None = None
        for ts, row in barras.iterrows():
            bar = type("B", (), dict(open=row["open"], high=row["high"],
                                      low=row["low"], close=row["close"]))()
            for p in _caminho_da_barra(bar):
                ev = rastreador.processa(p)
                if ev["novo_nascente"]:
                    direcao = ev["direcao_nascente"]
                    fol = folego.get(ts, float("nan"))
                    eventos.append(dict(ts=ts, direcao=direcao,
                                         concordancia=fol * direcao, confirmou=False))
                    idx_ativo = len(eventos) - 1
                if ev["confirmou_750"] and idx_ativo is not None:
                    eventos[idx_ativo]["confirmou"] = True
    return eventos


def _tabela_tercis(eventos: list[dict]) -> None:
    validos = [e for e in eventos if e["concordancia"] == e["concordancia"]]
    sem_folego = len(eventos) - len(validos)
    if len(validos) < 10:
        print(f"    n valido={len(validos)} (sem_folego={sem_folego}) -- amostra "
              f"pequena demais para tercis, pulando")
        return
    concs = np.array([e["concordancia"] for e in validos])
    confirma = np.array([e["confirmou"] for e in validos])
    q1, q2 = np.quantile(concs, [1 / 3, 2 / 3])
    baixo = concs <= q1
    medio = (concs > q1) & (concs <= q2)
    alto = concs > q2
    taxa_geral = confirma.mean()
    print(f"    n={len(validos)} (sem_folego={sem_folego})  taxa_confirmacao_GERAL="
          f"{100*taxa_geral:.1f}%  corte_tercis=[{q1:.3f}; {q2:.3f}]")
    for rotulo, mask in (("baixo/diverge", baixo), ("medio", medio), ("alto/confirma", alto)):
        n = int(mask.sum())
        if n == 0:
            print(f"      {rotulo:<14} n=0")
            continue
        k = int(confirma[mask].sum())
        lo, hi = b.ic95_wilson(k, n)
        print(f"      {rotulo:<14} n={n:>4}  confirmou={k:>4}  taxa={100*k/n:5.1f}%  "
              f"IC95=[{100*lo:5.1f}%;{100*hi:5.1f}%]  concordancia_media={concs[mask].mean():+.3f}")


def main() -> None:
    dias_is = b.dias_da_janela(b.carrega_win(), b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Validacao causal G23 -- IS (jan-jun/2026, {len(dias_is)} pregoes).")
    print(f"Pernada oficial = {PERNADA_PONTOS:.0f}pts (R43, congelada). Testando "
          f"{len(JANELAS_MIN)}x{len(NASCENTES_PONTOS)}={len(JANELAS_MIN)*len(NASCENTES_PONTOS)} "
          f"combinacoes de (janela_min, nascente_pontos).\n", flush=True)

    for janela_min in JANELAS_MIN:
        for nascente_pontos in NASCENTES_PONTOS:
            print(f"  -- janela_min={janela_min}min  nascente_pontos={nascente_pontos:.0f}pts --",
                  flush=True)
            eventos = _eventos_nascentes(dias_is, janela_min, nascente_pontos)
            print(f"    pernadas nascentes BRUTAS no IS: {len(eventos)}")
            _tabela_tercis(eventos)
            print(flush=True)


if __name__ == "__main__":
    main()
