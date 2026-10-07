#!/bin/bash
# uso: run_chain.sh 2125|2120
C=$1
HERE="$(cd "$(dirname "$0")" && pwd -W)"
export PYTHONPATH="$HERE/_sc" A1_CORTE=$C A1_MAXW=5 PYTHONIOENCODING=utf-8
PY=C:/Users/Jeffe/Documents/study/meta/.venv/Scripts/python.exe
D=C:/Users/Jeffe/Documents/study/meta/scripts/daytrade
for s in copawin_piso_sobrevivencia_2026_08_29 copawin_dimensionamento_por_risco_2026_08_29 copawin_recomendacao_final_2026_09_11 copawin_candidato_a76_validacao_2026_09_11 copawin_300_reais_acerto_90_2026_09_13 copawin_300_alvo_fino_sensibilidade_fila_2026_09_13 copawin_300_robustez_por_data_de_inicio_2026_09_13 wdo_win_padrao_dia_horario_2026_09_04 wdo_win_filtro_dia_horario_impacto_2026_09_04 copawin_grade_constancia_2026_09_11 copawin_finalistas_robustez_2026_09_11 copawin_robustez_por_data_de_inicio_2026_09_11 copawin_freios_e_corte_2026_09_11 copawin_consistencia_diagnostico_2026_09_11 copawin_ratchet_skim_teste_2026_08_29; do
  echo "[$(date +%T)] $s" >> $HERE/out/chain_$C.txt
  A1_LOG=$HERE/out/stats_$C.jsonl $PY -u $D/$s.py > $HERE/out/${s}_$C.log 2>&1
  echo "[$(date +%T)] fim $s rc=$?" >> $HERE/out/chain_$C.txt
done
echo FIM >> $HERE/out/chain_$C.txt
