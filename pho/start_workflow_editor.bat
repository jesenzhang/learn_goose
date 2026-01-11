@echo off
REM Start Pho Workflow Editor (Windows)

set STREAMLIT_EMAIL=
set PYTHONPATH=%cd%\src;%PYTHONPATH%

echo Starting Pho Workflow Editor...
echo.

"D:\miniforge3\python.exe" -m streamlit run src/pho/web/workflow_editor.py --server.headless=true --server.port=8501

pause
