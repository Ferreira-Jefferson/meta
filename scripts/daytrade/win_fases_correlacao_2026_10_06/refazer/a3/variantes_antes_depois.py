"""A3 refazer: WinCincoMedias v2.00..v2.03 por ano, ANTES (lib original, zera no call) x DEPOIS (lib sem leiloes).
         E/F = como D/C mas com o VOLUME bruto (isola o efeito da limpeza de volume)
Configs: A = original (win_cinco_medias, CSV WIN@ ajustado)       -> reproduz os numeros da memoria
         B = lib nova em modo legado (com leiloes) sobre WIN$N     -> separa o efeito da BASE
         C = lib nova SEM leiloes sobre WIN$N                       -> o numero corrigido
         D = lib nova SEM leiloes sobre WIN@ (CSV)                  -> corrigido na base original
         L = lib nova em modo legado sobre WIN@ (verifica que a lib nova == original)
Uso: python variantes_antes_depois.py  -> resultado.jsonl (uma linha por unidade, na ordem em que terminam)."""
import json, sys, io, contextlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DT = AQUI.parents[2]            # scripts/daytrade
sys.path.insert(0, str(DT))

VARIANTES = {
    "v2.00": dict(saida_vol=False, aperta=None, saida_st=None),
    "v2.01": dict(saida_vol=True, aperta=None, saida_st=None),
    "v2.02": dict(saida_vol=True, saida_st=None),
    "v2.03": dict(),
}
ANOS = (2022, 2023, 2024, 2025, 2026)


def unidade(cfg, ano):
    if cfg == "A":
        import win_cinco_medias as w
        w.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"; w.FIM_DADOS[2025] = "2025-10-01"
        for a in (2022, 2023, 2024):
            w.ARQUIVOS[a] = "WIN@_M1_202112010900_202412301824.csv"
        d = w.carregar(ano)
    else:
        import win_cinco_medias_semleilao as w
        if cfg == "B": d = w.carregar_bruta(ano, base="WIN$N")
        elif cfg == "L": d = w.carregar_bruta(ano, base="WIN@")
        elif cfg == "C": d = w.carregar(ano, base="WIN$N")
        elif cfg == "D": d = w.carregar(ano, base="WIN@")
        elif cfg in ("E", "F"):   # so' o PRECO/zeragem corrigidos; volume continua o bruto (com leilao e call) -> isola o efeito do volume
            bs = "WIN@" if cfg == "E" else "WIN$N"
            d = w.carregar(ano, base=bs); bruto = w.carregar_bruta(ano, base=bs)
            d["v"] = bruto["v"].reindex(d.index); d["tv"] = bruto["tv"].reindex(d.index)
    out = []
    for nome, kw in VARIANTES.items():
        _, r = w.rodar_janelas(ano, dados=d, **kw)
        r = {k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()}
        extra = {}
        if "proxy" in d.columns:
            ult = d[d.ultima_continua]
            extra = dict(dias=int(len(ult)), dias_proxy=int(ult.proxy.sum()))
        out.append(dict(cfg=cfg, ano=ano, variante=nome, **r, **extra))
    return out


if __name__ == "__main__":
    cfgs = sys.argv[1].split(",") if len(sys.argv) > 1 else ["A", "B", "C", "D", "E", "F", "L"]
    dest = AQUI / "resultado_variantes.jsonl"
    with ProcessPoolExecutor(max_workers=6) as ex, open(dest, "w", encoding="utf-8") as f:
        fut = {ex.submit(unidade, c, a): (c, a) for c in cfgs for a in ANOS}
        for x in as_completed(fut):
            for lin in x.result():
                f.write(json.dumps(lin) + "\n"); f.flush()
            print("ok", fut[x], flush=True)
