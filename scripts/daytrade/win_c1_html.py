"""Monta .claude/artifacts/win_c1/index.html a partir de c1_dados.json (gerado por win_c1_dados.py) + painel de replay.
Uso: python win_c1_html.py"""
import json
from pathlib import Path
import pandas as pd
import win_replay_ticks as rp

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".claude" / "artifacts" / "win_c1"
dados = json.loads((OUT / "c1_dados.json").read_text(encoding="utf-8"))

# subtotais das janelas WIN@D (j2, j2be): fora da amostra (ate 11/08) x amostra (a partir de 12/08)
from win_c1_dados import BE
for j2 in (z for z in dados if z["ativo"] == "WIN@D"):
    tr = pd.DataFrame([dict(dia=d["dia"], tx=o["ts"], rs=o["rs"]) for d in j2["dias"] for o in d["ops"]])
    partes = []
    for nome, fora in (("02/06 a 11/08 (fora da amostra)", True), ("12/08 a 01/10 (janela da confluência)", False)):
        g = tr[(tr.dia < "2026-08-12") == fora]
        pregoes = [x.stem for x in (rp.CACHE / "WIN@D").glob("2026-*.pkl") if "2026-06-02" <= x.stem <= "2026-10-01" and (x.stem < "2026-08-12") == fora]
        partes.append(dict(nome=nome, **rp.metricas(g, len(pregoes))))
    j2["partes"] = partes
for z in dados:
    if z.get("be"):
        z["colchao"] = BE["be_colchao_pts"]

painel = Path(__file__).with_name("win_replay_painel.html").read_text(encoding="utf-8")
painel = painel.replace('id="rp-ini" value="2026-09-01"', 'id="rp-ini" value="2026-08-12"').replace('id="rp-fim" value="2026-09-30"', 'id="rp-fim" value="2026-10-01"')
painel = painel.replace("const INICIAL={...PADRAO};", "const INICIAL={...PADRAO,be_minutos:15};")   # a pagina C1 abre com o BE 15 min / 7 pts ligado
painel = painel.replace("winReplayHist", "winC1ReplayHist").replace("scripts/daytrade/win_replay_server.py", "scripts/daytrade/win_c1_server.py")

html = (Path(__file__).with_name("win_c1_modelo.html")).read_text(encoding="utf-8")
nota = Path(__file__).with_name("win_c1_nota.html")
nota_be = Path(__file__).with_name("win_c1_nota_be.html")
out = (html.replace("__NOTA_BE__", nota_be.read_text(encoding="utf-8") if nota_be.exists() else "")
       .replace("__NOTA__", nota.read_text(encoding="utf-8") if nota.exists() else "").replace("__PAINEL__", painel)
       .replace("__DADOS__", json.dumps(dados, ensure_ascii=False)))
(OUT / "index.html").write_text(out, encoding="utf-8")
print(OUT / "index.html", len(out) // 1024, "KB")
