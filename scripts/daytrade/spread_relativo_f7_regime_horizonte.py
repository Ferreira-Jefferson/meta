"""Frente F7 -- spread relativo WIN@ x WDO@: RODADA 2 (filtro de regime de
volatilidade + saida por horizonte fixo casado com o efeito validado).

Contexto (nao rederive -- ver docstrings de `spread_relativo_f7_investigate.py`
e `spread_relativo_f7_rule.py`, que este script IMPORTA em vez de duplicar):
o passo 1 achou 2 metricas do residuo win~wdo que sobrevivem ao nulo de
repareamento de dia -- variance ratio do NIVEL (q=30min, real=0,828, nulo
percentil 0%) e correlacao(z-score 30min, retorno futuro 15min) (real=
-0,0162, nulo percentil 0%, e o efeito FICOU MAIS FORTE na 2a metade:
-0,0082 -> -0,0266). A regra da rodada 1 (entrada por z-score, saida por
threshold/stop/timeout, ordem a mercado) ficou NEGATIVA em toda a grade
(-R$3.646 a -R$51.323 liquido, full-IS), o candidato de metade2 perde
R$15.291,66 com bruto pre-custo de so' -R$1.693,66 contra R$13.598,00 de
custo -- o nulo sign-flip colocou o real no percentil 20% (indistinguivel de
ruido de custo) e a calibracao nula (repareamento de dia) mostrou o par
VERDADEIRO perdendo MAIS que os 5 pares sinteticos.

O critico da rodada 1 apontou 2 angulos baratos e NAO testados ainda
(execucao maker/limite JA esta' descartada por cima pelo cenario
zero-slippage da rodada 1 -- nao retestar aqui):

  1. FILTRO DE REGIME DE VOLATILIDADE: o custo e' FIXO em R$/contrato, mas o
     edge deveria escalar com o tamanho do movimento -- restringir a entrada
     ao TERCO de MAIOR volatilidade realizada do residuo por pregao (corte
     definido SO' na 1a metade do IS, aplicado sem reajuste na 2a) deveria
     melhorar a razao edge/custo.
  2. SAIDA CASADA COM O HORIZONTE VALIDADO: a regra da rodada 1 sai por
     threshold/stop/timeout -- uma logica DIFERENTE da janela onde o efeito
     foi de fato medido e sobreviveu ao nulo (corr(z, fwd15), horizonte FIXO
     de 15 minutos). Trocar a saida por horizonte fixo de 15min testa se a
     saida antiga estava deixando bruto na mesa por desalinhamento de janela.

Ultima rodada disponivel para esta frente (rodada 2 de no maximo 3; NAO ha'
rodada 3 para mais uma tentativa depois desta). Decisao objetiva pedida pelo
critico: reportar BRUTO antes do custo nas combinacoes de filtro (on/off) x
saida (threshold/horizonte); se nem no "melhor caso" (alta vol + horizonte
casado) o bruto superar claramente o piso de custo, ABANDON com a evidencia.

Disciplina mantida identica a' rodada 1 (nada disso e' relaxado aqui):
  - Beta (a,b) estimado SO' na 1a metade do IS -- reaproveitado tal e qual
    (mesma instancia de `estimar_beta`, mesmo resultado numerico) da rodada
    1, nunca reajustado.
  - O CORTE de regime (percentil 67 da volatilidade realizada por pregao) e'
    calculado SO' na distribuicao da 1a metade e aplicado como o MESMO
    numero na 2a metade -- nunca recalculado la'.
  - Custo das DUAS pernas (tarifa fixa + slippage de 1 tick por fill,
    default realista) sempre aplicado; nenhum numero de bruto e' reportado
    como se fosse o resultado.
  - Nulo sign-flip correto (bruto_d sorteado, custo_d nunca invertido) e
    calibracao nula por repareamento de dia rodados no candidato final,
    mesmas formulas e mesmo numero minimo de sementes da rodada 1.
  - OOS (`>=2026-06-13`) nunca tocado -- `carregar_is` (importado, nao
    reescrito) so' chama `.in_sample()`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import spread_relativo_f7_rule as f7  # noqa: E402 -- reaproveita rodada 1, nao duplica

HORIZONTE_FIXO = 15  # mesma janela de `corr(z, fwd15)` do passo 1 (a que sobreviveu ao nulo)
TERCO = 2 / 3         # corte "alto" = percentil 67 da vol realizada por pregao


# ============================ regime de volatilidade ==========================

def vol_do_dia(dia: pd.DataFrame, a: float, b: float) -> float:
    """Desvio-padrao (ddof=1) do retorno-residuo (win_r - a - b*wdo_r) DENTRO
    do pregao -- "volatilidade realizada do spread residual por pregao"
    pedida pelo critico. Usa o MESMO `a,b` (fixo, vindo da 1a metade) para
    todo dia, nunca reestima por dia."""
    win_r, wdo_r = f7.retornos(dia)
    spread_r = win_r - a - b * wdo_r
    if len(spread_r) < 2:
        return float("nan")
    return float(np.std(spread_r, ddof=1))


def vols_por_dia(dias: dict, subset: list, a: float, b: float) -> dict:
    return {d: vol_do_dia(dias[d], a, b) for d in subset}


def corte_alto_terco(vols_subset: dict) -> float:
    """Percentil 67 da volatilidade DENTRO do subset passado -- chamar so'
    com a 1a metade; o numero devolvido e' reaplicado literalmente na 2a."""
    vals = np.array(list(vols_subset.values()), dtype=float)
    return float(np.quantile(vals, TERCO))


