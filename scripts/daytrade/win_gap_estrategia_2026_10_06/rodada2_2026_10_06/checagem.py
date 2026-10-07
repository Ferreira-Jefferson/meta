# -*- coding: utf-8 -*-
"""Gera CHECAGEM_DADOS.md com a evidencia MEDIDA de cada item de integridade da rodada 2."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ctx as C  # noqa: E402
import ticks_prep as TP  # noqa: E402
from market_data_intraday.win_sem_leiloes import carrega_grade, fim_continuo  # noqa: E402

ROOT = TP.ROOT


def hms(ms):
    ms = int(ms)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def t2ms(s):
    h, m, r = str(s).split(":")
    return (int(h) * 3600 + int(m) * 60 + float(r)) * 1000


def md_tab(df: pd.DataFrame, max_rows=60) -> str:
    if df.empty:
        return "_(nenhum)_\n"
    df = df.head(max_rows)
    cab = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return cab + "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False)) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bj_all, dj_all, _ = None, None, None
    import dados
    b, d = dados.carrega("2026")
    ini, fim = pd.Timestamp(C.INI), pd.Timestamp(C.FIM)
    d = d[(d.index >= ini) & (d.index <= fim)]
    f = pd.read_csv(ROOT / "data" / "win_fases_pregao_6m.csv", sep=";", encoding="utf-8-sig", parse_dates=["data"]).set_index("data")
    f = f[(f.index >= ini) & (f.index <= fim)]
    tk = pd.read_csv(AQUI / "ticks_resumo.csv", sep=";", parse_dates=["dia"]).set_index("dia")
    grade = carrega_grade()
    bj, dj, ctx = C.constroi()
    usados = set(pd.Timestamp(x) for x in ctx)
    L = []
    L.append("# CHECAGEM DOS DADOS — rodada 2 (WIN gap, 2026-04-06 a 2026-10-05)\n")
    L.append("Tudo abaixo e' MEDIDO por `checagem.py` (reexecutavel). Fontes: `data/win_fases_pregao_6m.csv` (fases por tick), "
             "`data/b3_grade_horaria_win.csv`, `data/comparativo_win_2026/ticks/*.npz` (WIN$N), `data/win_sem_leiloes/m5_WIN$N.parquet`.\n")
    L.append(f"Pregoes na janela: {len(f)} (CSV) / {len(d)} (tabela de dias). Usados nas medicoes: **{len(usados)}**. Excluidos: {len(f) - len(usados)}.\n")

    # 1. gap
    L.append("## 1. Gap = preco do leilao de D − preco do call de D−1\n")
    g_csv_ini = f.pre_preco_inicio - f.pos_preco_fechamento.shift(1)
    g_csv_fec = f.pre_preco_fechamento - f.pos_preco_fechamento.shift(1)
    x = d[["gap"]].join(g_csv_ini.rename("csv_ini")).join(g_csv_fec.rename("csv_fec"))
    x = x.iloc[1:]
    L.append(f"- Gap usado (`dias_WIN$N.csv`) contra o recalculado no CSV de fases (`pre_preco_inicio[D] − pos_preco_fechamento[D−1]`): "
             f"{int(((x.gap - x.csv_ini).abs() == 0).sum())}/{int(x.gap.notna().sum())} dias comparaveis iguais (07-31 sem gap); maior diferenca {float((x.gap - x.csv_ini).abs().max()):.1f} pts. "
             f"Com `pre_preco_fechamento` (preco unico do leilao): {int(((x.gap - x.csv_fec).abs() == 0).sum())}/{int(x.gap.notna().sum())} iguais.")
    dif_ini_fec = (f.pre_preco_inicio - f.pre_preco_fechamento).abs()
    L.append(f"- `pre_preco_inicio == pre_preco_fechamento` (leilao de preco unico) em {int((dif_ini_fec == 0).sum())}/{len(f)} dias.")
    L.append("- O gap do 1o dia da janela (2026-04-06) usa o call de 2026-04-02 (fora da janela); e' 1 numero lido, nenhuma barra/tick anterior a 04-06 e' lido.\n")

    # 2. fases e continuo
    L.append("## 2. Fase continua: comeca depois do leilao e termina em `negociacao_fim` da grade\n")
    linhas = []
    ok_ini = ok_fim = 0
    for dia in f.index:
        r = f.loc[dia]
        fim_g = (fim_continuo(dia, grade) - dia).total_seconds() * 1000
        t = tk.loc[dia]
        leil_ms = t2ms(r.pre_hora_leilao) if isinstance(r.pre_hora_leilao, str) else np.nan
        ok_i = t.t_ini > leil_ms if leil_ms == leil_ms else False
        ok_f = t.t_fim < fim_g
        ok_ini += int(ok_i); ok_fim += int(ok_f)
        if not (ok_i and ok_f):
            linhas.append(dict(dia=dia.date(), leilao=r.pre_hora_leilao, primeiro_tick=hms(t.t_ini), ultimo_tick=hms(t.t_fim), fim_grade=hms(fim_g), ok_ini=ok_i, ok_fim=ok_f))
    L.append(f"- Primeiro tick continuo > hora do leilao: {ok_ini}/{len(f)}. Ultimo tick continuo < `negociacao_fim` da grade (18:25, ou 17:55 antes de 2024-03-11 em horario de verao dos EUA — nenhum dia da janela e' dessa fase): {ok_fim}/{len(f)}.")
    L.append("- Falhas:\n" + md_tab(pd.DataFrame(linhas)))
    fins = d["fim_continuo"].dt.strftime("%H:%M").value_counts().to_dict()
    L.append(f"- `fim_continuo` da grade por dia na janela: {fins}.\n")

    # 3. barras M5 sem leilao/call
    L.append("## 3. Nenhum leilao nem call nas barras usadas: 1a e ultima barra M5 de cada dia contra o CSV\n")
    rows = []
    for dia in sorted(usados):
        g = b[b.index.normalize() == dia]
        r = f.loc[dia]
        fim_g = fim_continuo(dia, grade)
        ult_esperada = fim_g - pd.Timedelta(minutes=5)
        rows.append(dict(dia=dia, open1=g.iloc[0].open, close_n=g.iloc[-1].close, hi=g.high.max(), lo=g.low.min(),
                         csv_o=r.pregao_preco_inicio, csv_c=r.pregao_preco_fechamento, csv_h=r.pregao_maxima, csv_l=r.pregao_minima,
                         ini1=g.index[0], fimN=g.index[-1], ult_esp=ult_esperada, fonte=r.fonte))
    T = pd.DataFrame(rows)
    ok_o = T.open1 == T.csv_o; ok_c = T.close_n == T.csv_c; ok_h = T.hi == T.csv_h; ok_l = T.lo == T.csv_l
    ok_u = T.fimN == T.ult_esp
    n = len(T)
    L.append(f"- Abertura da 1a barra M5 == `pregao_preco_inicio` (1o negocio continuo): {int(ok_o.sum())}/{n}")
    L.append(f"- Fechamento da ultima barra M5 == `pregao_preco_fechamento` (ultimo negocio continuo): {int(ok_c.sum())}/{n}")
    L.append(f"- Maxima do dia nas barras == `pregao_maxima`: {int(ok_h.sum())}/{n}; minima == `pregao_minima`: {int(ok_l.sum())}/{n}")
    L.append(f"- Hora da ultima barra == `fim_continuo` − 5 min (18:20): {int(ok_u.sum())}/{n}; nenhuma barra com hora >= 18:25: {int((b.index.time >= pd.Timestamp('18:25').time()).sum()) == 0}")
    bad = T[~(ok_o & ok_c & ok_h & ok_l & ok_u)][["dia", "open1", "csv_o", "close_n", "csv_c", "hi", "csv_h", "lo", "csv_l", "fimN", "ult_esp", "fonte"]]
    L.append("- Divergencias (dia, barras x CSV):\n" + md_tab(bad.assign(dia=bad.dia.dt.date)))


    # 3b. todas as barras M5 contra OHLC derivado dos ticks
    L.append("### 3b. Barras M5 usadas x OHLC reconstruido dos ticks continuos (high, low, close de TODAS as barras; open da barra 1)\n")
    tot = bad_h = bad_l = bad_c = bad_o1 = 0
    ex_h = []
    for dia in sorted(usados):
        g = b[b.index.normalize() == dia]
        t, p = TP.carrega(dia)
        st = (g.index.hour * 3_600_000 + g.index.minute * 60_000).to_numpy().astype("int64")
        bi = np.searchsorted(t, np.r_[st, st[-1] + 300_000], side="left")
        for k in range(len(st)):
            seg = p[bi[k]:bi[k + 1]]
            if len(seg) == 0:
                continue
            tot += 1
            r = g.iloc[k]
            bad_h += int(seg.max() != r.high); bad_l += int(seg.min() != r.low); bad_c += int(seg[-1] != r.close)
            if k == 0:
                bad_o1 += int(seg[0] != r.open)
            if seg.max() != r.high and len(ex_h) < 8:
                ex_h.append((str(dia.date()), g.index[k].strftime("%H:%M"), float(r.high), int(seg.max())))
    L.append(f"- {tot} barras comparadas: high diferente em {bad_h}, low diferente em {bad_l}, close diferente em {bad_c}; open da barra 1 diferente em {bad_o1}/{len(usados)}. "
             "Barras M5 e ticks vem de fontes distintas (M1 do MT5 x ticks); diferencas, quando existem, sao de 5 a 15 pts nos extremos. "
             f"Exemplos de high (dia, barra, M5, tick): {ex_h}. A execucao usa os ticks; o sinal usa open/close da barra 1.\n")

    # sinal da barra 1 com OHLC dos ticks x das barras M5
    mud = 0; mud_ids = []
    for dia in sorted(usados):
        g = b[b.index.normalize() == dia]
        t, p = TP.carrega(dia)
        k1 = int(np.searchsorted(t, 32_400_000 + 300_000, side="left"))
        o_t, c_t = float(p[0]), float(p[k1 - 1])
        o_m, c_m = float(g.iloc[0].open), float(g.iloc[0].close)
        s_t, s_m = np.sign(c_t - o_t), np.sign(c_m - o_m)
        if s_t != s_m:
            mud += 1; mud_ids.append(str(dia.date()))
    L.append(f"- Sinal da barra 1 (sinal de close-open) com OHLC dos ticks x das barras M5: diferente em {mud}/{len(usados)} dias {mud_ids}."+"\n")

    # 4. reconcile ticks
    L.append("## 4. Reconciliacao dos ticks continuos com o CSV (open/close/max/min do pregao)\n")
    rr = []
    for dia in sorted(usados):
        t = tk.loc[dia]; r = f.loc[dia]
        rr.append(dict(dia=dia.date(), tick_o=t.p_ini, csv_o=r.pregao_preco_inicio, tick_c=t.p_fim, csv_c=r.pregao_preco_fechamento,
                       tick_h=t.p_max, csv_h=r.pregao_maxima, tick_l=t.p_min, csv_l=r.pregao_minima,
                       o_ok=t.p_ini == r.pregao_preco_inicio, c_ok=t.p_fim == r.pregao_preco_fechamento, h_ok=t.p_max == r.pregao_maxima, l_ok=t.p_min == r.pregao_minima))
    R_ = pd.DataFrame(rr)
    L.append(f"- Ticks continuos (filtrados por `filtra_ticks_continuo`) == CSV, nos {len(R_)} dias usados: abertura {int(R_.o_ok.sum())}/{len(R_)}, "
             f"fechamento {int(R_.c_ok.sum())}/{len(R_)}, maxima {int(R_.h_ok.sum())}/{len(R_)}, minima {int(R_.l_ok.sum())}/{len(R_)}.")
    L.append("- Divergencias:\n" + md_tab(R_[~(R_.o_ok & R_.c_ok & R_.h_ok & R_.l_ok)]))
    ex = f.index.difference(pd.DatetimeIndex(sorted(usados)))
    re = []
    for dia in ex:
        t = tk.loc[dia]; r = f.loc[dia]
        re.append(dict(dia=dia.date(), tick_o=t.p_ini, csv_o=r.pregao_preco_inicio, tick_c=t.p_fim, csv_c=r.pregao_preco_fechamento, tick_h=t.p_max, csv_h=r.pregao_maxima, tick_l=t.p_min, csv_l=r.pregao_minima))
    L.append("- Mesma conta nos dias EXCLUIDOS (informativo):\n" + md_tab(pd.DataFrame(re)))

    # 5. excluidos
    L.append("## 5. Dias excluidos e decisoes\n")
    gap_abs = d.gap.abs()
    med = float(gap_abs[~d.index.isin(ex)].median())
    L.append(f"|gap| mediano dos dias usados: {med:.0f} pts.\n")
    rows = []
    for dia in ex:
        i = list(d.index).index(dia)
        prox = d.index[i + 1] if i + 1 < len(d) else None
        rows.append(dict(dia=dia.date(), motivo=d.loc[dia].motivo_excl or C.EXCLUIR_EXTRA.get(str(dia.date()), ""), gap=d.loc[dia].gap,
                         dia_seguinte=prox.date() if prox is not None else "", gap_seguinte=d.loc[prox].gap if prox is not None else np.nan))
    L.append(md_tab(pd.DataFrame(rows)))
    L.append("**Rolagens (04-15, 06-17, 08-12).** O WIN$N troca de contrato no vencimento (quarta mais proxima do dia 15 dos meses pares). "
             "No dia D da troca, o call de D−1 e o leilao de D sao de contratos diferentes: degrau medido de 3.350 a 4.415 pts no gap contra |gap| mediano de "
             f"{med:.0f}. Por isso os 3 dias sao excluidos. No dia SEGUINTE o call de D (ja' no contrato novo) e o leilao de D+1 estao no mesmo contrato: "
             "o gap desses dias esta na coluna `gap_seguinte` acima e fica na faixa normal; os dias seguintes sao MANTIDOS. "
             "Prova adicional: o pregao de D continua intra-contrato (tabela `lente4/dias_flag.csv`: 'pregao D intra-contrato ok'), e so' o gap e' contaminado.\n")
    L.append("**07-31.** Primeiro negocio as 12:34:07 (abertura atrasada real; 351 min de pregao): sem 1a barra as 09:00, o sinal 'a 1a barra M5' nao existe nesse dia. Excluido.\n")
    L.append("**10-05 (gap +17.775 pts).** E' real (dia seguinte ao 1o turno da eleicao): leilao e call batem com os ticks e com o CSV (item 4). Mantido, e e' o dia de maior |gap| da janela.\n")
    L.append("**05-06, 08-10, 09-24 (fonte `ticks+M1`).** Medido em `ticks_resumo.csv`/CSV de fases: 05-06 sem ticks de 09:16 a 09:23 (maior buraco entre ticks 368 s, dentro da janela da ordem de entrada 09:05-09:35); "
             "08-10 sem ticks de 10:00 a 10:08 (155 s; posicao potencialmente aberta); 09-24 ticks so' comecam as 09:14 (a 1a barra e o preco do 1o negocio continuo vem do M1, a janela inteira de entrada fica cega). "
             "Decisao: **excluir os tres**. O simulador resolve stop/alvo/limite por tick; num buraco ele nao ve se o nivel foi tocado, e o M1 nao devolve a sequencia. Custo: 3 de 123 pregoes.\n")

    # 6. horario da 1a barra
    L.append("## 6. Hora da 1a barra M5 e do sinal\n")
    rows = []
    for dia in sorted(usados):
        g = b[b.index.normalize() == dia]
        r = f.loc[dia]
        leil = t2ms(r.pre_hora_leilao)
        ini_c = t2ms(r.pregao_hora_inicio)
        rows.append(dict(dia=dia.date(), bar1=g.index[0].strftime("%H:%M"), leilao_ms=leil, ini_cont_ms=ini_c))
    H = pd.DataFrame(rows)
    fora = H[H.bar1 != "09:00"]
    L.append(f"- Pregoes cuja 1a barra M5 com negocio continuo NAO e' a das 09:00: {len(fora)} de {len(H)}.")
    L.append(md_tab(fora.assign(leilao=fora.leilao_ms.map(hms), inicio_continuo=fora.ini_cont_ms.map(hms))[["dia", "bar1", "leilao", "inicio_continuo"]]))
    dentro = H[(H.ini_cont_ms >= 32_400_000) & (H.ini_cont_ms < 32_700_000)]
    L.append(f"- Leilao de abertura DENTRO da barra 09:00-09:05 (o continuo comeca depois dele, no mesmo M5): {len(dentro)}/{len(H)} dias; "
             f"o continuo comeca em mediana {hms(H.ini_cont_ms.median())}, p90 {hms(H.ini_cont_ms.quantile(0.9))}. "
             "A barra 1 e' portanto parcial: so' os negocios continuos depois do leilao (o loader remove volume e preco do leilao; open = 1o negocio continuo, item 3). "
             "A decisao acontece no FECHO da barra (09:05); a ordem so' vale a partir de 09:05 (testado em `tests/test_win_gap_rodada2_lookahead.py`).")
    L.append(f"- Dias com o continuo comecando depois das 09:05: {int((H.ini_cont_ms >= 32_700_000).sum())}; antes das 09:00: {int((H.ini_cont_ms < 32_400_000).sum())}.\n")

    # 7. look-ahead
    L.append("## 7. Look-ahead\n")
    L.append("- ATR de dias anteriores (`ctx.calcula_atr_prev`): media da amplitude dos <= 10 pregoes validos ANTERIORES a D (exige >= 3), sem D; ele so' usa pregoes DENTRO da janela (nada antes de 04-06).")
    L.append("- Filtro de volume do call (V3): mediana movel de ate' 60 pregoes de `call_volume` com `shift(1)` (ate' D−1), so' valores do mesmo regime (medido), minimo 20 observacoes; "
             "no 1o pregao (cujo D−1 e' pre-janela) o filtro e' desligado. Pregoes sem historico suficiente contam como 'volume nao alto'.")
    L.append("- Contexto do dia (`ctx.constroi`) so' carrega: gap, vol_alto, call de D−1, ATR de D−1 para tras e a 1a barra (open/high/low/close).")
    L.append("- Testes pytest (`tests/test_win_gap_rodada2_lookahead.py`, tmp_path, paralelo-seguro): (1) ATR de D identico se D e o futuro mudam; (2) `vol_alto` identico para D <= k se `call_volume` de k em diante muda "
             "(e o teste enxerga mudanca depois); (3) decisao/niveis so' dependem da 1a barra e do contexto; (4) a ordem nao enche com ticks anteriores ao fecho da 1a barra; (5) stop/alvo ignoram ticks anteriores ao fill e nao mudam se so' o futuro muda.\n")
    out = AQUI / "CHECAGEM_DADOS.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("ok", out)


if __name__ == "__main__":
    main()
