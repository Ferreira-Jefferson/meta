"""Candidatas congeladas da familia ALVO (d2). CANDIDATAS = {nome: funcao(ano, dados) -> resumo}.
Evidencia FRACA (ver d2_relatorio.md): ganho concentrado em jul/ago-2026, perde janeiro; 12/14 janelas.
Alvo = limite (enche so com 1 tick alem), ATR(14) M30 da barra do sinal, extremo = maxima/minima das barras fechadas."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from d2_alvo import rodar, colunas_volume, carregar


def _mk(alvo):
    def f(ano, dados=None):
        d = colunas_volume(carregar(ano)) if dados is None else dados
        if "vrel" not in d.columns:
            d = colunas_volume(d)
        return rodar(d, ano=ano, alvo=alvo)[1]
    return f


CANDIDATAS = {
    "alvo_trail_k2_j1": _mk(("trail", 2, 1)),      # alvo inicial 2xATR; sobe p/ extremo+1xATR a cada novo extremo
    "alvo_trail_k2_j05": _mk(("trail", 2, 0.5)),
    "alvo_fixo_k2": _mk(("fixo", 2)),
}

if __name__ == "__main__":
    for n, f in CANDIDATAS.items():
        print(n, f(2026, None), flush=True)
