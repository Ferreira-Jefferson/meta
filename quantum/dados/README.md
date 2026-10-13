# quantum/dados — a base de arquivos

Fora do git (centenas de MB), mas completa e reprocessável: apagar `quantum.sqlite`
e rodar `python -m quantum atualizar --sem-estudos` reconstrói tudo a partir de `brutos/`
sem baixar de novo o que já está aqui.

```
dados/
├── brutos/                     arquivo ORIGINAL de cada fonte, nunca editado
│   ├── cvm/
│   │   ├── cad/                cad_cia_aberta.csv            cadastro de companhias
│   │   ├── fca/                fca_cia_aberta_AAAA.zip       tickers, site de RI
│   │   ├── dfp/                dfp_cia_aberta_AAAA.zip       demonstrações anuais
│   │   ├── itr/                itr_cia_aberta_AAAA.zip       demonstrações trimestrais
│   │   └── ipe/                ipe_cia_aberta_AAAA.zip       documentos publicados pelo RI
│   ├── cvm_docs/<cnpj>/        <protocolo>.pdf               PDFs do RI da lista curta
│   ├── yahoo/precos/           <TICKER>.csv (IDX_BVSP.csv = Ibovespa)
│   ├── bcb/cdi/                sgs12_AAAA_AAAA.json          CDI diário em janelas de 5 anos
│   └── balancos/               (só se configurado — fonte paga)
├── derivados/textos/           texto extraído de cada PDF (cache; regenerável)
├── manifesto.csv               caminho, fonte, url, coletado_em, bytes, sha256 de CADA bruto
├── quantum.sqlite              tabelas tratadas (empresas, tickers, demonstracoes, precos,
│                               indices, documentos, execucoes, estudos, revelacoes)
└── estudos/<AAAA-MM-DD_HHMM>/  cada rodada: resumo.csv, grade_is_<estrategia>.csv, rodada.json
```

Regras:
- **Ano fechado é congelado.** CVM de anos anteriores ao ano passado não é rebaixada.
  Ano corrente e anterior são rebaixados após 20h (a CVM recebe reapresentações).
- **Preços são rebaixados inteiros** a cada atualização: o preço ajustado muda para trás
  a cada provento novo, então emendar só os dias novos misturaria dois ajustes.
- **Toda escrita passa por `fontes/arquivo.py`**, que grava o manifesto. Arquivo fora do
  manifesto não foi baixado pelo sistema. Não coloque arquivos à mão em `brutos/`.
- CSVs de estudos usam `;` e vírgula decimal (abrem direto no Excel em pt-BR).
