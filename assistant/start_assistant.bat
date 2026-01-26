@echo off
setlocal enabledelayedexpansion

REM 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
echo 脚本目录: %SCRIPT_DIR%

REM 设置工作目录
set "WORK_DIR=%SCRIPT_DIR%"
echo 工作目录: %WORK_DIR%

REM 激活虚拟环境
set "VENV_DIR=%WORK_DIR%\venv"
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo 警告: 未找到虚拟环境，假设依赖已安装
)

REM 切换到assistant目录
cd /d "%WORK_DIR%\assistant"

REM 设置默认参数
set "SERVER_HOST=0.0.0.0"
set "SERVER_PORT=8400"
set "CONFIG_FILE=assistant_config.yaml"

REM 检查命令行参数
:parse_args
if "%~1"=="" goto start_server
if "%~1"=="--host" (
    set "SERVER_HOST=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--port" (
    set "SERVER_PORT=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--config" (
    set "CONFIG_FILE=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:start_server
echo Starting server on %SERVER_HOST%:%SERVER_PORT% with config %CONFIG_FILE%

REM 启动服务器
python -m assistant.main --host %SERVER_HOST% --port %SERVER_PORT% --config %CONFIG_FILE%

pause