def dias_do_terco_alto(vols_subset: dict, corte_alto: float) -> list:
    """Dias cujo `vols_subset[d] > corte_alto` -- `corte_alto` e' sempre um
    numero JA CALCULADO em outro subset (a 1a metade), nunca recomputado
    aqui dentro."""
    return sorted(d for d, v in vols_subset.items() if v > corte_alto)


# ============================ saida por horizonte fixo =========================

def simular_dia_horizonte(dia: pd.DataFrame, z: np.ndarray, entry_z: float, n_win: int,
                           n_wdo: int, horizonte: int = HORIZONTE_FIXO,
                           slippage_ticks: float | None = None) -> list[dict]:
    """Mesmo gatilho de entrada de `f7.simular_dia` (|z|>entry_z, executa no
    open da barra seguinte), mas a SAIDA e' SEMPRE `horizonte` barras depois
    da entrada (open da barra `entry_i+1+horizonte`) -- nunca por
    threshold/stop/timeout. Casa a saida com a janela onde
    `corr(z, fwd15)` foi de fato medida e sobreviveu ao nulo no passo 1.
    Flatten forcado no ultimo close do dia se nao houver barra suficiente
    para completar o horizonte (mesma disciplina de fim de sessao)."""
    n = len(z)
    win_open = dia["win_open"].to_numpy(float)
    wdo_open = dia["wdo_open"].to_numpy(float)
    win_close = dia["win_close"].to_numpy(float)
    wdo_close = dia["wdo_close"].to_numpy(float)

    trades = []
    fee_total = f7.FEE_ROUND_TRIP_BRL * (n_win + n_wdo)

    def custo_par() -> float:
        return fee_total + f7._custo_fill(n_win, n_wdo, slippage_ticks) * 2

    def fechar(sinal: float, entry_win_px: float, entry_wdo_px: float,
               exit_win_px: float, exit_wdo_px: float) -> None:
        bruto = (
            sinal * (exit_win_px - entry_win_px) * f7.POINT_VALUE_BRL["WIN@"] * n_win
            + sinal * (exit_wdo_px - entry_wdo_px) * f7.POINT_VALUE_BRL["WDO@"] * n_wdo
        )
        trades.append({"bruto_brl": bruto, "custo_brl": custo_par()})

    i = f7.JANELA_Z
    estado = None
    entry_i = entry_win_px = entry_wdo_px = None
    while i < n - 1:
        if estado is None:
            zi = z[i]
            if not np.isnan(zi):
                if zi > entry_z:
                    estado = "short"
                elif zi < -entry_z:
                    estado = "long"
                if estado is not None:
                    entry_i = i
                    entry_win_px, entry_wdo_px = win_open[i + 1], wdo_open[i + 1]
        else:
            saida_i = entry_i + 1 + horizonte  # barra que executa a saida no OPEN
            if saida_i < n:
                sinal = 1.0 if estado == "long" else -1.0
                fechar(sinal, entry_win_px, entry_wdo_px, win_open[saida_i], wdo_open[saida_i])
                estado = None
                i = saida_i  # nao reabre sinal dentro da propria janela de saida
                continue
            elif i == n - 2:
                # dado acaba antes do horizonte completar -- flatten forcado
                sinal = 1.0 if estado == "long" else -1.0
                fechar(sinal, entry_win_px, entry_wdo_px, win_close[-1], wdo_close[-1])
                estado = None
        i += 1

    if estado is not None:
        sinal = 1.0 if estado == "long" else -1.0
        fechar(sinal, entry_win_px, entry_wdo_px, win_close[-1], wdo_close[-1])

    return trades


