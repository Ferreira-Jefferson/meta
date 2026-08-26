"""Ciclo de vida do TERMINAL MT5 -- abrir ja' com o AutoTrading ligado.

Existe por causa de 25/08/2026: o terminal subiu com o botao AutoTrading
DESLIGADO e a primeira ordem do pregao do slot `dt-gremah_tick-pmam3-live`
morreu com `retcode=10027 AutoTrading disabled by client`, sem chegar na
corretora. `IntradayLiveRuntime._check_autotrading` passou a RECUSAR o pregao
nesse caso (melhor do que perder ordem em silencio), e este modulo e' a outra
metade: fazer o estado certo acontecer em vez de so' reclamar dele.

POR QUE PASSA PELO ARQUIVO DE CONFIG, e nao por um "liga o botao":

  - a API do MetaTrader5 so' LE (`terminal_info().trade_allowed`); nao ha
    funcao para ligar (ver `MT5Broker.autotrading_allowed`);
  - `PostMessage(Ctrl+E)` na janela do terminal e' ignorado (o acelerador
    confere o teclado REAL);
  - `SendInput(Ctrl+E)` envia, mas o Windows recusa dar o foco ao terminal
    para um processo de segundo plano (`SetForegroundWindow` -> 0): as teclas
    caem na janela que o dono estiver usando. Medido nesta maquina em
    2026-08-25 -- injetar tecla as cegas na janela errada e' pior que nao
    operar.

O estado mora em `<data_dir>/config/common.ini`, secao `[Experts]`, chave
`Enabled`. O terminal LE esse arquivo ao abrir e o REESCREVE ao fechar --
por isso este modulo so' mexe nele com o terminal FECHADO, e o efeito vale a
partir da proxima abertura.

TERMINAL JA ABERTO COM O BOTAO DESLIGADO NAO E' RESOLVIDO AQUI, de proposito:
a saida seria fechar o terminal para reescrever o arquivo, e fechar um
terminal aberto pode derrubar ordem pendente, posicao vigiada e a conexao dos
outros robos. Nesse caso este modulo diz o que fazer (Ctrl+E) e nao faz nada.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Classe da janela principal do terminal MT5 -- e' o jeito de saber se HA um
#: terminal aberto sem chamar `mt5.initialize()`, que ABRIRIA um se nao
#: houvesse (exatamente o que nao queremos antes de conferir o config).
_WINDOW_CLASS = "MetaQuotes::MetaTrader::5.00"

#: `common.ini` e' UTF-16 com BOM (escrito pelo terminal). Ler/gravar em
#: outra coisa corrompe o arquivo inteiro, nao so' a linha tocada.
_INI_ENCODING = "utf-16"


@dataclass(frozen=True)
class ResultadoTerminal:
    """`ok`: da' para operar agora (terminal aberto e AutoTrading ligado).
    `acao`: o que este modulo fez, para o chamador logar/mostrar.
    `motivo`: texto pronto para o dono ler quando `ok` e' `False`."""

    ok: bool
    acao: str
    motivo: str = ""


def terminal_aberto() -> bool:
    """Ha' uma janela de terminal MT5 aberta nesta maquina?

    Via janela, e nao via `tasklist`/`mt5.initialize()`: o primeiro nao
    distingue instalacao (esta maquina tem duas), e o segundo ABRE um
    terminal quando nao acha nenhum -- comportamento documentado da API, e o
    oposto do que uma CONFERENCIA deve fazer."""
    import ctypes

    try:
        return bool(ctypes.windll.user32.FindWindowW(_WINDOW_CLASS, None))
    except Exception:
        return False


