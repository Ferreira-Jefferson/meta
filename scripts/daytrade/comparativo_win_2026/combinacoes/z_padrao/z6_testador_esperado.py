"""Z6: numero esperado no Testador para WinRetanguloEma34 v1.06 (M15 ajustado + filtro f3 k=0,5 + sem velas pos-pregao).
WINV26, 13/08/2026 -> 30/09/2026, "cada tick baseado em ticks reais", sem custo, R$1.000, 1 contrato.

Mesmo port padrao v1.06 (port_retangulo_ema34_padrao -> port_ret_tf_v2 tf=15 ajustes=True + port_z4.instala f3 0,5 sem_pos),
duas leituras (no B o ATR14 D1 e a amplitude do filtro saem do M1 do WINV26, como o EA no Testador):
  A) dados do comparativo (M1 e ticks do WIN$N; o aquecimento antes de 13/08 e' do contrato anterior);
  B) WINV26 puro (o que o Testador aquece): M1 do WINV26 (m1_WINV26.parquet, da Z1) para a EMA34 e o historico de
     velas pre-carregado, e os ticks reais do WINV26 em data/cache_win_ticks/WINV26 (shim da Z1).
Grava comparativo_win_2026/esperado_testador/WinRetanguloEma34_v106_esperado_testador_<WINV26|WINN>.csv.
Uso: python z6_testador_esperado.py [A|B]
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]                      # comparativo_win_2026/
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(AQUI))
import dados as D  # noqa: E402

INI, FIM = date(2026, 8, 13), date(2026, 9, 30)
OUT = BASE / "esperado_testador"

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "B"
    if modo == "B":
        import z1_testador_esperado as Z1
        S = Z1.shim_winv26()
        S.CAPITAL = D.CAPITAL
        sys.modules["dados"] = S
        D = S
    import port_retangulo_ema34_padrao as PP
    dias = [d for d in D.dias() if INI <= d <= FIM]
    ea = PP.roda(dias_lista=dias, verbose=False)
    df = pd.DataFrame(ea.trades, columns=D.COLUNAS)
    rot = "WINV26" if modo == "B" else "WINN"
    OUT.mkdir(exist_ok=True)
    f = OUT / f"WinRetanguloEma34_v106_esperado_testador_{rot}.csv"
    df.to_csv(f, index=False)
    print(f"== {rot}: {len(dias)} pregoes, {len(df)} ops, liquido R$ {df.rs.sum():.2f}, bloqueadas {PP.P.Ea.n_bloq} -> {f}", flush=True)
    print(df[["entrada", "lado", "saida", "preco_entrada", "preco_saida", "motivo", "rs"]].to_string(index=False), flush=True)