def rodar_regra_horizonte(dias: dict, subset: list, a: float, b: float, entry_z: float,
                           n_win: int, n_wdo: int, horizonte: int = HORIZONTE_FIXO,
                           slippage_ticks: float | None = None) -> dict:
    por_dia = {}
    for d in subset:
        _, z = f7.nivel_e_z(dias[d], a, b, f7.JANELA_Z)
        trades = simular_dia_horizonte(dias[d], z, entry_z, n_win, n_wdo, horizonte, slippage_ticks)
        if trades:
            por_dia[d] = trades
    return por_dia


# ============================ orquestracao ====================================

def resumo_com_por_trade(por_dia: dict) -> dict:
    r = f7.resumo(por_dia)
    r["bruto_por_trade"] = r["bruto"] / r["trades"] if r["trades"] else float("nan")
    r["custo_por_trade"] = r["custo"] / r["trades"] if r["trades"] else float("nan")
    return r


def rodar_variante(exit_style: str, filtro: str, dias: dict, subset: list,
                    dias_permitidos: set | None, a: float, b: float, entry_z: float,
                    n_win: int, n_wdo: int) -> dict:
    if filtro == "terco_alto_vol":
        subset_uso = [d for d in subset if d in dias_permitidos]
    else:
        subset_uso = subset
    if exit_style == "horizonte15":
        por_dia = rodar_regra_horizonte(dias, subset_uso, a, b, entry_z, n_win, n_wdo)
    else:
        por_dia = f7.rodar_regra(dias, subset_uso, a, b, entry_z, n_win, n_wdo)
    return resumo_com_por_trade(por_dia), por_dia


