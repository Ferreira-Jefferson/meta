"""F1 — candidatas congeladas (padrao de candle como SAIDA da WinCincoMedias v2.02).
Saida: vela fechada com pavio de rejeicao CONTRA a posicao >= X do range E range >= K x ATR(14 da vela anterior)
-> sai a mercado na abertura seguinte (compra: pavio superior; venda: pavio inferior).
CANDIDATAS = {nome: funcao(ano, dados_m30) -> resumo (formato de rodar_janelas)}.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import f1_candle as f   # aplica o gancho saida_extra em win_cinco_medias.simula
import win_cinco_medias as w


def _mk(x, mg):
    def run(ano, dados):
        _, resumo = w.rodar_janelas(ano, dados=dados, saida_extra=f.saida_func(("wick_rej", x, mg)))
        return resumo
    return run


CANDIDATAS = {
    "saida_pavio0.5_rng1.0": _mk(0.5, 1.0),   # centro do platoo
    "saida_pavio0.6_rng0.75": _mk(0.6, 0.75),  # vizinho do platoo (mais meses melhores)
}

if __name__ == "__main__":
    d = w.carregar(2026)
    for k, fn in CANDIDATAS.items():
        print(k, fn(2026, d))
