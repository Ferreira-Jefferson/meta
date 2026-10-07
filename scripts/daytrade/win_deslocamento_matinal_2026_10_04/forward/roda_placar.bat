@echo off
cd /d C:\Users\Jeffe\Documents\study\meta
echo === %date% %time% >> scripts\daytrade\win_deslocamento_matinal_2026_10_04\forward\placar_forward.log
.\.venv\Scripts\python.exe scripts\daytrade\win_deslocamento_matinal_2026_10_04\forward\placar_forward.py >> scripts\daytrade\win_deslocamento_matinal_2026_10_04\forward\placar_forward.log 2>&1
