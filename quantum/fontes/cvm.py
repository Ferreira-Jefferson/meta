"""CVM — Portal de Dados Abertos (gratuito, sem chave). Fonte primária do Quantum.

O que vem daqui:
  - cadastro de companhias abertas (nome, setor, situação)
  - FCA: tickers de cada companhia (inclusive os que deixaram de negociar) e o site de RI
  - DFP (anual) e ITR (trimestral): demonstrações com `DT_RECEB`, a data em que o
    documento chegou ao mercado — base do backtest sem olhar o futuro
  - IPE: tudo que a companhia publica no RI e protocola na CVM (fatos relevantes,
    releases de resultado, apresentações, avisos de proventos), com link do PDF

Por que a CVM e não raspar o site de RI de cada empresa: cada site tem um layout
e muda sem aviso; a CVM recebe os MESMOS documentos, padronizados, com data de
entrega. O link de RI de cada empresa fica guardado para consulta humana.
"""
from __future__ import annotations

import re
import time
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import arquivo

BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"

# Categorias do IPE que interessam a quem analisa ação (o resto é ruído
# societário: posições de administradores, debêntures, atas de conselho fiscal...).
IPE_CATEGORIAS = (
    "Fato Relevante",
    "Comunicado ao Mercado",
    "Dados Econômico-Financeiros",
    "Aviso aos Acionistas",
    "Relatório Proventos",
    "Calendário de Eventos Corporativos",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower()


# ── Download (vai para dados/brutos/cvm/<grupo>/, com manifesto) ───────────
def baixar(rel: str, max_idade_h: float | None = None) -> Path | None:
    """Baixa `BASE/rel` para `brutos/cvm/<grupo>/`. None se não existe na CVM.

    `max_idade_h`: rebaixa se o arquivo local for mais velho que isso (o ano
    corrente muda toda semana; anos fechados ficam congelados para sempre).
    """
    partes = rel.split("/")
    grupo = (partes[1] if partes[0] == "DOC" else partes[0]).lower()
    destino = arquivo.caminho("cvm", grupo, partes[-1])
    return arquivo.baixar(f"{BASE}/{rel}", destino, "cvm", max_idade_h)


def url_de(p: Path) -> str:
    """URL de origem de um bruto da CVM a partir do caminho local (para o manifesto)."""
    grupo = p.parent.name.upper()
    return f"{BASE}/CAD/DADOS/{p.name}" if grupo == "CAD" else f"{BASE}/DOC/{grupo}/DADOS/{p.name}"


def _idade_para(ano: int) -> float | None:
    """Ano corrente e anterior são revisados (reapresentações): rebaixa após 20h."""
    return 20.0 if ano >= date.today().year - 1 else None


def _csv(z: zipfile.ZipFile, nome: str, usecols=None) -> pd.DataFrame | None:
    if nome not in z.namelist():
        return None
    return pd.read_csv(z.open(nome), sep=";", encoding="latin1", dtype=str, usecols=usecols)


# ── Cadastro e tickers ─────────────────────────────────────────────────────
def ler_cadastro() -> pd.DataFrame:
    p = baixar("CAD/DADOS/cad_cia_aberta.csv", max_idade_h=20)
    df = pd.read_csv(p, sep=";", encoding="latin1", dtype=str)
    df = df.sort_values("DT_INI_SIT").drop_duplicates("CNPJ_CIA", keep="last")
    out = pd.DataFrame({
        "cnpj": df.CNPJ_CIA,
        "nome": df.DENOM_SOCIAL,
        "nome_comercial": df.DENOM_COMERC,
        "cd_cvm": df.CD_CVM,
        "setor": df.SETOR_ATIV,
        "situacao": df.SIT,
    })
    out["financeira"] = out.setor.fillna("").map(_eh_setor_financeiro).astype(int)
    return out


def _eh_setor_financeiro(setor: str) -> bool:
    s = _norm(setor)
    return any(k in s for k in ("banco", "intermediacao financeira", "segurad", "arrendamento mercantil", "securitiz"))


def acoes_por_unit(texto) -> float:
    """'1 ON / 2 PN' → 3; '1 KLBN3 + 4 KLBN4' → 5. Recibos de subscrição não contam.
    Sem composição legível devolve NaN: o valor de mercado da empresa fica em branco
    em vez de sair 3× maior."""
    if not isinstance(texto, str):
        return float("nan")
    nums = [int(n) for n, depois in re.findall(r"(?<![A-Za-z0-9])(\d+)\s*([A-Za-zçÇ]+)", texto)
            if not depois.lower().startswith("recibo")]
    return float(sum(nums)) if nums and sum(nums) > 0 else float("nan")


def ler_fca(anos: range) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (tickers, sites_ri) a partir de todos os FCAs do intervalo."""
    vms, gerais = [], []
    for ano in anos:
        p = baixar(f"DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip", max_idade_h=_idade_para(ano))
        if p is None:
            continue
        with zipfile.ZipFile(p) as z:
            vm = _csv(z, f"fca_cia_aberta_valor_mobiliario_{ano}.csv")
            ge = _csv(z, f"fca_cia_aberta_geral_{ano}.csv")
        if vm is not None:
            vm["ano"] = ano
            vms.append(vm)
        if ge is not None:
            ge["ano"] = ano
            gerais.append(ge)
    vm = pd.concat(vms, ignore_index=True)
    vm = vm[(vm.Mercado == "Bolsa") & vm.Valor_Mobiliario.isin(
        ["Ações Ordinárias", "Ações Preferenciais", "Units"])]
    vm = vm[vm.Codigo_Negociacao.fillna("").str.fullmatch(r"[A-Z][A-Z0-9]{3}\d{1,2}")]
    vm = vm.sort_values(["ano", "Versao"]).drop_duplicates("Codigo_Negociacao", keep="last")
    tickers = pd.DataFrame({
        "ticker": vm.Codigo_Negociacao,
        "cnpj": vm.CNPJ_Companhia,
        "classe": vm.Valor_Mobiliario.map({"Ações Ordinárias": "ON", "Ações Preferenciais": "PN", "Units": "UNIT"}),
        "segmento": vm.Segmento,
        "inicio_negociacao": vm.Data_Inicio_Negociacao,
        "fim_negociacao": vm.Data_Fim_Negociacao,
        "acoes_por_unit": [acoes_por_unit(c) if cl == "Units" else 1.0
                           for c, cl in zip(vm.Composicao_BDR_Unit, vm.Valor_Mobiliario)],
    })
    ge = pd.concat(gerais, ignore_index=True).sort_values("ano").drop_duplicates("CNPJ_Companhia", keep="last")
    sites = ge[["CNPJ_Companhia", "Pagina_Web"]].rename(columns={"CNPJ_Companhia": "cnpj", "Pagina_Web": "site_ri"})
    return tickers, sites


# ── Demonstrações (DFP/ITR) ────────────────────────────────────────────────
_COLS = ["CNPJ_CIA", "DT_REFER", "VERSAO", "ESCALA_MOEDA", "ORDEM_EXERC",
         "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"]


def _ler_demonstrativo(z, prefixo: str, ano: int, nome: str, contas_re: str) -> pd.DataFrame:
    """Lê con e ind de um demonstrativo, só as contas que casam com `contas_re`."""
    partes = []
    for cons, sufixo in ((1, "con"), (0, "ind")):
        arq = f"{prefixo}_cia_aberta_{nome}_{sufixo}_{ano}.csv"
        if arq not in z.namelist():
            continue
        cols = [c for c in _COLS if c != "DT_INI_EXERC" or not nome.startswith("BP")]
        df = _csv(z, arq, usecols=cols)
        df = df[df.CD_CONTA.str.match(contas_re)]
        df["consolidado"] = cons
        partes.append(df)
    if not partes:
        return pd.DataFrame(columns=_COLS + ["consolidado"])
    df = pd.concat(partes, ignore_index=True)
    # LPA (3.99) é R$/ação: não passa pela escala de milhar dos demais valores.
    escala = np.where((df.ESCALA_MOEDA == "MIL") & ~df.CD_CONTA.str.startswith("3.99"), 1000.0, 1.0)
    df["VL"] = pd.to_numeric(df.VL_CONTA, errors="coerce") * escala
    return df


def _contas_fluxo(dre: pd.DataFrame, dfc: pd.DataFrame) -> pd.DataFrame:
    """Valores ACUMULADOS NO ANO (YTD) de cada documento, para ÚLTIMO e PENÚLTIMO.

    O ITR traz duas linhas por conta: o trimestre isolado e o acumulado no ano.
    Fica a de período mais longo (acumulado), que é o que a DFC também traz.
    """
    fl = pd.concat([dre, dfc], ignore_index=True)
    fl = fl[fl.ORDEM_EXERC.isin(["ÚLTIMO", "PENÚLTIMO"])].copy()
    ini = pd.to_datetime(fl.DT_INI_EXERC, errors="coerce")
    fim = pd.to_datetime(fl.DT_FIM_EXERC, errors="coerce")
    fl["meses"] = ((fim.dt.year - ini.dt.year) * 12 + fim.dt.month - ini.dt.month + 1)
    fl = fl.sort_values("meses").drop_duplicates(
        ["CNPJ_CIA", "DT_REFER", "consolidado", "ORDEM_EXERC", "CD_CONTA"], keep="last")
    mapa = {"3.01": "receita", "3.03": "lucro_bruto", "3.05": "ebit", "6.01": "fco"}
    fl["campo"] = fl.CD_CONTA.map(mapa)
    # Lucro líquido: o código muda entre modelos (3.11 empresas, 3.09 bancos antigos,
    # 3.13 seguradoras...). Identifica pelo NOME da conta de nível 1, e o atribuível
    # à controladora pelo filho dela que cita "controladora".
    ds = fl.DS_CONTA.map(_norm)
    nivel = fl.CD_CONTA.str.count(r"\.")
    eh_lucro = ((nivel == 1) & fl.CD_CONTA.str.startswith("3.") & ~fl.CD_CONTA.str.startswith("3.99")
                & ds.str.contains("lucro|resultado liquido") & ds.str.contains("periodo|exercicio")
                & ~ds.str.contains("antes|por acao|continuad"))
    chave = ["CNPJ_CIA", "DT_REFER", "consolidado", "ORDEM_EXERC"]
    cod_lucro = fl[eh_lucro].groupby(chave).CD_CONTA.max().rename("cod_lucro")
    fl = fl.join(cod_lucro, on=chave)
    fl.loc[fl.CD_CONTA == fl.cod_lucro, "campo"] = "lucro"
    filho = pd.Series([c.startswith(f"{p}.") for c, p in zip(fl.CD_CONTA, fl.cod_lucro.fillna("x"))], index=fl.index)
    fl.loc[filho & (nivel == 2) & ds.str.contains("controladora"), "campo"] = "lucro_contr"
    # LPA básico: vem por classe (3.99.01.01, .02, ...), com zeros nas classes que a
    # empresa não tem; bancos às vezes só publicam na individual. Fica o primeiro
    # valor não nulo, preferindo ON, de qualquer das duas demonstrações.
    lpa = fl[fl.CD_CONTA.str.match(r"^3\.99\.01\.\d\d$") & (fl.VL.fillna(0) != 0)].copy()
    lpa["pref"] = (~ds.loc[lpa.index].str.fullmatch(r"\s*on\s*")).astype(int)
    lpa = lpa.sort_values(["pref", "consolidado", "CD_CONTA"], ascending=[True, False, True])
    lpa = lpa.drop_duplicates(["CNPJ_CIA", "DT_REFER", "ORDEM_EXERC"]).set_index(
        ["CNPJ_CIA", "DT_REFER", "ORDEM_EXERC"]).VL.rename("lpa_on")
    fl = fl[fl.campo.notna()]
    w = fl.pivot_table(index=["CNPJ_CIA", "DT_REFER", "consolidado", "ORDEM_EXERC"],
                       columns="campo", values="VL", aggfunc="first")
    meses = fl[fl.CD_CONTA.str.startswith("3.")].groupby(
        ["CNPJ_CIA", "DT_REFER", "consolidado", "ORDEM_EXERC"]).meses.max()
    w["meses"] = meses
    w = w.reset_index()
    return w.join(lpa, on=["CNPJ_CIA", "DT_REFER", "ORDEM_EXERC"])


def _contas_estoque(bpa: pd.DataFrame, bpp: pd.DataFrame) -> pd.DataFrame:
    """Estoques do balanço no fim do período (só ÚLTIMO)."""
    bp = pd.concat([bpa, bpp], ignore_index=True)
    bp = bp[bp.ORDEM_EXERC == "ÚLTIMO"].copy()
    bp["ds"] = bp.DS_CONTA.map(_norm)
    chave = ["CNPJ_CIA", "DT_REFER", "consolidado"]

    def soma(mask):
        return bp[mask].groupby(chave).VL.sum(min_count=1)

    nivel = bp.CD_CONTA.str.count(r"\.")
    eh_pl = (nivel == 1) & bp.CD_CONTA.str.startswith("2.") & bp.ds.str.contains("patrimonio liquido")
    pl = bp[eh_pl].groupby(chave).VL.first()
    cod_pl = bp[eh_pl].set_index(chave).CD_CONTA
    bp = bp.join(cod_pl.rename("cod_pl"), on=chave)
    filho_do_pl = [c.startswith(f"{p}.") for c, p in zip(bp.CD_CONTA, bp.cod_pl.fillna("x"))]
    minor = soma((nivel == 2) & pd.Series(filho_do_pl, index=bp.index)
                 & bp.ds.str.contains("nao controlador"))
    out = pd.DataFrame({
        "ativo": soma(bp.CD_CONTA == "1"),
        "caixa": soma(bp.CD_CONTA.isin(["1.01.01", "1.01.02"])),
        "divida": soma(bp.CD_CONTA.isin(["2.01.04", "2.02.01"]) & bp.ds.str.contains("emprestimo")),
        "pl": pl,
    })
    out["pl_contr"] = out.pl - minor.reindex(out.index).fillna(0.0)
    return out.reset_index()


def _acoes(z, prefixo: str, ano: int) -> pd.DataFrame | None:
    df = _csv(z, f"{prefixo}_cia_aberta_composicao_capital_{ano}.csv")
    if df is None:
        return None
    tot = pd.to_numeric(df.QT_ACAO_TOTAL_CAP_INTEGR, errors="coerce")
    tes = pd.to_numeric(df.QT_ACAO_TOTAL_TESOURO, errors="coerce").fillna(0)
    df["acoes"] = (tot - tes).where(tot > 0)
    return df[["CNPJ_CIA", "DT_REFER", "acoes"]].drop_duplicates(["CNPJ_CIA", "DT_REFER"], keep="last")


def ler_documentos_ano(tipo: str, ano: int) -> pd.DataFrame | None:
    """Extrai de um zip DFP/ITR uma linha por (empresa, dt_refer) com YTD + estoques."""
    prefixo = tipo.lower()
    p = baixar(f"DOC/{tipo}/DADOS/{prefixo}_cia_aberta_{ano}.zip", max_idade_h=_idade_para(ano))
    if p is None:
        return None
    with zipfile.ZipFile(p) as z:
        idx = _csv(z, f"{prefixo}_cia_aberta_{ano}.csv")
        idx["VERSAO"] = idx.VERSAO.astype(int)
        idx = idx.sort_values("VERSAO").drop_duplicates(["CNPJ_CIA", "DT_REFER"], keep="last")
        dre = _ler_demonstrativo(z, prefixo, ano, "DRE", r"^3\.(\d\d(\.0[12])?|99\.01\.\d\d)$")
        dfc = pd.concat([_ler_demonstrativo(z, prefixo, ano, n, r"^6\.01$") for n in ("DFC_MI", "DFC_MD")])
        bpa = _ler_demonstrativo(z, prefixo, ano, "BPA", r"^1(\.01\.0[12])?$")
        bpp = _ler_demonstrativo(z, prefixo, ano, "BPP", r"^2\.\d\d(\.\d\d)?$")
        acoes = _acoes(z, prefixo, ano)

    fl = _contas_fluxo(dre, dfc)
    es = _contas_estoque(bpa, bpp)
    ult = fl[fl.ORDEM_EXERC == "ÚLTIMO"].drop(columns="ORDEM_EXERC")
    pen = fl[fl.ORDEM_EXERC == "PENÚLTIMO"].drop(columns=["ORDEM_EXERC", "lpa_on", "meses"], errors="ignore")
    pen = pen.rename(columns={c: c + "_pen" for c in pen.columns if c not in ("CNPJ_CIA", "DT_REFER", "consolidado")})
    df = ult.merge(pen, on=["CNPJ_CIA", "DT_REFER", "consolidado"], how="left") \
            .merge(es, on=["CNPJ_CIA", "DT_REFER", "consolidado"], how="outer")
    # Consolidado quando existe; individual só para quem não consolida.
    df["tem"] = df[["receita", "ativo"]].notna().any(axis=1)
    df = df[df.tem].sort_values("consolidado").drop_duplicates(["CNPJ_CIA", "DT_REFER"], keep="last")
    df = df.merge(idx[["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB"]], on=["CNPJ_CIA", "DT_REFER"], how="inner")
    if acoes is not None:
        df = df.merge(acoes, on=["CNPJ_CIA", "DT_REFER"], how="left")
    else:
        df["acoes"] = np.nan
    df["tipo"] = tipo
    return df.drop(columns="tem")


_FLUXOS = ("receita", "lucro_bruto", "ebit", "lucro", "lucro_contr", "fco")


def montar_ltm(docs: pd.DataFrame) -> pd.DataFrame:
    """Converte YTD em últimos 12 meses (LTM), sem olhar o futuro.

    LTM = YTD_atual + ANUAL_anterior − YTD_mesmo_período_do_ano_anterior.
    O anual vem da DFP anterior; o YTD anterior vem do PRÓPRIO documento (coluna
    PENÚLTIMO), que já traz a comparação reapresentada. A data de disponibilidade
    do resultado é a MAIOR entre a do documento e a da DFP usada.
    """
    d = docs.copy()
    num = [c for c in d.columns if c not in ("CNPJ_CIA", "DT_REFER", "DT_RECEB", "tipo", "VERSAO", "consolidado")]
    d[num] = d[num].apply(pd.to_numeric, errors="coerce")
    d["dt"] = pd.to_datetime(d.DT_REFER)
    d["lucro_contr"] = d.lucro_contr.fillna(d.lucro)
    d["lucro_contr_pen"] = d.get("lucro_contr_pen", pd.Series(np.nan, index=d.index)).fillna(d.get("lucro_pen"))
    anual = d[d.meses == 12][["CNPJ_CIA", "dt", "DT_RECEB", *_FLUXOS]]
    anual = anual.rename(columns={c: c + "_anual" for c in _FLUXOS}).rename(
        columns={"dt": "dt_anual", "DT_RECEB": "receb_anual"})
    d = d.sort_values("dt")
    anual = anual.sort_values("dt_anual")
    # DFP mais recente estritamente anterior ao documento (no máximo 12 meses antes).
    d = pd.merge_asof(d, anual, left_on="dt", right_on="dt_anual", by="CNPJ_CIA",
                      allow_exact_matches=False, tolerance=pd.Timedelta(days=370))
    meses = d.meses.fillna(pd.Series(np.where(d.tipo == "DFP", 12, 0), index=d.index))
    parcial = meses < 12
    for c in _FLUXOS:
        ltm = d[c] + d[c + "_anual"] - d[c + "_pen"]
        d[c] = np.where(parcial, ltm, d[c])
    receb = pd.to_datetime(d.DT_RECEB)
    receb_anual = pd.to_datetime(d.receb_anual)
    d["dt_receb"] = np.where(parcial & receb_anual.notna() & (receb_anual > receb), receb_anual, receb)
    d["dt_receb"] = pd.to_datetime(d.dt_receb).dt.strftime("%Y-%m-%d")
    # Quantidade de ações: composição do capital quando existe; nos anos em que a
    # CVM não publica esse arquivo, estima pelo lucro ÷ LPA do MESMO documento
    # (mesma data, mesma base pré-desdobramento que o preço sem ajuste).
    estim = d.lucro_contr_ytd / d.lpa_on
    estim = estim.where((d.lpa_on.abs() > 1e-6) & (estim > 0))
    # A composição do capital vem em UNIDADES para a maioria e em MILHARES para
    # algumas (Bradesco sempre; Petrobras no 1T21). Decide a escala comparando com
    # lucro ÷ LPA do mesmo documento; sem essa referência, < 2 milhões de ações
    # é tratado como milhar (nenhuma listada relevante tem tão poucas).
    comp = d.acoes
    erro1 = (np.log10(comp / estim)).abs()
    erro1000 = (np.log10(comp * 1000 / estim)).abs()
    em_milhar = np.where(estim.notna() & comp.notna(), erro1000 < erro1, comp < 2e6)
    d["acoes"] = np.where(em_milhar, comp * 1000, comp)
    d["acoes"] = d.acoes.fillna(estim)
    # Segunda checagem, sem LPA: um documento 1000× abaixo da mediana da própria
    # empresa é escala trocada (desdobramento de 1000:1 não existe na prática).
    med = d.groupby("CNPJ_CIA").acoes.transform("median")
    milhar_viz = (np.log10(d.acoes * 1000 / med)).abs() < (np.log10(d.acoes / med)).abs()
    d["acoes"] = np.where(milhar_viz.fillna(False), d.acoes * 1000, d.acoes)
    # Terceira checagem, para quem declara em milhar em TODOS os documentos (Santander):
    # valor patrimonial acima de R$ 2.000 por ação não existe entre as listadas.
    vpa = d.pl_contr / d.acoes
    d["acoes"] = np.where((vpa > 2000) & (vpa / 1000 > 0.1), d.acoes * 1000, d.acoes)
    return pd.DataFrame({
        "cnpj": d.CNPJ_CIA, "dt_refer": d.DT_REFER, "tipo": d.tipo, "versao": d.VERSAO,
        "dt_receb": d.dt_receb, "consolidado": d.consolidado,
        **{c: d[c] for c in _FLUXOS},
        "ativo": d.ativo, "caixa": d.caixa, "divida": d.divida, "pl": d.pl, "pl_contr": d.pl_contr,
        "acoes": d.acoes,
    })


def ler_demonstracoes(anos: range, progresso=print) -> pd.DataFrame:
    partes = []
    for ano in anos:
        for tipo in ("DFP", "ITR"):
            t0 = time.time()
            df = ler_documentos_ano(tipo, ano)
            if df is not None:
                partes.append(df)
                progresso(f"  CVM {tipo} {ano}: {len(df)} documentos ({time.time() - t0:.0f}s)")
    docs = pd.concat(partes, ignore_index=True)
    # Guarda o YTD bruto do lucro para a estimativa de ações (antes de virar LTM).
    docs["lucro_contr_ytd"] = docs.lucro_contr.fillna(docs.lucro)
    return montar_ltm(docs)


# ── IPE: documentos publicados pelo RI ─────────────────────────────────────
def ler_ipe(anos: range, cnpjs: set[str]) -> pd.DataFrame:
    partes = []
    for ano in anos:
        p = baixar(f"DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip", max_idade_h=_idade_para(ano))
        if p is None:
            continue
        with zipfile.ZipFile(p) as z:
            df = _csv(z, f"ipe_cia_aberta_{ano}.csv")
        df = df[df.Categoria.isin(IPE_CATEGORIAS) & df.CNPJ_Companhia.isin(cnpjs)]
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    return pd.DataFrame({
        "protocolo": df.Protocolo_Entrega + "-" + df.Versao.astype(str),
        "cnpj": df.CNPJ_Companhia, "data_entrega": df.Data_Entrega, "data_ref": df.Data_Referencia,
        "categoria": df.Categoria, "tipo": df.Tipo, "especie": df.Especie,
        "assunto": df.Assunto, "link": df.Link_Download,
    }).drop_duplicates("protocolo")
