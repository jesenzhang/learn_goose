#!/bin/bash
# ✅ 关键：第一时间保存用户终端的原始工作目录（在任何 cd 操作前！）
WORK_DIR=$(pwd)  # 或使用 $(pwd)

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR"
SCRIPT_PATH=$(pwd)/$(basename "$0")
echo "脚本的完整路径是: $SCRIPT_PATH"


echo "目录完整路径是: $WORK_DIR"

cd "$WORK_DIR"

# 定义虚拟环境的路径
VENV_DIR="$WORK_DIR/.venv"

# 激活虚拟环境
source "$VENV_DIR/bin/activate"


cd "$WORK_DIR"

cd "assistant"


log_file='assistant.log'

# server_cmd='python -m assistant.main'


# 使用命令行参数传递配置
SERVER_HOST="0.0.0.0"
SERVER_PORT=8400
CONFIG_FILE="F:\Workspace\learn_goose\assistant\assistant_config.yaml"


server_cmd='ASSISTANT_LOG_FILE=${log_file} nohup python -m assistant.main --host ${SERVER_HOST} --port ${SERVER_PORT} --config ${CONFIG_FILE} \
            >/dev/null 2>&1'

eval "${server_cmd}" &

if [[ $? -eq 0 ]]; then
    echo "Waiting for assistant_server server to start..."
    result="true"
    # 使用 tail -F 监控日志文件的新增内容
    tail -F "$log_file" | while read -r log_content; do
    # 对新增的每一行进行检查
        # log_content=$(cat ${log_file})  # 读取 log 文件内容到变量
        echo "$log_content"
        if echo "$log_content" | grep -q 'To see the GUI go to:'; then
            break  # 如果找到了日志，可以退出循环
        fi
        if echo "$log_content" | grep -q 'Uvicorn running on'; then
            break  # 如果找到了日志，可以退出循环
        fi
        # 检查特定的错误信息
        if echo "$log_content" | grep -q 'Stopped server'; then
            result="false"
            break
        fi
        if echo "$log_content" | grep -q 'address already in use'; then
            echo -e "${RED}address already in use${RESET}" 
            result="false"
            break
        fi
        # 错误信息处理函数
        check_and_print_error() {
            local error_message="$1"
            if echo "$log_content" | grep -q "$error_message"; then
                # error_line=$(grep "$error_message" ${log_content})  # 打印整行内容
                # line_number=$(echo "$error_line" | cut -d':' -f1)
                echo -e "${RED}"$log_content"${RESET}" 
                echo "-----------------------------------------------"
                # if [[ ! "${printed_logs[*]}" =~ "${error_line}" ]]; then
                #     echo -e "${RED}"$error_line"${RESET}" 
                #     printed_logs+=("$error_line")  # 添加到已打印数组
                #     echo "-----------------------------------------------"
                # fi
            fi
        }

        # 检查不同的错误信息
        check_and_print_error "(IMPORT FAILED):"
        check_and_print_error "ModuleNotFoundError: No module named"
        check_and_print_error "ImportError: cannot import name"
        check_and_print_error "can't open file"
        check_and_print_error "Cannot import"
    done

    if [ "$result" = "true" ]; then
        echo "启动成功"
        echo "assistant_server start done!"
    else
        echo "启动失败"
        echo "assistant_server start failed!"
    fi
fi

exit 1
