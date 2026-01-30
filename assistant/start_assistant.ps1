# PowerShell启动脚本
Write-Host "脚本目录: $(Split-Path -Parent $MyInvocation.MyCommand.Path)"

# 设置工作目录
$WORK_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "工作目录: $WORK_DIR"

# 激活虚拟环境
$VENV_DIR = Join-Path $WORK_DIR "venv"
if (Test-Path "$VENV_DIR\Scripts\Activate.ps1") {
    & "$VENV_DIR\Scripts\Activate.ps1"
} else {
    Write-Host "警告: 未找到虚拟环境，假设依赖已安装" -ForegroundColor Yellow
}

# 切换到assistant目录
Set-Location "$WORK_DIR\assistant"

# 设置默认参数
$SERVER_HOST = "0.0.0.0"
$SERVER_PORT = 8400
$CONFIG_FILE = "assistant_config.yaml"
$LOG_FILE = "assistant.log"

# 解析命令行参数
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "--host" -and $i + 1 -lt $args.Count) {
        $SERVER_HOST = $args[++$i]
    } elseif ($args[$i] -eq "--port" -and $i + 1 -lt $args.Count) {
        $SERVER_PORT = [int]$args[++$i]
    } elseif ($args[$i] -eq "--config" -and $i + 1 -lt $args.Count) {
        $CONFIG_FILE = $args[++$i]
    } elseif ($args[$i] -eq "--log" -and $i + 1 -lt $args.Count) {
        $LOG_FILE = $args[++$i]
    }
}

Write-Host "Starting server on $SERVER_HOST`:$SERVER_PORT with config $CONFIG_FILE" -ForegroundColor Green

# 启动服务器（日志输出到指定文件）
$env:ASSISTANT_LOG_FILE = $LOG_FILE
Start-Process -FilePath "python" -ArgumentList "-m", "assistant.main", "--host", $SERVER_HOST, "--port", $SERVER_PORT, "--config", $CONFIG_FILE
