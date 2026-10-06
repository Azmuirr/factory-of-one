@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m factory.chief --mode %1 --scenario %2 --as-of %3 >> "runs\chief\scheduled\%1.log" 2>&1
