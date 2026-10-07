"""Gera os .ini da bateria de testes do WinMaestro no Testador do MT5.

11 testes, todos WINV26, M1, 13/08/2026 a 30/09/2026, "Todos os ticks" (Model=0,
ticks GERADOS -- os ticks reais do WINV26 na Rico descartam 85% dos minutos),
sem atraso, deposito R$1.000:
  M_GB, M_CM, M_DM, M_RE, M_C1  -> WinMaestro com um robo ligado
  M_TODOS                       -> WinMaestro com os 5 ligados
  A_GB, A_CM, A_DM, A_RE, A_C1  -> EA avulso de cada robo, inputs padrao

Uso: python gera_ini.py   (escreve em mt5/testes/ini/)
"""
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "ini"

ROBOS = {  # sigla -> EA avulso
    "GB": "WinGapBarra1",
    "CM": "WinCincoMedias",
    "DM": "WinDeslocamentoMatinal",
    "RE": "WinRetanguloEma34",
    "C1": "Win_c1",
}

BASE = """[Tester]
Expert={expert}.ex5
Symbol=WINV26
Period=M1
Optimization=0
Model=0
FromDate=2026.08.13
ToDate=2026.09.30
ForwardMode=0
Deposit=1000
Currency=BRL
ProfitInPips=0
Leverage=1
ExecutionMode=0
Visual=0
Report=testes_maestro\\{nome}
ReplaceReport=1
ShutdownTerminal=1
"""


def _ativos(ligados):
    linhas = ["[TesterInputs]"]
    for sigla in ROBOS:
        v = "true" if sigla in ligados else "false"
        linhas.append(f"Ativo_{sigla}={v}||false||0||true||N")
    return "\n".join(linhas) + "\n"


def main():
    SAIDA.mkdir(exist_ok=True)
    testes = {}
    for sigla in ROBOS:
        testes[f"M_{sigla}"] = BASE.format(expert="WinMaestro", nome=f"M_{sigla}") + _ativos({sigla})
    testes["M_TODOS"] = BASE.format(expert="WinMaestro", nome="M_TODOS") + _ativos(set(ROBOS))
    for sigla, ea in ROBOS.items():
        testes[f"A_{sigla}"] = BASE.format(expert=ea, nome=f"A_{sigla}")
    for nome, txt in testes.items():
        # O terminal grava os .ini dele em UTF-16 LE com BOM; lemos e escrevemos igual.
        with open(SAIDA / f"{nome}.ini", "w", encoding="utf-16", newline="\r\n") as f:
            f.write(txt)
    print(f"{len(testes)} arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
