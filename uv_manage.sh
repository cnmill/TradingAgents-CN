#!/usr/bin/env bash
# 使用 uv 管理 Python 环境；不修改 pyproject.toml、uv.lock 或现有业务代码。
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

usage() {
    cat <<'EOF'
用法：bash uv_manage.sh <命令> [参数...]

命令：
  init             创建 .venv 并安装项目依赖（首次使用）
  sync             按 pyproject.toml 安装/补齐依赖（同 init）
  backend [参数]   启动后端，参数传给 uvicorn（默认 127.0.0.1:8000）
  worker [参数]    启动 Worker API（默认 127.0.0.1:8001）
  frontend-init    使用 npm ci 安装前端依赖（需要 Node.js >=18、npm >=8）
  frontend [参数] 启动前端开发服务，参数传给 Vite
  run <命令> [...] 在 .venv 中执行任意命令
  test [参数]      安装 test 可选依赖并执行 pytest
  help             显示帮助

示例：
  bash uv_manage.sh init
  bash uv_manage.sh backend --reload
  bash uv_manage.sh backend --port 9000
  bash uv_manage.sh worker
  bash uv_manage.sh frontend-init
  bash uv_manage.sh frontend
  bash uv_manage.sh frontend --host 0.0.0.0 --port 3000
  bash uv_manage.sh run python -m app.worker
  bash uv_manage.sh test tests/test_cli_version.py -q

环境变量：UV_MANAGE_PYTHON 指定创建环境的 Python 版本，默认 3.11。
请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/
启动服务前需配置 .env，并自行启动 MongoDB 和 Redis；前端仍用 npm 管理。
依赖直接来自 pyproject.toml，不使用或更新现有 uv.lock。
sync 使用可编辑安装补齐依赖，不会清除环境中的额外包或强制升级所有包。
EOF
}

action="${1:-help}"
if [[ $# -gt 0 ]]; then
    shift
fi
case "$action" in
    help|-h|--help) usage; exit 0 ;;
    init|sync|backend|worker|test|frontend|frontend-init) ;;
    run)
        if [[ $# -eq 0 ]]; then
            echo '错误：run 后需要指定命令。' >&2
            exit 2
        fi
        ;;
    *) usage >&2; exit 2 ;;
esac

# 前端独立运行，无需 uv 或 Python 虚拟环境。
if [[ "$action" == frontend || "$action" == frontend-init ]]; then
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        echo '错误：前端需要 Node.js >=18 和 npm >=8，请先安装。' >&2
        exit 1
    fi
    cd -- "$PROJECT_ROOT/frontend"
    if [[ "$action" == frontend-init ]]; then
        exec npm ci "$@"
    fi
    if [[ ! -d node_modules ]]; then
        echo '错误：前端依赖未安装，请先执行 bash uv_manage.sh frontend-init。' >&2
        exit 1
    fi
    exec npm run dev -- "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo '错误：未找到 uv，请先安装：https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
fi

cd -- "$PROJECT_ROOT"
if [[ -x "$VENV_DIR/bin/python" ]]; then
    VENV_PYTHON="$VENV_DIR/bin/python"
elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
elif [[ "$action" == init || "$action" == sync ]]; then
    uv venv --python "${UV_MANAGE_PYTHON:-3.11}" "$VENV_DIR"
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        VENV_PYTHON="$VENV_DIR/bin/python"
    else
        VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
    fi
else
    echo '错误：项目 .venv 不存在，请先执行 bash uv_manage.sh init。' >&2
    exit 1
fi

export VIRTUAL_ENV="$VENV_DIR"
export PATH="$(dirname -- "$VENV_PYTHON"):$PATH"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1

case "$action" in
    init|sync)
        uv pip install --python "$VENV_PYTHON" --editable "$PROJECT_ROOT" "$@"
        ;;
    backend)
        exec "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
        ;;
    worker)
        exec "$VENV_PYTHON" -m uvicorn app.worker.worker_app:app --host 127.0.0.1 --port 8001 "$@"
        ;;
    run)
        exec "$@"
        ;;
    test)
        uv pip install --python "$VENV_PYTHON" --editable "$PROJECT_ROOT[test]"
        exec "$VENV_PYTHON" -m pytest "$@"
        ;;
esac
