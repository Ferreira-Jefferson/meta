"""Testes da camada de dado de mercado — sem rede.

Foco: o merge que impede um download com pregão faltando de apagar dado bom
(`merge_preserving_history`) e a impressao digital que detecta run stale
(`universe_fingerprint`).
"""
from pathlib import Path

import pandas as pd
import pytest

from market_data.download import incremental_start, merge_preserving_history, save_parquet
from market_data.loader import _frame_digest, universe_fingerprint
from market_data.quality import consensus_calendar, fill_gaps


def _panel(dates: list[str], close_base: float = 10.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates], name="date")
    n = len(idx)
    return pd.DataFrame(
        {
            "open": [close_base + i for i in range(n)],
            "high": [close_base + i + 1 for i in range(n)],
            "low": [close_base + i - 1 for i in range(n)],
            "close": [close_base + i + 0.5 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        },
        index=idx,
    )


def test_merge_resgata_pregao_que_o_download_perdeu(tmp_path):
    """O caso real: o parquet tinha 2026-08-10, o download novo veio sem ele."""
    completo = _panel(["2026-08-07", "2026-08-10", "2026-08-11"])
    save_parquet("TEST4.SA", completo, out_dir=tmp_path)

    com_buraco = _panel(["2026-08-07", "2026-08-11"], close_base=99.0)
    merged, rescued = merge_preserving_history("TEST4.SA", com_buraco, out_dir=tmp_path)

    assert [d.strftime("%Y-%m-%d") for d in rescued] == ["2026-08-10"]
    assert len(merged) == 3
    # o dia resgatado mantem o valor antigo...
    assert merged.loc["2026-08-10", "close"] == pytest.approx(completo.loc["2026-08-10", "close"])
    # ...e os dias sobrepostos ficam com o valor NOVO (correcao do provedor vale)
    assert merged.loc["2026-08-07", "close"] == pytest.approx(99.5)
    assert merged.index.is_monotonic_increasing


def test_merge_sem_parquet_antigo_devolve_o_novo(tmp_path):
    novo = _panel(["2026-08-07", "2026-08-10"])
    merged, rescued = merge_preserving_history("NOVO3.SA", novo, out_dir=tmp_path)
    assert rescued == []
    assert merged.equals(novo)


def test_merge_nao_ressuscita_datas_futuras(tmp_path):
    """Se o parquet antigo tem data ALEM do download novo, nao e 'buraco' —
    e um download mais curto; nao inventa barra futura."""
    antigo = _panel(["2026-08-07", "2026-08-10", "2026-08-11"])
    save_parquet("CURTO3.SA", antigo, out_dir=tmp_path)
    novo = _panel(["2026-08-07", "2026-08-10"])
    merged, rescued = merge_preserving_history("CURTO3.SA", novo, out_dir=tmp_path)
    assert rescued == []
    assert merged.index[-1] == pd.Timestamp("2026-08-10")


def test_merge_preserva_multiplos_buracos(tmp_path):
    antigo = _panel(["2026-07-30", "2026-07-31", "2026-08-03", "2026-08-10", "2026-08-11"])
    save_parquet("MULTI3.SA", antigo, out_dir=tmp_path)
    novo = _panel(["2026-07-30", "2026-08-03", "2026-08-11"], close_base=50.0)
    merged, rescued = merge_preserving_history("MULTI3.SA", novo, out_dir=tmp_path)
    assert len(rescued) == 2
    assert len(merged) == 5


def test_frame_digest_muda_com_o_conteudo():
    a = _panel(["2026-08-07", "2026-08-10"])
    b = a.copy()
    assert _frame_digest(a) == _frame_digest(b)
    b.loc["2026-08-10", "close"] = 999.0
    assert _frame_digest(a) != _frame_digest(b)


def test_frame_digest_muda_quando_falta_pregao():
    completo = _panel(["2026-08-07", "2026-08-10", "2026-08-11"])
    com_buraco = completo.drop(index=pd.Timestamp("2026-08-10"))
    assert _frame_digest(completo) != _frame_digest(com_buraco)


def test_universe_fingerprint_estavel_e_sensivel(tmp_path):
    save_parquet("AAAA3.SA", _panel(["2026-08-07", "2026-08-10"]), out_dir=tmp_path)
    fp1 = universe_fingerprint(tickers=["AAAA3.SA"], include_benchmark=False,
                               macros=(), out_dir=tmp_path)
    fp2 = universe_fingerprint(tickers=["AAAA3.SA"], include_benchmark=False,
                               macros=(), out_dir=tmp_path)
    assert fp1 == fp2                      # deterministico sobre o mesmo dado

    save_parquet("AAAA3.SA", _panel(["2026-08-07", "2026-08-10"], close_base=77.0),
                 out_dir=tmp_path)
    fp3 = universe_fingerprint(tickers=["AAAA3.SA"], include_benchmark=False,
                               macros=(), out_dir=tmp_path)
    assert fp3 != fp1                      # dado revisado -> run considerada stale


def test_consensus_calendar_diferencia_feriado_real_de_buraco_pontual():
    """Feriado real: NINGUÉM tem a data -> fora do consenso.
    Buraco pontual: 9 de 10 tickers têm -> consenso inclui (é dia de pregão)."""
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    frames = {}
    for i in range(10):
        d = [x for x in days if x != "2024-01-04"]  # feriado: nenhum ticker tem
        if i == 0:
            d = [x for x in d if x != "2024-01-08"]  # buraco pontual: só este ticker perde
        frames[f"T{i}.SA"] = _panel(d)

    cal = consensus_calendar(frames, min_ratio=0.9, min_tickers=5)
    assert pd.Timestamp("2024-01-04") not in cal
    assert pd.Timestamp("2024-01-08") in cal


def test_consensus_calendar_devolve_none_com_poucos_tickers():
    frames = {"A.SA": _panel(["2024-01-02", "2024-01-03"])}
    assert consensus_calendar(frames, min_tickers=5) is None


def test_fill_gaps_carrega_close_anterior_e_marca_synthetic():
    df = _panel(["2024-01-02", "2024-01-03", "2024-01-05"])  # falta 2024-01-04
    calendar = pd.DatetimeIndex(
        [pd.Timestamp(d) for d in ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]]
    )
    filled, missing = fill_gaps(df, calendar)

    assert [d.strftime("%Y-%m-%d") for d in missing] == ["2024-01-04"]
    assert filled.loc["2024-01-04", "close"] == pytest.approx(filled.loc["2024-01-03", "close"])
    assert filled.loc["2024-01-04", "volume"] == 0
    assert bool(filled.loc["2024-01-04", "synthetic"]) is True
    assert bool(filled.loc["2024-01-03", "synthetic"]) is False


