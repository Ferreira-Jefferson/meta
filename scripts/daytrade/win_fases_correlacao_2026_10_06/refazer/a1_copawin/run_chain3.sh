#!/bin/bash
# uso: run_chain3.sh CORTE FIM script...   (legado + base truncada em FIM)
C=$1; F=$2; shift 2
HERE="$(cd "$(dirname "$0")" && pwd -W)"
export PYTHONPATH="$HERE/_sc" A1_CORTE=$C A1_MAXW=4 PYTHONIOENCODING=utf-8 A1_FIM=$F
[ "${LEG:-1}" = 1 ] && export A1_LEGADO=1
PY=C:/Users/Jeffe/Documents/study/meta/.venv/Scripts/python.exe
D=C:/Users/Jeffe/Documents/study/meta/scripts/daytrade
for s in "$@"; do
  echo "[$(date +%T)] $s" >> $HERE/out/chain_fim${F}${ARG:+_$ARG}_$C.txt
  A1_LOG=$HERE/out/stats_fim${F}_$C.jsonl $PY -u $D/$s.py $ARG > $HERE/out/${s}${ARG:+_$ARG}__fim${F}_$C.log 2>&1
  echo "[$(date +%T)] fim $s rc=$?" >> $HERE/out/chain_fim${F}${ARG:+_$ARG}_$C.txt
done
echo FIM >> $HERE/out/chain_fim${F}${ARG:+_$ARG}_$C.txt
