"""Injeta os dados da coleta dentro do painel local `analise.html`.

O painel e' UM arquivo so': os dados entram no lugar do bloco
`<script id="dados">`, entao ele abre com dois cliques, funciona offline e
pode ser copiado para qualquer lugar sem levar anexo junto. Rodar de novo e'
idempotente -- o bloco e' substituido, nunca duplicado.

O HTML e' escrito e revisado a mao; so' os dados sao regenerados quando uma
coleta nova termina.

FONTE: `50_perfil_operacoes.csv` -- as 195 operacoes da geometria de PRODUCAO
(T2.0, com fade) nas tres janelas, com as 15 variaveis medidas no instante do
sinal. E' a base mais rica das coletas de 2026-09-14: `30_fade_agitacao_
trades.csv` tem mais linhas (327) porque inclui a variante `sem_fade`, mas
nao carrega distancia do rompimento, minutos desde a abertura, aceleracao de
volume nem espera ate' preencher -- que sao justamente as variaveis da
pergunta "o que as perdedoras tem em comum".

Uso: `python -u scripts/daytrade/wdo_orb_painel_dados_2026_09_14.py`
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DIR = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"

COLUNAS = [
    "data", "janela", "tipo", "side", "dia_semana", "saida_efetiva",
    "pnl_brl", "venceu",
    # conhecidas no momento do sinal
    "minutos_desde_abertura", "hora_sinal", "dist_rompimento_ticks",
    "faixa_ticks", "faixa_rel_amplitude15", "stop_ticks", "alvo_ticks",
    "tentativa_no_dia", "vol_5min", "vol_15min", "aceleracao_vol",
    "nticks_5min", "amplitude_5min", "amplitude_15min",
    "retorno_5min_ticks", "alinhamento_ticks", "atraso_fill_min",
    # so' existem depois que a operacao fechou
    "mfe_ticks", "mae_ticks", "mfe_sobre_alvo",
]


def main() -> None:
    df = pd.read_csv(DIR / "50_perfil_operacoes.csv")

    # a geometria de producao e' alvo = 2x stop (`alvo_multiplo=2.0`); o CSV do
    # perfil guarda so' o stop, entao o alvo e' reconstruido -- nao medido.
    df["alvo_ticks"] = (df["stop_ticks"] * 2).round(0)
    df["mfe_sobre_alvo"] = (df["mfe_ticks"] / df["alvo_ticks"]).round(3)
    df["minutos_desde_abertura"] = df["minutos_desde_abertura"].round(1)
    df["atraso_fill_min"] = df["atraso_fill_min"].round(2)

    out = df[COLUNAS].where(pd.notna(df[COLUNAS]), None)
    linhas = [[(None if pd.isna(v) else (round(v, 4) if isinstance(v, float) else v))
               for v in row] for row in out.itertuples(index=False, name=None)]

    bloco = (
        "\n/* gerado por scripts/daytrade/wdo_orb_painel_dados_2026_09_14.py */\n"
        f"window.COLUNAS = {json.dumps(COLUNAS)};\n"
        f"window.OPS = {json.dumps(linhas, ensure_ascii=False)};\n"
    )

    destino = DIR / "analise.html"
    html = destino.read_text(encoding="utf-8")
    abre, fecha = '<script id="dados">', "</script>"
    i = html.index(abre) + len(abre)
    j = html.index(fecha, i)
    destino.write_text(html[:i] + bloco + html[j:], encoding="utf-8")

    print(f"[painel] {len(linhas)} operacoes, {len(COLUNAS)} colunas -> {destino}")
    print(f"[painel] janelas: {df.janela.value_counts().to_dict()}")
    print(f"[painel] vitorias: {int(df.venceu.sum())} de {len(df)}")


if __name__ == "__main__":
    main()
