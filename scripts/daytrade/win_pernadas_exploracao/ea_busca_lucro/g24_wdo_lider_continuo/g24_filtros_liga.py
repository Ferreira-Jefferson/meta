# -*- coding: utf-8 -*-
"""PASSO 3 do mandato (G24): o lift de direcao do passo 2 melhora quando
combinado com os filtros de LIGA que ja' funcionam no resto da busca (R01:
hora<11h; R20/R35: onda de volatilidade -- vela M1 com faixa >= 2x a mediana
CAUSAL do mesmo minuto-do-dia nos 20 pregoes anteriores)? Mede o efeito ANTES
e DEPOIS de cada filtro, SEPARADAMENTE, sobre os MESMOS eventos do passo 2
(estratificacao pos-hoc sobre uma unica passada -- nao reabre uma simulacao
nova por filtro, mesma disciplina do item 6.50 de LICOES_DE_PRODUCAO.md:
aqui nao ha' "rearme" de ordem nenhum, e' medida estatistica pura sobre
minutos ja' ocorridos, entao sub-filtrar o mesmo conjunto e' valido).

Usa k=1min e k=5min (os dois extremos do passo 2), quantil=0,90 (decil, o
corte mais seletivo ja' testado).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g24_wdo_lider_continuo/g24_filtros_liga.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import g24_base as b  # noqa: E402

KS = [1, 5]
QUANTIL = 0.90
MIN_DIAS_BURN_IN_VOL = 20


def _faixa_m1_relativa(df: pd.DataFrame, dias: list) -> pd.Series:
    """Faixa (`high-low`) de cada vela M1 dividida pela mediana CAUSAL da
    faixa do MESMO minuto-do-dia nos `min_dias_burn_in` pregoes anteriores
    (R20/R35: "vela M1 com faixa >= 2x a do mesmo minuto nos 20 pregoes
    anteriores"). Fora do burn-in -> NaN (nunca conta como "grande")."""
    fatia = b.bars_dos_dias(df, dias)
    faixa = fatia["high"] - fatia["low"]
    minuto_do_dia = fatia.index.strftime("%H:%M")
    dia = pd.Series(fatia.index.date, index=fatia.index)
    chave = pd.Series(minuto_do_dia, index=fatia.index)

    tabela = pd.DataFrame({"dia": dia.values, "minuto": chave.values, "faixa": faixa.values},
                          index=fatia.index)
    dias_ordenados = sorted(tabela["dia"].unique())
    out = pd.Series(float("nan"), index=fatia.index)
    hist: dict[str, list[float]] = {}
    for i, d in enumerate(dias_ordenados):
        mask_dia = tabela["dia"] == d
        if i >= MIN_DIAS_BURN_IN_VOL:
            medianas = {m: float(np.median(v)) for m, v in hist.items() if len(v) >= 5}
            sub = tabela[mask_dia]
            med = sub["minuto"].map(medianas)
            rel = sub["faixa"].to_numpy() / med.to_numpy()
            out.loc[sub.index] = rel
        for m, f in zip(tabela.loc[mask_dia, "minuto"], tabela.loc[mask_dia, "faixa"]):
            hist.setdefault(m, []).append(f)
    return out


def _wilson_linha(rotulo: str, mesma_dir: np.ndarray) -> str:
    n = len(mesma_dir)
    if n == 0:
        return f"        {rotulo:<42} n=0"
    k = int(mesma_dir.sum())
    lo, hi = b.ic95_wilson(k, n)
    return (f"        {rotulo:<42} n={n:>6}  mesma_dir={100*k/n:5.1f}% "
             f"IC95=[{100*lo:5.1f}%;{100*hi:5.1f}%]")


def main() -> None:
    win = b.carrega_win()
    wdo = b.carrega_wdo()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Filtros de LIGA sobre o lift de direcao (G24) -- IS ({len(dias_is)} pregoes), "
          f"quantil={QUANTIL:.2f} (decil).\n", flush=True)

    faixa_rel = _faixa_m1_relativa(win, dias_is)

    for k in KS:
        ret_wdo_passado = b.retorno_k_min(wdo, dias_is, k)
        ret_win_futuro_bruto = b.retorno_k_min(win, dias_is, k)
        ret_win_futuro = b.desloca_dentro_do_dia(ret_win_futuro_bruto, k)

        idx_comum = (ret_wdo_passado.index
                     .intersection(ret_win_futuro.index)
                     .intersection(faixa_rel.index)
                     .sort_values())
        wdo_p = ret_wdo_passado.reindex(idx_comum)
        win_f = ret_win_futuro.reindex(idx_comum)
        faixa_k = faixa_rel.reindex(idx_comum)
        hora = pd.Series(idx_comum.hour, index=idx_comum)

        validos = wdo_p.notna() & win_f.notna() & (wdo_p != 0)
        wdo_v, win_v, faixa_v, hora_v = wdo_p[validos], win_f[validos], faixa_k[validos], hora[validos]

        limiar = b.quantil_causal_abs(wdo_v, QUANTIL)
        grande = (wdo_v.abs() >= limiar).fillna(False)
        mesma_dir = (np.sign(wdo_v) == np.sign(win_v))

        print(f"  -- k={k}min --")
        base = mesma_dir[grande].to_numpy()
        print(_wilson_linha("SEM filtro de LIGA (so' magnitude grande)", base))

        so_manha = grande & (hora_v < 11)
        print(_wilson_linha("+ R01 hora<11h", mesma_dir[so_manha].to_numpy()))

        so_vol = grande & (faixa_v >= 2.0).fillna(False)
        print(_wilson_linha("+ R20/R35 vela M1 faixa>=2x (causal)", mesma_dir[so_vol].to_numpy()))

        so_ambos = grande & (hora_v < 11) & (faixa_v >= 2.0).fillna(False)
        print(_wilson_linha("+ R01 E R20/R35 (ambos)", mesma_dir[so_ambos].to_numpy()), flush=True)
        print(flush=True)

    print("Leitura: compare cada linha filtrada contra a linha 'SEM filtro' do "
          "mesmo k -- se os filtros de LIGA nao deslocam a taxa de 'mesma "
          "direcao' para bem acima de ~50%, eles ajudam a achar QUANDO o WIN "
          "se mexe mais (seu papel original, ja' confirmado em R01/R02/R20/"
          "R35), mas nao ajudam a achar PARA ONDE -- a mesma distincao que "
          "o resumo de REGRAS.md ja' registra para o WIN em geral.")


if __name__ == "__main__":
    main()
