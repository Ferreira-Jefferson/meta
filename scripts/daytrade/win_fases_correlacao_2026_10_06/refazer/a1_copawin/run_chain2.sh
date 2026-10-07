#!/bin/bash
# uso: run_chain2.sh CORTE MODO(leg|atual) script1 script2 ...
C=$1; M=$2; shift 2
HERE="$(cd "$(dirname "$0")" && pwd -W)"
export PYTHONPATH="$HERE/_sc" A1_CORTE=$C A1_MAXW=4 PYTHONIOENCODING=utf-8
[ "$M" = leg ] && export A1_LEGADO=1
PY=C:/Users/Jeffe/Documents/study/meta/.venv/Scripts/python.exe
D=C:/Users/Jeffe/Documents/study/meta/scripts/daytrade
for s in "$@"; do
  echo "[$(date +%T)] $s" >> $HERE/out/chain_${M}_$C.txt
  A1_LOG=$HERE/out/stats_${M}_$C.jsonl $PY -u $D/$s.py > $HERE/out/${s}__${M}_$C.log 2>&1
  echo "[$(date +%T)] fim $s rc=$?" >> $HERE/out/chain_${M}_$C.txt
done
echo FIM >> $HERE/out/chain_${M}_$C.txt
