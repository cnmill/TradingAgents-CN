#!/bin/bash
# 快速检查数据时效性的便捷脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR" || exit 1

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "❌ 虚拟环境不存在，请先执行: bash uv_manage.sh init"
    exit 1
fi

# 运行检查脚本
python scripts/check_data_freshness.py "$@"
