#!/bin/bash
# uso: cadeia.sh nome script1 script2 ... (cada um em antes e depois, em sequencia)
cd /c/Users/Jeffe/Documents/study/meta
R=scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro; O=$R/refeito_2026_10_06/out
export PYTHONIOENCODING=utf-8
shift
for S in "$@"; do
  B=$(basename $S .py)
  for M in ${MODOS:-antes depois}; do
    ORB_MODO=$M ORB_LOG=$O/${B}_$M.jsonl .venv/Scripts/python.exe -u $R/refeito_2026_10_06/roda.py $R/$S > $O/${B}_$M.log 2>&1
    echo "fim $B $M" >> $O/_progresso${TAG}.txt
  done
done