def data_dir_de(terminal_exe: Path) -> Optional[Path]:
    """Pasta de dados (`%APPDATA%/MetaQuotes/Terminal/<hash>`) da instalacao
    em `terminal_exe`, ou `None` se nao der para identificar.

    O casamento e' pelo `origin.txt` de cada pasta, que guarda o diretorio de
    instalacao que a criou -- necessario porque uma maquina com dois
    terminais (o caso desta) tem duas pastas de hash, e escrever no config da
    errada liga o AutoTrading de um terminal que nao e' o que vai operar."""
    import os

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    raiz = Path(appdata) / "MetaQuotes" / "Terminal"
    if not raiz.is_dir():
        return None
    alvo = str(Path(terminal_exe).parent).rstrip("\\/").lower()
    for pasta in raiz.iterdir():
        origem = pasta / "origin.txt"
        if not origem.is_file():
            continue
        try:
            texto = origem.read_text(encoding=_INI_ENCODING).strip("﻿ \r\n\t")
        except (OSError, UnicodeError):
            continue
        if texto.rstrip("\\/").lower() == alvo:
            return pasta
    return None


def _config_ini(data_dir: Path) -> Path:
    return Path(data_dir) / "config" / "common.ini"


def autotrading_no_config(data_dir: Path) -> Optional[bool]:
    """Valor de `[Experts] Enabled` no `common.ini`, ou `None` se o arquivo
    nao existe / nao da' para ler. `None` NAO e' "desligado": e' "nao sei"."""
    caminho = _config_ini(data_dir)
    try:
        linhas = caminho.read_text(encoding=_INI_ENCODING).splitlines()
    except (OSError, UnicodeError):
        return None
    valor = _valor_na_secao(linhas, "Experts", "Enabled")
    return None if valor is None else valor.strip() == "1"


def ligar_autotrading_no_config(data_dir: Path) -> bool:
    """Escreve `[Experts] Enabled=1` no `common.ini`. `True` se o arquivo
    ficou com o valor certo (inclusive quando ja estava).

    Edicao por LINHA, nao via `configparser`: aquele reescreveria o arquivo
    inteiro no formato dele (ordem das secoes, espacamento, aspas), e este
    arquivo e' do terminal, nao nosso -- a unica mudanca segura e' a linha
    pedida. So' chamar com o terminal FECHADO: aberto, ele reescreve tudo por
    cima quando sai."""
    caminho = _config_ini(data_dir)
    try:
        texto = caminho.read_text(encoding=_INI_ENCODING)
    except (OSError, UnicodeError):
        return False
    quebra = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines()
    novas = _definir_na_secao(linhas, "Experts", "Enabled", "1")
    try:
        caminho.write_text(quebra.join(novas) + quebra, encoding=_INI_ENCODING)
    except OSError:
        return False
    return autotrading_no_config(data_dir) is True


def _indice_secao(linhas: list[str], secao: str) -> Optional[int]:
    alvo = f"[{secao}]".lower()
    for i, linha in enumerate(linhas):
        if linha.strip().lower() == alvo:
            return i
    return None


def _fim_da_secao(linhas: list[str], inicio: int) -> int:
    for i in range(inicio + 1, len(linhas)):
        if linhas[i].strip().startswith("["):
            return i
    return len(linhas)


def _valor_na_secao(linhas: list[str], secao: str, chave: str) -> Optional[str]:
    inicio = _indice_secao(linhas, secao)
    if inicio is None:
        return None
    for linha in linhas[inicio + 1:_fim_da_secao(linhas, inicio)]:
        nome, _, valor = linha.partition("=")
        if nome.strip().lower() == chave.lower():
            return valor
    return None


def _definir_na_secao(linhas: list[str], secao: str, chave: str, valor: str) -> list[str]:
    """`linhas` com `chave=valor` dentro de `[secao]` -- substituindo a chave
    que existir, ou criando chave (e secao) que faltar."""
    saida = list(linhas)
    inicio = _indice_secao(saida, secao)
    if inicio is None:
        return saida + [f"[{secao}]", f"{chave}={valor}"]
    fim = _fim_da_secao(saida, inicio)
    for i in range(inicio + 1, fim):
        nome, sep, _ = saida[i].partition("=")
        if sep and nome.strip().lower() == chave.lower():
            saida[i] = f"{nome}={valor}"
            return saida
    saida.insert(fim, f"{chave}={valor}")
    return saida


