"""VALIDACAO 2025 — rodada UMA vez, 2026-10-06, com a lista CONGELADA abaixo
(escrita antes de qualquer contato com os dados de 2025). Nenhum parametro
daqui pode ser ajustado depois de ver o resultado.

Candidatas: saidas dos agentes b1 (mais medias), b2 (tempos graficos) e b3
(posicao do preco), escolhidas so' com 2026. Mais duas referencias: a ATUAL e a
versao de 5 medias SEM o filtro do mes.
Dado: WIN@ do MT5 (contratos anteriores ao vigente vem AJUSTADOS — item 5.32),
segmentado por rolagem (mesma regra do EA), ate' 01/10/2025 (igual ao Testador).
"""
import importlib.util as u
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("w", AQUI.parent / "win_cinco_medias.py"); w = u.module_from_spec(s); s.loader.exec_module(w)
w.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"
w.FIM_DADOS[2025] = "2025-10-01"

CONGELADAS = [
    ("ATUAL 9/21/34/100/200 M5", "5min", {}),
    ("ref: 5 medias SEM filtro do mes", "5min", dict(filtro_mes=False)),
    ("b1-1 9/21/34/55/100/150/200/300", "5min", dict(periodos=(9, 21, 34, 55, 100, 150, 200, 300))),
    ("b1-2 9/21/34/55/100/200", "5min", dict(periodos=(9, 21, 34, 55, 100, 200))),
    ("b1-3 9/21/34/55/100/150/200/300/400", "5min", dict(periodos=(9, 21, 34, 55, 100, 150, 200, 300, 400))),
    ("b2-1 M15 3/7/11/33/67 saida7", "15min", dict(periodos=(3, 7, 11, 33, 67), ema_saida=7)),
    ("b2-2 M30 2/4/6/17/33 saida4", "30min", dict(periodos=(2, 4, 6, 17, 33), ema_saida=4)),
    ("b2-3 M10 9/21/34/100/200", "10min", {}),
    ("b3 corpo>EMA9, inclina nenhuma", "5min", dict(zona="corpo>m1", inclina=())),
]


def main():
    linhas, meses = [], {}
    for nome, tf, kw in CONGELADAS:
        for ano in (2026, 2025):
            df, r = w.rodar_janelas(ano, tf, **kw)
            linhas.append(dict(variante=nome, ano=ano, **{k: r[k] for k in ("liquido", "janelas_pos", "pior", "trades", "acerto", "PF", "pts_op", "ic95", "maior_DD")}))
            if ano == 2025:
                meses[nome] = df.set_index("janela").liquido
            print(nome, ano, r, flush=True)
    t = pd.DataFrame(linhas)
    pd.set_option("display.width", 250)
    print("\n" + t.to_string(index=False))
    print("\n2025 mes a mes:\n" + pd.DataFrame(meses).to_string())
    t.to_csv(AQUI / "validacao_2025_resumo.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(meses).to_csv(AQUI / "validacao_2025_meses.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
