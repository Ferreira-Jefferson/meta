#!/bin/bash
C=$1
HERE="$(cd "$(dirname "$0")" && pwd -W)"
export PYTHONPATH="$HERE/_sc" A1_CORTE=$C A1_MAXW=5 A1_LEGADO=1 PYTHONIOENCODING=utf-8
PY=C:/Users/Jeffe/Documents/study/meta/.venv/Scripts/python.exe
D=C:/Users/Jeffe/Documents/study/meta/scripts/daytrade
for s in copawin_piso_sobrevivencia_2026_08_29 copawin_dimensionamento_por_risco_2026_08_29 copawin_seguranca_capital_alto_2026_08_29; do
  [ -f $D/$s.py ] || continue
  A1_LOG=$HERE/out/stats_leg_$C.jsonl $PY -u $D/$s.py > $HERE/out/${s}_LEG_$C.log 2>&1
done
echo FIM > $HERE/out/leg_$C.txt
