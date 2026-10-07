from lente3_base import *
for nome, cfg in [('defeito', Cfg(modo_defeito=True)), ('corr_semSL', Cfg(alvo_frac=None, stop_frac=None)), ('corr_default', Cfg())]:
    t = run(cfg)
    print(nome, len(t), 'rs', round(t.rs.sum()), t.groupby('mes').rs.agg(['sum','count']).round(0).to_dict(), t.saida.value_counts().to_dict())
