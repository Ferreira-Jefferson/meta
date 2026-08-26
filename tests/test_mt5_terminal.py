"""Testes de `live/mt5_terminal.py` — subir o terminal MT5 com o AutoTrading
ligado.

Nenhum deles abre terminal nenhum: o `common.ini` e a pasta de dados são
sintéticos (`tmp_path`), e as duas leituras que dependem do mundo real
(`terminal_aberto`, `_autotrading_ligado_agora`) entram por monkeypatch. O
que está em jogo:

  1. o arquivo é do TERMINAL, não nosso — editar `[Experts] Enabled` não pode
     mexer em mais nada (nem no resto do arquivo, nem na codificação UTF-16);
  2. a pasta de dados certa, numa máquina com DOIS terminais instalados;
  3. terminal já aberto com o botão desligado NÃO é "conserta fechando" —
     fechar derruba ordem pendente e a conexão dos outros robôs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from live import mt5_terminal as mt


_COMMON_INI = """[Charts]
ProfileLast=Default
MaxBars=100000
[Experts]
AllowDllImport=0
Enabled=0
Account=1
[Notification]
Enable=1
"""


def _monta_terminal(tmp_path: Path, instalacao: str, ini: str = _COMMON_INI) -> Path:
    """Cria uma pasta de dados de terminal como o MT5 a escreve: `origin.txt`
    apontando para a instalação e `config/common.ini` em UTF-16."""
    data_dir = tmp_path / "38FF261A42172F3478E54D3A1A8FE02B"
    (data_dir / "config").mkdir(parents=True)
    (data_dir / "origin.txt").write_text(instalacao, encoding="utf-16")
    (data_dir / "config" / "common.ini").write_text(ini, encoding="utf-16")
    return data_dir


# ---------- edição do common.ini -------------------------------------------

def test_ligar_autotrading_troca_so_a_linha_pedida(tmp_path):
    data_dir = _monta_terminal(tmp_path, r"C:\Program Files\Rico - MetaTrader 5")
    assert mt.autotrading_no_config(data_dir) is False

    assert mt.ligar_autotrading_no_config(data_dir) is True

    assert mt.autotrading_no_config(data_dir) is True
    texto = (data_dir / "config" / "common.ini").read_text(encoding="utf-16")
    # tudo o mais intacto -- inclusive a codificação, que se for reescrita em
    # UTF-8 corrompe o arquivo INTEIRO para o terminal, não só a linha tocada
    assert "AllowDllImport=0" in texto
    assert "ProfileLast=Default" in texto
    assert "[Notification]" in texto
    assert texto.count("Enabled=") == 1


def test_chave_ausente_e_criada_dentro_da_secao_certa(tmp_path):
    """`[Experts]` sem `Enabled` acontece em terminal recém-instalado."""
    ini = "[Charts]\nMaxBars=100000\n[Experts]\nAllowDllImport=0\n[Notification]\nEnable=1\n"
    data_dir = _monta_terminal(tmp_path, r"C:\MT5", ini=ini)

    assert mt.ligar_autotrading_no_config(data_dir) is True

    linhas = (data_dir / "config" / "common.ini").read_text(encoding="utf-16").splitlines()
    experts = linhas.index("[Experts]")
    notification = linhas.index("[Notification]")
    assert "Enabled=1" in linhas[experts:notification]


def test_secao_ausente_e_criada(tmp_path):
    data_dir = _monta_terminal(tmp_path, r"C:\MT5", ini="[Charts]\nMaxBars=1\n")

    assert mt.ligar_autotrading_no_config(data_dir) is True
    assert mt.autotrading_no_config(data_dir) is True


def test_config_ilegivel_nao_e_lido_como_desligado(tmp_path):
    """`None` é "não sei", e "não sei" não pode virar "desligado": quem
    confunde os dois desliga o robô por causa de um arquivo que sumiu."""
    assert mt.autotrading_no_config(tmp_path / "nao-existe") is None
    assert mt.ligar_autotrading_no_config(tmp_path / "nao-existe") is False


# ---------- descoberta da pasta de dados -----------------------------------

def test_data_dir_casa_pela_instalacao_e_nao_pela_primeira_pasta(tmp_path, monkeypatch):
    """Esta máquina tem DOIS terminais instalados. Escrever no config do
    errado ligaria o AutoTrading de um terminal que não vai operar."""
    raiz = tmp_path / "MetaQuotes" / "Terminal"
    for hashdir, origem in (("AAAA", r"C:\Program Files\Outro MetaTrader 5"),
                            ("BBBB", r"C:\Program Files\Rico - MetaTrader 5")):
        pasta = raiz / hashdir
        pasta.mkdir(parents=True)
        (pasta / "origin.txt").write_text(origem, encoding="utf-16")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    achado = mt.data_dir_de(Path(r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"))

    assert achado == raiz / "BBBB"


def test_data_dir_sem_correspondencia_devolve_none(tmp_path, monkeypatch):
    raiz = tmp_path / "MetaQuotes" / "Terminal" / "AAAA"
    raiz.mkdir(parents=True)
    (raiz / "origin.txt").write_text(r"C:\Outro", encoding="utf-16")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert mt.data_dir_de(Path(r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe")) is None


# ---------- decisão de alto nível ------------------------------------------

def test_terminal_aberto_com_autotrading_ligado_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(mt, "terminal_aberto", lambda: True)
    monkeypatch.setattr(mt, "_autotrading_ligado_agora", lambda: True)

    resultado = mt.garantir_terminal_com_autotrading(r"C:\qualquer\terminal64.exe")

    assert resultado.ok is True
    assert resultado.acao == "ja_aberto"


def test_terminal_aberto_com_autotrading_desligado_nao_fecha_o_terminal(monkeypatch, tmp_path):
    """Fechar para reescrever o config derrubaria ordem pendente, posição
    vigiada e a conexão dos outros robôs — por 1 segundo de Ctrl+E."""
    monkeypatch.setattr(mt, "terminal_aberto", lambda: True)
    monkeypatch.setattr(mt, "_autotrading_ligado_agora", lambda: False)
    monkeypatch.setattr(mt, "ligar_autotrading_no_config",
                        lambda *a: pytest.fail("não pode tocar no config com o terminal aberto"))
    monkeypatch.setattr(mt.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("não pode abrir/fechar terminal aqui"))

    resultado = mt.garantir_terminal_com_autotrading(r"C:\qualquer\terminal64.exe")

    assert resultado.ok is False
    assert resultado.acao == "aberto_sem_autotrading"
    assert "Ctrl+E" in resultado.motivo


def test_terminal_fechado_liga_no_config_e_abre(monkeypatch, tmp_path):
    data_dir = _monta_terminal(tmp_path, str(tmp_path))
    exe = tmp_path / "terminal64.exe"
    exe.write_text("", encoding="utf-8")
    abertos = []
    monkeypatch.setattr(mt, "terminal_aberto", lambda: False)
    monkeypatch.setattr(mt, "data_dir_de", lambda _exe: data_dir)
    monkeypatch.setattr(mt.subprocess, "Popen", lambda cmd, **k: abertos.append(cmd))
    monkeypatch.setattr(mt, "_autotrading_ligado_agora", lambda: True)

    resultado = mt.garantir_terminal_com_autotrading(str(exe))

    assert resultado.ok is True
    assert resultado.acao == "aberto_com_autotrading"
    assert abertos == [[str(exe)]]
    assert mt.autotrading_no_config(data_dir) is True


def test_terminal_que_nao_confirma_o_botao_nao_e_dado_como_pronto(monkeypatch, tmp_path):
    """A confirmação vem do TERMINAL, nunca da suposição de que escrever no
    arquivo bastou — login pendente deixa o terminal aberto e inútil."""
    data_dir = _monta_terminal(tmp_path, str(tmp_path))
    exe = tmp_path / "terminal64.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(mt, "terminal_aberto", lambda: False)
    monkeypatch.setattr(mt, "data_dir_de", lambda _exe: data_dir)
    monkeypatch.setattr(mt.subprocess, "Popen", lambda cmd, **k: None)
    monkeypatch.setattr(mt, "_autotrading_ligado_agora", lambda: None)
    monkeypatch.setattr(mt.time, "sleep", lambda _s: None)

    resultado = mt.garantir_terminal_com_autotrading(str(exe), espera_segundos=0.01)

    assert resultado.ok is False
    assert resultado.acao == "sem_confirmacao"


def test_sem_caminho_do_terminal_diz_o_que_falta(monkeypatch):
    monkeypatch.setattr(mt, "terminal_aberto", lambda: False)

    resultado = mt.garantir_terminal_com_autotrading(None)

    assert resultado.ok is False
    assert "MT5_TERMINAL_PATH" in resultado.motivo