def test_incremental_start_sem_parquet_usa_default():
    assert incremental_start("NUNCA3.SA", "2010-01-01", out_dir=Path("/nao/existe")) == "2010-01-01"


def test_incremental_start_com_parquet_pede_so_janela_recente(tmp_path):
    save_parquet("VELHA3.SA", _panel(["2020-01-02", "2026-08-01"]), out_dir=tmp_path)
    got = incremental_start("VELHA3.SA", "2010-01-01", out_dir=tmp_path)
    assert got == (pd.Timestamp("2026-08-01") - pd.Timedelta(days=15)).strftime("%Y-%m-%d")


def test_incremental_start_nao_ultrapassa_o_default(tmp_path):
    """Histórico muito curto: a janela de lookback não deve voltar antes do
    início oficial da série."""
    save_parquet("NOVA3.SA", _panel(["2026-08-10", "2026-08-11"]), out_dir=tmp_path)
    got = incremental_start("NOVA3.SA", "2026-08-11", out_dir=tmp_path)
    assert got == "2026-08-11"


def test_fill_gaps_sem_buracos_nao_altera_linhas():
    df = _panel(["2024-01-02", "2024-01-03"])
    calendar = pd.DatetimeIndex([pd.Timestamp(d) for d in ["2024-01-02", "2024-01-03"]])
    filled, missing = fill_gaps(df, calendar)

    assert missing == []
    assert not filled["synthetic"].any()
    assert len(filled) == 2


# ---------- escrita atomica do parquet -------------------------------------

def test_save_parquet_nao_deixa_temporario_para_tras(tmp_path):
    """Caminho felizmente comum: grava, renomeia, nao sobra lixo no diretorio."""
    save_parquet("AAA.SA", _panel(["2026-01-02", "2026-01-05"]), out_dir=tmp_path)
    arquivos = sorted(p.name for p in tmp_path.iterdir())
    assert arquivos == ["AAA_SA.parquet"]


def test_falha_de_escrita_preserva_o_parquet_anterior(tmp_path, monkeypatch):
    """O motivo de existir `write_parquet_atomico`: o parquet nunca pode ficar
    truncado nem desaparecer por causa de uma escrita que falhou no meio.

    Antes, `df.to_parquet(path)` gravava NO LUGAR — o arquivo passava por um
    estado parcial, e um erro no meio deixava o dado bom destruido. Como o
    supervisor ao vivo chama `sync_data()` enquanto o painel le os mesmos
    parquets, isso e risco com um unico processo, nao so com dois.
    """
    bom = _panel(["2026-01-02", "2026-01-05"])
    caminho = save_parquet("AAA.SA", bom, out_dir=tmp_path)
    antes = caminho.read_bytes()

    def explode(self, *a, **k):
        raise OSError("disco cheio no meio da escrita")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", explode)
    with pytest.raises(OSError):
        save_parquet("AAA.SA", _panel(["2026-01-02"]), out_dir=tmp_path)
    monkeypatch.undo()

    assert caminho.read_bytes() == antes, "escrita falha destruiu o parquet anterior"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["AAA_SA.parquet"], (
        "temporario ficou para tras")
