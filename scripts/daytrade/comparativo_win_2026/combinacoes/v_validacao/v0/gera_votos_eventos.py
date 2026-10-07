"""V0 -- votos_val.parquet e eventos_val.parquet de 2024-01-02..2025-09-30, reaproveitando f0_fundacao/votos.py e
eventos.py SEM editar (shim `dados` + monkeypatch dos caminhos).
WdoRetangulo EXCLUIDO pelo dono: mantem-se a estrutura de 6 estrategias, com WdoRetangulo NEUTRO: voto 0, forca 0,
ret 0, posicao 0, sinal 0 e sem operacoes em eventos. Consequencias nos eventos: 'neutro' conta o WdoRetangulo (+1
constante em todas as linhas que nao sao dele) e 'favor/contra' nunca o contam.
Uso: python gera_votos_eventos.py [votos|eventos|teste]"""
import sys, types
from pathlib import Path
import numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados_val
sys.modules["dados"] = dados_val
BASE = AQUI.parents[2]
F0 = BASE / "combinacoes" / "f0_fundacao"
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(F0))
sys.modules["port_wdo_retangulo"] = types.ModuleType("port_wdo_retangulo")   # WdoRetangulo excluido
import votos as V
import eventos as E

V.ARQ = AQUI / "votos_val.parquet"; E.ARQ_VOTOS = V.ARQ; E.ARQ = AQUI / "eventos_val.parquet"


def wdo_neutro(m1, idx):
    z = np.zeros(len(idx)); return z, z.copy(), z.copy()
V.votos_wdo_ret = wdo_neutro
_pos0 = V.posicoes
def posicoes(idx, nome):
    if nome == "WdoRetangulo":
        z = np.zeros(len(idx)); return z, z.copy()
    t = pd.read_csv(AQUI / "resultados" / f"{nome}.csv")
    te = pd.to_datetime(t.entrada, format="mixed").values; tx = pd.to_datetime(t.saida, format="mixed").values
    fim = (idx + pd.Timedelta(minutes=1)).values
    posicao = np.zeros(len(idx)); sinal = np.zeros(len(idx))
    a = np.searchsorted(fim, te, side="right"); z = np.searchsorted(fim, tx, side="right")
    ks = np.searchsorted(idx.values, te, side="right") - 1
    for i in range(len(t)):
        posicao[a[i]:z[i]] = t.lado.iloc[i]
        if ks[i] >= 0: sinal[ks[i]] = t.lado.iloc[i]
    return posicao, sinal
V.posicoes = posicoes   # mesma logica de f0 (copiada so' para trocar a pasta de resultados)

def carrega_entradas():
    fs = [pd.read_csv(AQUI / "resultados" / f"{nm}.csv") for nm in V.ESTRATEGIAS if nm != "WdoRetangulo"]
    df = pd.concat(fs, ignore_index=True)
    df["entrada"] = pd.to_datetime(df.entrada, format="mixed"); df["saida"] = pd.to_datetime(df.saida, format="mixed")
    df["t_entrada_ms"] = df.entrada.values.astype("datetime64[ms]").astype(np.int64)
    df["t_saida_ms"] = df.saida.values.astype("datetime64[ms]").astype(np.int64)
    return df.drop(columns=["qtd"]).sort_values(["entrada", "estrategia"], kind="stable").reset_index(drop=True)
E.carrega_entradas = carrega_entradas

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "votos"
    if modo == "votos": V.gerar()
    elif modo == "eventos": E.gerar()
    else:
        f = V.teste_sem_futuro()
        print("TESTE SEM-FUTURO:", "OK" if not f else f"FALHOU {f}", flush=True)
