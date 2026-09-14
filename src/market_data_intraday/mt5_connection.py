"""Conexao IPC com o terminal MT5: UMA por processo, nao uma por leitura.

O que aconteceu (2026-09-14)
----------------------------
Os cinco slots de day trade em operacao gravaram, em 4 episodios do mesmo
pregao, a linha `feed nao conseguiu LER o terminal (<simbolo>): connect:
falha ao conectar ao terminal MT5 (last_error=(-6, 'Terminal: Authorization
failed'))`. O padrao no diario e' inequivoco:

  * os CINCO processos falham na MESMA janela de 1 a 4 segundos e voltam
    juntos 5-15s depois (1 a 3 passos do supervisor). Cinco processos
    independentes nao erram em uniao por acaso -- a falha e' do terminal;
  * no MESMO processo e no MESMO segundo, o `MT5Feed` (relogio) e o
    `MT5Broker` (ordens) nao reclamaram de nada. A diferenca entre eles e o
    feed intradiario NAO e' o terminal: e' que os dois primeiros guardam
    `_connected` e chamam `mt5.initialize()` UMA vez por processo, enquanto
    `mt5_source._connect`/`mt5_ticks_source._connect` chamavam a CADA
    leitura -- 5 em 5 segundos, vezes 5 processos, ~1 autorizacao por
    segundo contra o terminal, o pregao inteiro.

`mt5.initialize(login=..., password=..., server=...)` nao e' uma consulta
barata: com credenciais ele repede AUTORIZACAO ao servidor da corretora.
Enquanto o terminal esta reconectando (ou apenas ocupado), essa autorizacao
volta `-6 RES_E_AUTH_FAILED` -- mesmo com a sessao IPC que ja existe
perfeitamente viva e capaz de entregar tick. Ou seja: o robo declarava
cegueira por causa de uma pergunta que ele nao precisava ter feito.

Os dois `_connect` ja diziam na docstring "Idempotente -- mesmo padrao de
`MT5Feed._connect`/`MT5Broker.connect`". Nao eram: a promessa estava no
comentario e o cache nao estava no codigo. Este modulo cumpre a promessa num
lugar so', para os dois arquivos da feature.

O que NAO muda, e e' o ponto (item 5.17 de `LICOES_DE_PRODUCAO.md`)
-------------------------------------------------------------------
O alarme de leitura falhada continua existindo inteiro. Cachear a conexao
cala o falso positivo ("nao consegui REPERGUNTAR a autorizacao"), nunca o
verdadeiro ("nao consegui LER"): quem decide se a leitura deu certo continua
sendo `_falha_de_leitura` sobre o RESULTADO de `copy_ticks_range` /
`copy_rates_*`. Se o terminal ficar de pe mas parar de entregar negocio, a
chamada devolve `None` (ou vazio com `last_error` negativo) e o diario grita
igual. O que se perde e' so' o ruido; a cegueira de 44,8 minutos de
2026-09-08 seria reportada exatamente como foi.

Por que a liveness e' `terminal_info() is not None`
---------------------------------------------------
E' o teste de a SESSAO IPC deste processo estar de pe -- que e' a unica coisa
que `initialize()` resolveria. Deliberadamente NAO se olha
`terminal_info().connected` (a conexao do terminal com o servidor de
negociacao): quando ela cai, reinicializar nao conserta nada (e' justamente
quando `-6` aparece) e quem tem autoridade para dizer que o robo ficou cego
e' a leitura, nao o handshake. Testar o handshake para decidir sobre o dado
e' trocar o termometro pelo termostato.

Retentativa curta
-----------------
Quando a sessao REALMENTE precisa nascer (primeiro passo do processo, ou IPC
que caiu), `-6` costuma durar menos que um passo do supervisor. Tres
tentativas espacadas de 0,35s custam no pior caso 0,7s de um ciclo de 5s, e
so' no caminho de falha. Nao ha retentativa no caminho feliz: ele nem chama
`initialize()`.

`mt5.shutdown()` nunca e' chamado aqui de proposito: o IPC do pacote
`MetaTrader5` e' GLOBAL do processo, e o mesmo processo tem um `MT5Broker`
com `_connected=True` em memoria. Derrubar a sessao para "limpar" deixaria o
broker achando que esta conectado -- trocar um alarme falso por uma ordem
que nao sai.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional


#: Tentativas de `initialize()` antes de declarar falha de conexao. Vale so'
#: para o caminho em que a sessao precisa nascer.
TENTATIVAS_DE_CONEXAO = 3

#: Espera entre tentativas, em segundos. Teto de espera total =
#: `(TENTATIVAS_DE_CONEXAO - 1) * ESPERA_ENTRE_TENTATIVAS_S`.
ESPERA_ENTRE_TENTATIVAS_S = 0.35

#: `(modulo_mt5, chave_de_credenciais)` da sessao viva deste processo, ou
#: `None`. Guarda o proprio MODULO, nao um booleano: e' o que faz um fake de
#: teste trocado em `sys.modules` invalidar o cache sozinho, sem nenhum
#: `reset` espalhado pela suite (e o que impede uma sessao de vazar entre
#: testes do mesmo worker do xdist).
_SESSAO: Optional[tuple] = None

_LOCK = threading.Lock()


def _chave(login, server, path) -> tuple:
    """Identidade da conexao pedida. A SENHA fica de fora de proposito: nao
    ha por que manter segredo vivo num global de modulo, e credencial que
    muda so' na senha (mesmo login, mesmo servidor) nao existe na pratica --
    trocar de conta troca o login."""
    return (login, server, path)


def _sessao_viva(mt5) -> bool:
    """A sessao IPC deste processo ainda responde?

    `terminal_info()` ausente = modulo limitado (fake de teste): assume viva,
    porque quem ja' inicializou com sucesso contra aquele objeto nao tem como
    checar melhor. O pacote real sempre tem o atributo.
    """
    verificar: Optional[Callable] = getattr(mt5, "terminal_info", None)
    if verificar is None:
        return True
    try:
        return verificar() is not None
    except Exception:
        return False


def conectar(mt5, login=None, password=None, server=None, path=None,
             sleep_fn: Callable[[float], None] = time.sleep) -> bool:
    """`True` se este processo tem sessao utilizavel com o terminal.

    Idempotente DE VERDADE: com a sessao de pe nao chama `initialize()`
    nenhuma vez. Sem ela (primeiro uso, credenciais diferentes, IPC caido),
    tenta ate `TENTATIVAS_DE_CONEXAO` vezes antes de devolver `False` -- e
    so' entao quem chamou reporta falha de conexao.
    """
    global _SESSAO
    chave = _chave(login, server, path)
    with _LOCK:
        if _SESSAO is not None and _SESSAO[0] is mt5 and _SESSAO[1] == chave:
            if _sessao_viva(mt5):
                return True
            _SESSAO = None

        kwargs = {}
        if path:
            kwargs["path"] = path
        if login is not None:
            kwargs["login"] = login
            kwargs["password"] = password
            kwargs["server"] = server

        for tentativa in range(TENTATIVAS_DE_CONEXAO):
            try:
                ok = bool(mt5.initialize(**kwargs))
            except Exception:
                ok = False
            if ok:
                _SESSAO = (mt5, chave)
                return True
            if tentativa < TENTATIVAS_DE_CONEXAO - 1:
                sleep_fn(ESPERA_ENTRE_TENTATIVAS_S)
        _SESSAO = None
        return False


def esquecer_sessao() -> None:
    """Descarta o cache SEM tocar no terminal (nao ha `shutdown()` aqui, ver
    docstring do modulo). Existe para teste; em producao a invalidacao e'
    automatica, por `terminal_info()`."""
    global _SESSAO
    with _LOCK:
        _SESSAO = None
