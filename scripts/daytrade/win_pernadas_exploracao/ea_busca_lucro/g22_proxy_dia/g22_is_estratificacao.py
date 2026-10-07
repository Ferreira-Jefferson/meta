# -*- coding: utf-8 -*-
"""Geracao 22 -- estratificacao POS-HOC do vencedor da G21 (retangulo,
stop=0,45xL/alvo=2,0x, capital R$1.000) por 4 proxies DIARIOS causais, no IS
(jan-jun/2026, 122 pregoes).

Protocolo (item 3 do mandato -- NUNCA simulacoes exclusivas separadas, mesma
lesson do item 6.50 de LICOES_DE_PRODUCAO.md): roda a G21 UMA UNICA VEZ sem
filtro de dia, registra os 4 proxies de cada pregao, e SO' DEPOIS particiona
os MESMOS trades ja ocorridos pelo proxy.

Proxies:
  (a) amplitude_ontem     -- high-low do pregao anterior do WIN@ (3 grupos)
  (b) gap_abertura        -- |abertura hoje - fechamento ontem| do WIN@ (3 grupos)
  (c) dia_semana          -- segunda/sexta vs meio de semana (2 grupos)
  (d) wdo_range_abertura  -- high-low dos 1os 30min do WDO@ no mesmo dia (3 grupos)

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g22_proxy_dia/g22_is_estratificacao.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g22_base as b  # noqa: E402


def _formata_grupo(m: dict) -> str:
    win_pct = f"{100*m['win']:.1f}" if m['win'] == m['win'] else "--"
    be_pct = f"{100*m['be']:.1f}" if m['be'] == m['be'] else "--"
    lo_pct = f"{100*m['lo']:.1f}" if m['lo'] == m['lo'] else "--"
    hi_pct = f"{100*m['hi']:.1f}" if m['hi'] == m['hi'] else "--"
    top3_pct = f"{100*m['top3']:.0f}" if m['top3'] == m['top3'] else "--"
    return (
        f"    grupo={m['rotulo']:<14} dias={m['n_dias']:>3} "
        f"(com_trade={m['com_trade']:>3}/sem_trade={m['sem_trade']:>3})  "
        f"n_trades={m['n_trades']:>4}  liquido={b.br(m['liquido']):>10}  "
        f"R$/pregao={b.br(m['liquido_por_pregao']):>8}  "
        f"R$/pregao_operado={b.br(m['liquido_por_pregao_operado']):>8}  "
        f"win={win_pct:>5}%  BEemp={be_pct:>5}%  IC95=[{lo_pct};{hi_pct}]  "
        f"veredito={m['veredito']:<10}  top3/liq={top3_pct:>5}%"
    )


def _roda_proxy(nome: str, grupos_dias: dict, trades: list, serie_total) -> None:
    print(f"\n--- Proxy: {nome} ---")
    metricas = {}
    for rotulo, dias_grupo in grupos_dias.items():
        m = b.metricas_por_grupo(trades, dias_grupo, str(rotulo))
        metricas[rotulo] = m
        print(_formata_grupo(m))
    obs, p = b.permutation_test_grupos(serie_total, grupos_dias, n_perm=5000, seed=0)
    print(f"    permutacao (amplitude das medias R$/pregao entre grupos): "
          f"observado={b.br(obs)}  p={p:.4f}  "
          f"(H0: a particao em grupos nao importa -- rotulo e' so' etiqueta)")


def main() -> None:
    win_full = b.carrega_win()
    wdo_full = b.carrega_wdo()
    dias_is = b.dias_da_janela(win_full, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Geracao 22 -- estratificacao IS (jan-jun/2026, {len(dias_is)} pregoes). "
          f"Rodando a G21 vencedora (stop=0,45xL/alvo=2,0x, capital R$1.000) "
          f"UMA VEZ, sem filtro de dia...\n", flush=True)

    res, strat = b.roda_g21_vencedor(dias_is)
    trades = list(res.trades)
    c_ref = b.consistencia(trades, dias_is)
    serie_total = c_ref["serie"]
    print(f"Referencia (sem filtro, = G21 ja registrada em ORQUESTRACAO.md): "
          f"liquido={b.br(c_ref['liquido'])}  n={c_ref['n']}  win={100*c_ref['win']:.1f}%  "
          f"BEemp={100*c_ref['be']:.1f}%  veredito={c_ref['veredito']}  "
          f"top3/liq={100*c_ref['concentracao_top3']:.0f}%  "
          f"sem_trade={c_ref['sem_trade']}/{c_ref['pregoes']}", flush=True)

    proxies = b.calcula_proxies(dias_is, win_full, wdo_full)
    faltantes = proxies.isna().sum()
    print(f"\nProxies com NaN (dias excluidos da estratificacao daquele proxy): "
          f"{dict(faltantes[faltantes > 0])}" if faltantes.sum() else
          "\nNenhum proxy com NaN.", flush=True)

    # (a) amplitude do pregao anterior -- 3 grupos (tercis)
    rot_a, c1_a, c2_a = b.tercis_com_corte(proxies["amplitude_ontem"])
    grupos_a = {
        f"baixo(<{c1_a:.0f}pts)": list(proxies.index[rot_a == 0]),
        f"medio[{c1_a:.0f};{c2_a:.0f}]pts": list(proxies.index[rot_a == 1]),
        f"alto(>{c2_a:.0f}pts)": list(proxies.index[rot_a == 2]),
    }
    _roda_proxy("(a) amplitude_ontem (high-low do pregao anterior, WIN@)",
                grupos_a, trades, serie_total)

    # (b) gap de abertura -- 3 grupos (tercis)
    rot_b, c1_b, c2_b = b.tercis_com_corte(proxies["gap_abertura"])
    grupos_b = {
        f"baixo(<{c1_b:.0f}pts)": list(proxies.index[rot_b == 0]),
        f"medio[{c1_b:.0f};{c2_b:.0f}]pts": list(proxies.index[rot_b == 1]),
        f"alto(>{c2_b:.0f}pts)": list(proxies.index[rot_b == 2]),
    }
    _roda_proxy("(b) gap_abertura (|abertura hoje - fechamento ontem|, WIN@)",
                grupos_b, trades, serie_total)

    # (c) dia da semana -- 2 grupos (segunda/sexta vs meio de semana)
    seg_sex = [d for d in proxies.index if proxies.loc[d, "dia_semana"] in (0, 4)]
    meio = [d for d in proxies.index if proxies.loc[d, "dia_semana"] in (1, 2, 3)]
    grupos_c = {"seg_sex": seg_sex, "meio_semana(ter-qui)": meio}
    _roda_proxy("(c) dia_semana (segunda/sexta vs ter-qui)", grupos_c, trades, serie_total)

    # (d) range de abertura do WDO@ (30min) -- 3 grupos (tercis)
    rot_d, c1_d, c2_d = b.tercis_com_corte(proxies["wdo_range_abertura"])
    grupos_d = {
        f"baixo(<{c1_d:.0f}pts)": list(proxies.index[rot_d == 0]),
        f"medio[{c1_d:.0f};{c2_d:.0f}]pts": list(proxies.index[rot_d == 1]),
        f"alto(>{c2_d:.0f}pts)": list(proxies.index[rot_d == 2]),
    }
    _roda_proxy("(d) wdo_range_abertura (high-low dos 1os 30min do WDO@)",
                grupos_d, trades, serie_total)

    print("\n--- Limiares congelaveis (numeros ABSOLUTOS, para repetir no OOS-1 sem reajustar) ---")
    print(f"  amplitude_ontem: c1={c1_a:.1f}pts  c2={c2_a:.1f}pts")
    print(f"  gap_abertura:    c1={c1_b:.1f}pts  c2={c2_b:.1f}pts")
    print(f"  wdo_range_abertura: c1={c1_d:.1f}pts  c2={c2_d:.1f}pts")


if __name__ == "__main__":
    main()
