# -*- coding: utf-8 -*-
"""Geracao 5 (`WinBuscaLucroG05RegimeVol`) -- BUSCA no IS (jan-jun/2026).

Pergunta: o efeito da G4 (confirmacao cruzada WIN x WDO) e' de fato sobre a
CORRELACAO entre os dois mercados, ou e' so' um "regime de movimento forte"
que o proprio WIN sozinho ja' expoe -- com amostra MAIOR, porque nao depende
de dois instrumentos concordarem no mesmo minuto? Testa 3 proxies WIN-only
causais (`regime_amplitude_bloco` -- R20; `regime_vela_extrema` -- R35, ja'
confirmado; `regime_volume_bloco`) como ALTERNATIVAS ao estado cruzado da G4,
mais um ENSEMBLE (>=2 concordam) e a linha de REFERENCIA (G4 recalculada
nesta geracao, mesma janela).

Para cada proxy: ESTAGIO 1 escolhe os parametros do DETECTOR (janela/quantil
ou multiplo) com a geometria vencedora da G4 fixa (stop=150, alvo=3x,
buffer=30 -- ponto de partida, nao herdado cegamente). ESTAGIOS 2/3/4
retunam stop_pontos / alvo_multiplo / buffer_entrada_pontos no detector
vencedor, mesmo molde greedy sequencial de G1-G4.

Criterio de SUCESSO desta geracao (ORQUESTRACAO.md, item 4 do mandato): nao
basta liquido positivo -- precisa de (a) trades > 127 (amostra da G4), (b)
concentracao top-3-pregoes/liquido <= ~35-40% (G4 tinha 59% no IS), (c) IC95
do win% nao tocando o breakeven empirico (ou folga clara). Se nenhum proxy
bater isso, reporta honestamente -- nao forca.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g05_regime_vol/g05_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g05_base as b  # noqa: E402

MAX_WORKERS = 4
GEOMETRIA_G4 = dict(stop_pontos=150.0, alvo_multiplo=3.0, buffer_entrada_pontos=30.0)

PROXY_A_GRID = [(f"A j{jm} q{int(q*100)}", dict(janela_min=jm, quantil=q))
                for jm in (10, 15, 20) for q in (0.75, 0.85, 0.90)]
PROXY_B_GRID = [(f"B m{m:.1f}", dict(multiplo=m)) for m in (2.0, 2.5, 3.0)]
PROXY_C_GRID = [(f"C j{jm} q{int(q*100)}", dict(janela_min=jm, quantil=q))
                for jm in (15, 20) for q in (0.75, 0.85, 0.90)]

PROXY_FN = dict(A="regime_amplitude_bloco", B="regime_vela_extrema", C="regime_volume_bloco")


def _criterio_sucesso(c: dict) -> tuple[bool, list[str]]:
    razoes = []
    ok = True
    if not (c["n"] > 127):
        ok = False
        razoes.append(f"trades={c['n']} <= 127 (G4)")
    if not (c["concentracao_top3"] == c["concentracao_top3"] and c["concentracao_top3"] <= 0.40):
        ok = False
        conc = c["concentracao_top3"]
        razoes.append(f"top3/liq={b.br(100*conc,0) if conc==conc else '--'}% > 40%")
    if c["veredito"] != "POSITIVO":
        ok = False
        razoes.append(f"veredito win%={c['veredito']} (nao e' POSITIVO com folga)")
    if c["liquido"] <= 0:
        ok = False
        razoes.append("liquido <= 0")
    return ok, razoes


def _worker(rotulo: str, proxy_nome: str, regime_kwargs: dict, geo_kwargs: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from strategy.daytrade.lab import win_busca_lucro_g05_regime_vol as mod
    regime_fn = getattr(mod, PROXY_FN[proxy_nome])
    res, strat = b.roda(dias, dias, regime_fn, regime_kwargs, **geo_kwargs)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    from backtest.intraday.report import linha_de_resultado
    be_nom = 1.0 / (1.0 + geo_kwargs.get("alvo_multiplo", 3.0))
    sucesso, razoes = _criterio_sucesso(c)
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto": str(strat.stats_bruto),
        "sem_tend": str(strat.stats_sem_tendencia),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
        "sucesso": "SIM" if sucesso else "nao",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, proxy_nome=proxy_nome, regime_kwargs=regime_kwargs, geo_kwargs=geo_kwargs,
        c=c, linha=linha_res, equity_min=equity_min,
        bruto=strat.stats_bruto, sem_tend=strat.stats_sem_tendencia, emitidas=strat.stats_ordens_emitidas,
        sucesso=sucesso, razoes=razoes,
        stop_dist_mediana=(sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                            if c["stop_dist_pts"] else float("nan")),
    )


def _roda_lote(nome: str, variantes: list, dias: list) -> list[dict]:
    print(f"\n--- {nome} ({len(variantes)} variantes, {MAX_WORKERS} workers) ---", flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, pn, dict(rk), dict(gk), dias): rot
                for rot, pn, rk, gk in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            print(f"  {rot:<16} liquido={b.br(c['liquido']):>10}  bruto={r['bruto']:>5}  "
                  f"sem_tend={r['sem_tend']:>4}  emitidas={r['emitidas']:>4}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
                  f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
                  f"sucesso={r['sucesso']}", flush=True)
    return [resultados[rot] for rot, _, _, _ in variantes]


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _melhor(resultados: list[dict]) -> dict:
    nao_censurados = [r for r in resultados if not _censurado(r)]
    pool = nao_censurados if nao_censurados else resultados
    return max(pool, key=lambda r: r["c"]["liquido"])


def _retuna_geometria(proxy_nome: str, regime_kwargs: dict, dias: list, label: str) -> list[dict]:
    """Estagios B/C/D -- greedy sequencial, mesmo molde de G4."""
    todas = []
    geo = dict(GEOMETRIA_G4)
    variantes_b = [(f"{label} stop={s:.0f}", proxy_nome, regime_kwargs,
                    dict(geo, stop_pontos=s)) for s in (100.0, 150.0, 200.0)]
    res_b = _roda_lote(f"{label} ESTAGIO B -- stop_pontos", variantes_b, dias)
    todas += res_b
    venc_b = _melhor(res_b)
    geo = dict(venc_b["geo_kwargs"])

    variantes_c = [(f"{label} alvo={m:.0f}x", proxy_nome, regime_kwargs,
                    dict(geo, alvo_multiplo=m)) for m in (3.0, 5.0, 7.0)]
    res_c = _roda_lote(f"{label} ESTAGIO C -- alvo_multiplo", variantes_c, dias)
    todas += res_c
    venc_c = _melhor(res_c)
    geo = dict(venc_c["geo_kwargs"])

    variantes_d = [(f"{label} buffer={bp:.0f}", proxy_nome, regime_kwargs,
                    dict(geo, buffer_entrada_pontos=bp)) for bp in (0.0, 10.0, 20.0, 30.0)]
    res_d = _roda_lote(f"{label} ESTAGIO D -- buffer_entrada", variantes_d, dias)
    todas += res_d
    venc_d = _melhor(res_d)

    print(f"\n  >> vencedor da geometria ({label}): {venc_d['rotulo']} "
          f"liquido={b.br(venc_d['c']['liquido'])} censurado={_censurado(venc_d)}", flush=True)
    return todas, venc_d


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 140)
    print("WinBuscaLucroG05RegimeVol -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 140)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Criterio de SUCESSO: trades>127 E top3/liq<=40% E veredito win%=POSITIVO E liquido>0.\n", flush=True)

    todas_as_linhas = []

    # -- ESTAGIO 1: detector de cada proxy, geometria G4 fixa --------------
    variantes_a = [(rot, "A", kw, GEOMETRIA_G4) for rot, kw in PROXY_A_GRID]
    variantes_b = [(rot, "B", kw, GEOMETRIA_G4) for rot, kw in PROXY_B_GRID]
    variantes_c = [(rot, "C", kw, GEOMETRIA_G4) for rot, kw in PROXY_C_GRID]

    res_a1 = _roda_lote("ESTAGIO 1A -- proxy amplitude_bloco (R20)", variantes_a, dias)
    res_b1 = _roda_lote("ESTAGIO 1B -- proxy vela_extrema (R35)", variantes_b, dias)
    res_c1 = _roda_lote("ESTAGIO 1C -- proxy volume_bloco", variantes_c, dias)
    todas_as_linhas += res_a1 + res_b1 + res_c1

    venc_a1 = _melhor(res_a1)
    venc_b1 = _melhor(res_b1)
    venc_c1 = _melhor(res_c1)
    print(f"\n  >> detector vencedor A: {venc_a1['rotulo']} (censurado={_censurado(venc_a1)})")
    print(f"  >> detector vencedor B: {venc_b1['rotulo']} (censurado={_censurado(venc_b1)})")
    print(f"  >> detector vencedor C: {venc_c1['rotulo']} (censurado={_censurado(venc_c1)})", flush=True)

    # -- ESTAGIOS 2/3/4: retuna geometria em cima do detector vencedor -----
    linhas_a2, venc_a_final = _retuna_geometria("A", venc_a1["regime_kwargs"], dias, "A")
    linhas_b2, venc_b_final = _retuna_geometria("B", venc_b1["regime_kwargs"], dias, "B")
    linhas_c2, venc_c_final = _retuna_geometria("C", venc_c1["regime_kwargs"], dias, "C")
    todas_as_linhas += linhas_a2 + linhas_b2 + linhas_c2

    # -- REFERENCIA: G4 recalculada nesta geracao (mesma janela) -----------
    print("\n--- REFERENCIA -- G4 recalculada (continuacao, j20/q75, stop150/alvo3x/buffer30) ---", flush=True)
    res_g4, strat_g4 = b.roda_g04_referencia(
        dias, dias, janela_min=20, quantil=0.75,
        direcao_aposta="continuacao", stop_pontos=150.0, alvo_multiplo=3.0, buffer_entrada_pontos=30.0)
    trades_g4 = list(res_g4.trades)
    c_g4 = b.consistencia(trades_g4, dias)
    equity_min_g4 = float(res_g4.equity_curve.min()) if len(res_g4.equity_curve) else float("nan")
    from backtest.intraday.report import linha_de_resultado
    sucesso_g4, razoes_g4 = _criterio_sucesso(c_g4)
    extras_g4 = {
        "BEnom%": b.br(100 / 4, 1) + "%",
        "BEemp%": (b.br(100 * c_g4["be"], 1) + "%") if c_g4["be"] == c_g4["be"] else "--",
        "IC95 win": (f"[{b.br(100*c_g4['lo'],1)};{b.br(100*c_g4['hi'],1)}]" if c_g4["n"] else "--"),
        "veredito": c_g4["veredito"],
        "bruto": str(strat_g4.stats_bruto),
        "sem_tend": str(strat_g4.stats_contra_tendencia),
        "emit/brt": f"{strat_g4.stats_ordens_emitidas}/{strat_g4.stats_bruto}",
        "top3/liq": (b.br(100 * c_g4["concentracao_top3"], 0) + "%") if c_g4["concentracao_top3"] == c_g4["concentracao_top3"] else "--",
        "sem_tr": f"{c_g4['sem_trade']}/{c_g4['pregoes']}",
        "sucesso": "SIM" if sucesso_g4 else "nao",
    }
    linha_g4 = linha_de_resultado("REF G4 cruzado (recalc)", res_g4, b.CAPITAL, extras=extras_g4)
    todas_as_linhas.append(dict(rotulo="REF G4 cruzado (recalc)", c=c_g4, linha=linha_g4,
                                 equity_min=equity_min_g4, bruto=strat_g4.stats_bruto,
                                 sem_tend=strat_g4.stats_contra_tendencia,
                                 emitidas=strat_g4.stats_ordens_emitidas,
                                 sucesso=sucesso_g4, razoes=razoes_g4))
    print(f"  REF G4 cruzado (recalc)  liquido={b.br(c_g4['liquido'])}  trades={c_g4['n']}  "
          f"win={b.br(100*c_g4['win'],1) if c_g4['n'] else '--'}%  "
          f"top3/liq={b.br(100*c_g4['concentracao_top3'],0) if c_g4['concentracao_top3']==c_g4['concentracao_top3'] else '--'}%  "
          f"sucesso={sucesso_g4}", flush=True)

    # -- ENSEMBLE: >=2 dos 4 proxies concordam (geometria G4, sem retunar) --
    print("\n--- ENSEMBLE -- >=2 de {A,B,C,G4-cruzado} concordam na mesma barra (geometria G4) ---", flush=True)
    sys.path.insert(0, str(b.ROOT / "src"))
    from strategy.daytrade.lab import win_busca_lucro_g05_regime_vol as mod
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g05_regime_vol import WinBuscaLucroG05RegimeVol

    win_fatia = b.bars_dos_dias(win, dias)
    wdo_fatia = b.bars_dos_dias(b.carrega_wdo(), dias)
    r_a = getattr(mod, PROXY_FN["A"])(win_fatia, **venc_a1["regime_kwargs"]).astype(int)
    r_b = getattr(mod, PROXY_FN["B"])(win_fatia, **venc_b1["regime_kwargs"]).astype(int)
    r_c = getattr(mod, PROXY_FN["C"])(win_fatia, **venc_c1["regime_kwargs"]).astype(int)
    anomalo_g4, _ = estado_anomalo_cruzado(win_fatia["close"], wdo_fatia["close"], janela_min=20, quantil=0.75)
    r_g4 = anomalo_g4.astype(int)
    soma = r_a + r_b + r_c + r_g4
    ensemble = (soma >= 2)
    strat_ens = WinBuscaLucroG05RegimeVol(regime_ativo=ensemble, **GEOMETRIA_G4)
    cfg = b.monta_config(b.CAPITAL)
    res_ens = run_intraday_backtest(win_fatia, strat_ens, cfg)
    trades_ens = list(res_ens.trades)
    c_ens = b.consistencia(trades_ens, dias)
    equity_min_ens = float(res_ens.equity_curve.min()) if len(res_ens.equity_curve) else float("nan")
    sucesso_ens, razoes_ens = _criterio_sucesso(c_ens)
    extras_ens = {
        "BEnom%": b.br(100 / 4, 1) + "%",
        "BEemp%": (b.br(100 * c_ens["be"], 1) + "%") if c_ens["be"] == c_ens["be"] else "--",
        "IC95 win": (f"[{b.br(100*c_ens['lo'],1)};{b.br(100*c_ens['hi'],1)}]" if c_ens["n"] else "--"),
        "veredito": c_ens["veredito"],
        "bruto": str(strat_ens.stats_bruto),
        "sem_tend": str(strat_ens.stats_sem_tendencia),
        "emit/brt": f"{strat_ens.stats_ordens_emitidas}/{strat_ens.stats_bruto}",
        "top3/liq": (b.br(100 * c_ens["concentracao_top3"], 0) + "%") if c_ens["concentracao_top3"] == c_ens["concentracao_top3"] else "--",
        "sem_tr": f"{c_ens['sem_trade']}/{c_ens['pregoes']}",
        "sucesso": "SIM" if sucesso_ens else "nao",
    }
    linha_ens = linha_de_resultado("ENSEMBLE >=2/4", res_ens, b.CAPITAL, extras=extras_ens)
    todas_as_linhas.append(dict(rotulo="ENSEMBLE >=2/4", c=c_ens, linha=linha_ens,
                                 equity_min=equity_min_ens, bruto=strat_ens.stats_bruto,
                                 sem_tend=strat_ens.stats_sem_tendencia,
                                 emitidas=strat_ens.stats_ordens_emitidas,
                                 sucesso=sucesso_ens, razoes=razoes_ens))
    print(f"  ENSEMBLE >=2/4  liquido={b.br(c_ens['liquido'])}  trades={c_ens['n']}  "
          f"win={b.br(100*c_ens['win'],1) if c_ens['n'] else '--'}%  "
          f"top3/liq={b.br(100*c_ens['concentracao_top3'],0) if c_ens['concentracao_top3']==c_ens['concentracao_top3'] else '--'}%  "
          f"sucesso={sucesso_ens}", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "bruto", "sem_tend", "emit/brt",
              "top3/liq", "sem_tr", "sucesso")
    print("\n" + "=" * 140)
    print("TABELA CONSOLIDADA -- todas as variantes testadas no IS")
    print("=" * 140)
    print(tabela([r["linha"] for r in todas_as_linhas], extras=EXTRAS, largura_extra=10))

    candidatos_finais = [
        ("A (amplitude_bloco)", venc_a_final),
        ("B (vela_extrema/R35)", venc_b_final),
        ("C (volume_bloco)", venc_c_final),
        ("REF G4 cruzado", dict(rotulo="REF G4 cruzado (recalc)", c=c_g4, equity_min=equity_min_g4,
                                 sucesso=sucesso_g4, razoes=razoes_g4)),
        ("ENSEMBLE >=2/4", dict(rotulo="ENSEMBLE >=2/4", c=c_ens, equity_min=equity_min_ens,
                                 sucesso=sucesso_ens, razoes=razoes_ens)),
    ]
    print("\nCANDIDATOS FINAIS (um por proxy + referencia + ensemble):")
    aprovados = []
    for nome, r in candidatos_finais:
        cc = r["c"]
        print(f"  {nome:<24} {r['rotulo']:<28} liquido={b.br(cc['liquido']):>10}  trades={cc['n']:>4}  "
              f"win={b.br(100*cc['win'],1) if cc['n'] else '--':>6}%  "
              f"top3/liq={b.br(100*cc['concentracao_top3'],0) if cc['concentracao_top3']==cc['concentracao_top3'] else '--':>5}%  "
              f"sucesso={r['sucesso']}  razoes={r['razoes']}")
        if r["sucesso"]:
            aprovados.append((nome, r))

    print("\nVEREDITO DO PORTAO IS (criterio de sucesso do mandato, item 4):")
    if aprovados:
        for nome, r in aprovados:
            print(f"  -> {nome} BATE o criterio de sucesso -- candidato a promover ao OOS-1.")
    else:
        print("  -> NENHUM proxy/ensemble bate o criterio de sucesso completo no IS. "
              "Nao promove ninguem ao OOS-1 (protocolo: so' promove quem bate o criterio).")
    print("\nFIM.")


if __name__ == "__main__":
    main()