def _autotrading_ligado_agora() -> Optional[bool]:
    """Le o terminal ABERTO. `None` = nao deu para saber."""
    from live.broker_mt5 import MT5Broker

    broker = MT5Broker()
    if not broker.connect():
        return None
    return broker.autotrading_allowed()


def garantir_terminal_com_autotrading(
    terminal_exe: Optional[str], espera_segundos: float = 90.0,
) -> ResultadoTerminal:
    """Deixa o terminal aberto e com o AutoTrading LIGADO, se der.

    Os quatro desfechos, e o porque de cada um:

      - terminal aberto e botao ligado -> `ok`, nada a fazer;
      - terminal aberto e botao DESLIGADO -> NAO ok, e este modulo nao mexe:
        ligar exigiria fechar o terminal para reescrever o config, e fechar um
        terminal aberto derruba ordem pendente, posicao vigiada e a conexao
        dos outros robos. O dono resolve com Ctrl+E em 1 segundo; o robo, ate'
        la', recusa o pregao com o motivo na tela;
      - terminal FECHADO -> escreve `Enabled=1` no config e abre o terminal,
        esperando ate' `espera_segundos` pela confirmacao de que subiu com o
        botao ligado (a confirmacao vem do proprio terminal, nunca da
        suposicao de que escrever no arquivo bastou);
      - sem `terminal_exe` (`MT5_TERMINAL_PATH` nao definido), exe inexistente
        ou pasta de dados nao identificada -> NAO ok, com o motivo dizendo o
        que falta configurar.
    """
    if terminal_aberto():
        ligado = _autotrading_ligado_agora()
        if ligado:
            return ResultadoTerminal(True, "ja_aberto")
        return ResultadoTerminal(
            False, "aberto_sem_autotrading",
            "o terminal MT5 ja esta aberto com o AutoTrading DESLIGADO. Nao vou "
            "fecha-lo para arrumar o config (fechar derruba ordem pendente e a "
            "conexao dos outros robos): ligue no botao 'Algo Trading' (Ctrl+E) "
            "do terminal.",
        )

    if not terminal_exe:
        return ResultadoTerminal(
            False, "sem_caminho",
            "nao sei onde esta o terminal MT5: defina MT5_TERMINAL_PATH com o "
            "caminho do terminal64.exe.",
        )
    exe = Path(terminal_exe)
    if not exe.is_file():
        return ResultadoTerminal(
            False, "exe_inexistente",
            f"MT5_TERMINAL_PATH aponta para {exe} e nao ha arquivo ali.",
        )
    data_dir = data_dir_de(exe)
    if data_dir is None:
        return ResultadoTerminal(
            False, "data_dir_desconhecida",
            f"nao achei a pasta de dados do terminal instalado em {exe.parent} "
            "(%APPDATA%/MetaQuotes/Terminal/<hash>/origin.txt).",
        )
    if not ligar_autotrading_no_config(data_dir):
        return ResultadoTerminal(
            False, "config_nao_gravado",
            f"nao consegui gravar [Experts] Enabled=1 em {_config_ini(data_dir)}.",
        )

    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except OSError as erro:
        return ResultadoTerminal(False, "falha_ao_abrir", f"nao consegui abrir {exe}: {erro}")

    limite = time.monotonic() + espera_segundos
    while time.monotonic() < limite:
        if _autotrading_ligado_agora():
            return ResultadoTerminal(True, "aberto_com_autotrading")
        time.sleep(1.0)
    return ResultadoTerminal(
        False, "sem_confirmacao",
        f"abri o terminal mas ele nao confirmou o AutoTrading ligado em "
        f"{espera_segundos:.0f}s (login pendente? senha nao salva?).",
    )
