# Start Pho Workflow Editor (PowerShell)

$env:STREAMLIT_EMAIL = ""
$env:PYTHONPATH = "src;$env:PYTHONPATH"

Write-Host "Starting Pho Workflow Editor..." -ForegroundColor Green
Write-Host ""

& "D:\miniforge3\python.exe" -m streamlit run src/pho/web/workflow_editor.py --server.headless=true --server.port=8501