def main() -> None:
    win_is = f7.carregar_is("WIN@")
    wdo_is = f7.carregar_is("WDO@")
    dias = f7.montar_dias_comuns(win_is, wdo_is)
    ordenados = sorted(dias)
    meio = ordenados[len(ordenados) // 2]
    metade1 = [d for d in ordenados if d < meio]
    metade2 = [d for d in ordenados if d >= meio]
    print(f"[f7-r2] dias comuns: {len(ordenados)} | metade1={len(metade1)} "
          f"({metade1[0]}..{metade1[-1]}) | metade2={len(metade2)} "
          f"({metade2[0]}..{metade2[-1]})")

    a_h1, b_h1 = f7.estimar_beta(dias, metade1)
    print(f"[hedge] beta so' 1a metade (reaproveitado tal e qual da rodada 1) = {b_h1:.4f}")

    # ---- corte de regime: calculado SO' na 1a metade, aplicado sem reajuste ----
    vols_h1 = vols_por_dia(dias, metade1, a_h1, b_h1)
    corte_alto = corte_alto_terco(vols_h1)
    dias_h1_alto = set(dias_do_terco_alto(vols_h1, corte_alto))
    vols_h2 = vols_por_dia(dias, metade2, a_h1, b_h1)
    dias_h2_alto = set(dias_do_terco_alto(vols_h2, corte_alto))
    print(f"[regime] corte (percentil 67 da vol diaria do residuo, so' 1a metade) = "
          f"{corte_alto:.6f}")
    print(f"[regime] dias no terco alto: 1a metade={len(dias_h1_alto)}/{len(metade1)} "
          f"(auto, referencia) | 2a metade={len(dias_h2_alto)}/{len(metade2)} "
          f"(corte importado, sem reajuste -- decisivo)")

    # ---- piso de custo por round-trip (referencia impressa uma vez) ----
    for n_win, n_wdo in [(1, 1), (2, 1)]:
        fee = f7.FEE_ROUND_TRIP_BRL * (n_win + n_wdo)
        slip = f7._custo_fill(n_win, n_wdo) * 2
        print(f"[piso de custo] {n_win}W:{n_wdo}D -> fee={f7.num_br(fee, 2)} + "
              f"slippage(1 tick x 4 fills)={f7.num_br(slip, 2)} = "
              f"{f7.num_br(fee + slip, 2)} por round-trip fechado")

    razoes = [(1, 1), (2, 1)]
    entry_zs = [1.0, 1.5, 2.0]
    exit_styles = ["threshold", "horizonte15"]
    filtros = ["todos_os_dias", "terco_alto_vol"]

    linhas = []
    resultados_h2 = {}  # (exit_style, filtro, razao, entry_z) -> por_dia (para nulo/repareamento)
    for exit_style in exit_styles:
        for filtro in filtros:
            for n_win, n_wdo in razoes:
                for ez in entry_zs:
                    r_h1, _ = rodar_variante(exit_style, filtro, dias, metade1, dias_h1_alto,
                                              a_h1, b_h1, ez, n_win, n_wdo)
                    r_h2, por_dia_h2 = rodar_variante(exit_style, filtro, dias, metade2, dias_h2_alto,
                                                       a_h1, b_h1, ez, n_win, n_wdo)
                    resultados_h2[(exit_style, filtro, n_win, n_wdo, ez)] = por_dia_h2
                    linhas.append({
                        "saida": exit_style, "filtro": filtro, "razao": f"{n_win}W:{n_wdo}D",
                        "entry_z": ez,
                        "h1_trades": r_h1["trades"], "h1_bruto": r_h1["bruto"],
                        "h1_custo": r_h1["custo"], "h1_liq": r_h1["liquido"],
                        "h2_trades": r_h2["trades"], "h2_bruto": r_h2["bruto"],
                        "h2_custo": r_h2["custo"], "h2_liq": r_h2["liquido"],
                        "h2_bruto_trd": r_h2["bruto_por_trade"], "h2_custo_trd": r_h2["custo_por_trade"],
                    })

    tab = pd.DataFrame(linhas)
    fmt = {c: (lambda x: f7.num_br(x, 2)) for c in
           ["h1_bruto", "h1_custo", "h1_liq", "h2_bruto", "h2_custo", "h2_liq",
            "h2_bruto_trd", "h2_custo_trd"]}
    print("\n[GRADE COMPLETA] bruto/custo/liquido R$ -- metade1 (auto) e metade2 "
          "(fora da amostra, beta E corte de regime da 1a metade, sem reajuste). "
          "'h2_bruto_trd' vs 'h2_custo_trd' e' o teste decisivo desta rodada "
          "(bruto por trade tem que superar CLARAMENTE o custo por trade):")
    print(tab.to_string(index=False, formatters=fmt))

    # ---- foco no "melhor caso" pedido pelo critico: alta vol + horizonte casado ----
    melhor_caso = tab[(tab["saida"] == "horizonte15") & (tab["filtro"] == "terco_alto_vol")]
    print("\n[MELHOR CASO] saida=horizonte15 (casada com corr(z,fwd15) do passo 1) x "
          "filtro=terco_alto_vol (regime de maior volatilidade realizada):")
    print(melhor_caso.to_string(index=False, formatters=fmt))

    linha_melhor = melhor_caso.loc[melhor_caso["h2_bruto_trd"].idxmax()]
    print(f"\n[decisao] maior bruto/trade no melhor caso: razao={linha_melhor['razao']} "
          f"entry_z={linha_melhor['entry_z']} -> bruto/trade={f7.num_br(linha_melhor['h2_bruto_trd'], 2)} "
          f"vs custo/trade={f7.num_br(linha_melhor['h2_custo_trd'], 2)} "
          f"({int(linha_melhor['h2_trades'])} trades em {len(dias_h2_alto)} pregoes de alta vol)")
    supera_custo = linha_melhor["h2_bruto_trd"] > linha_melhor["h2_custo_trd"]
    print(f"[decisao] bruto/trade supera custo/trade no melhor caso? {'SIM' if supera_custo else 'NAO'}")

    # ---- candidato final desta rodada: maior h2_liq em TODA a grade (as 4 combinacoes) ----
    linha_candidato = tab.loc[tab["h2_liq"].idxmax()]
    print(f"\n[candidato final] maior liquido em metade2 (fora da amostra) em toda a grade "
          f"desta rodada: saida={linha_candidato['saida']} filtro={linha_candidato['filtro']} "
          f"razao={linha_candidato['razao']} entry_z={linha_candidato['entry_z']} "
          f"liquido={f7.num_br(linha_candidato['h2_liq'], 2)} bruto={f7.num_br(linha_candidato['h2_bruto'], 2)} "
          f"custo={f7.num_br(linha_candidato['h2_custo'], 2)} ({int(linha_candidato['h2_trades'])} trades)")

    chave = (linha_candidato["saida"], linha_candidato["filtro"],
             int(linha_candidato["razao"].split("W:")[0]),
             int(linha_candidato["razao"].split(":")[1].replace("D", "")),
             float(linha_candidato["entry_z"]))
    por_dia_candidato = resultados_h2[chave]

    # ---- nulo sign-flip (regra 5) no candidato final ----
    bruto_d, custo_d = f7.bruto_custo_por_dia(por_dia_candidato)
    liquido_real = float(np.sum(bruto_d) - np.sum(custo_d))
    n_seeds = 500
    nulo = f7.nulo_sign_flip(bruto_d, custo_d, n_sementes=n_seeds)
    pct = 100.0 * (nulo < liquido_real).mean()
    print(f"\n[NULO sign-flip] candidato final, {len(bruto_d)} pregoes-com-trade, {n_seeds} sementes:")
    print(f"  liquido real = {f7.num_br(liquido_real, 2)}")
    print(f"  nulo: media={f7.num_br(nulo.mean(), 2)}  min={f7.num_br(nulo.min(), 2)}  "
          f"max={f7.num_br(nulo.max(), 2)}  dp={f7.num_br(nulo.std(ddof=1), 2)}  n={n_seeds}")
    print(f"  percentil do real no nulo = {pct:.1f}%")

    # ---- calibracao nula (regra 8): mesma regra sobre repareamento de dia ----
    exit_style_c, filtro_c, n_win_c, n_wdo_c, ez_c = chave
    print(f"\n[CALIBRACAO NULA] mesma regra (saida={exit_style_c} filtro={filtro_c} "
          f"razao={n_win_c}W:{n_wdo_c}D entry_z={ez_c}) sobre repareamento de dia, 5 sementes, "
          f"aplicada na metade2 (filtro de regime recomputado DENTRO de cada repareamento, "
          f"usando o mesmo corte numerico -- so' a perna WDO troca de dia):")
    subset_c = sorted(dias_h2_alto) if filtro_c == "terco_alto_vol" else metade2
    liquidos_calib = []
    for seed in range(5):
        fake = f7.dias_repareados(dias, metade2, seed)
        if filtro_c == "terco_alto_vol":
            vols_fake = vols_por_dia(fake, metade2, a_h1, b_h1)
            subset_fake = dias_do_terco_alto(vols_fake, corte_alto)
        else:
            subset_fake = metade2
        r_fake, _ = rodar_variante(exit_style_c, "todos_os_dias", fake, subset_fake, None,
                                    a_h1, b_h1, ez_c, n_win_c, n_wdo_c)
        liquidos_calib.append(r_fake["liquido"])
        print(f"  seed={seed}: liquido={f7.num_br(r_fake['liquido'], 2)}  trades={r_fake['trades']}")
    liquidos_calib = np.array(liquidos_calib)
    print(f"  real (par verdadeiro) = {f7.num_br(liquido_real, 2)}  |  repareado: "
          f"media={f7.num_br(liquidos_calib.mean(), 2)} min={f7.num_br(liquidos_calib.min(), 2)} "
          f"max={f7.num_br(liquidos_calib.max(), 2)}")

    print(f"\n[VEREDITO] {len(subset_c)} pregoes no subset do candidato final. "
          f"{'Ver acima -- ' if supera_custo else 'bruto/trade NAO supera custo/trade no melhor caso; '}"
          "combinado com a grade completa (24 combinacoes) acima, ver relatorio para a decisao "
          "CONTINUE/ABANDON desta frente.")


if __name__ == "__main__":
    main()
