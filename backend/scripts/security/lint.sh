#!/usr/bin/env bash
# 代码静态检查脚本
#
# 使用 ruff（代码风格与简化检查）与 mypy（类型检查）对项目代码进行静态分析。
#
# 用法：
#   ./scripts/security/lint.sh [--fix] [--strict]
#
# 选项：
#   --fix     自动修复可修复的问题（ruff --fix）
#   --strict  严格模式，发现任何问题均以非零状态码退出（默认即严格）
#
# 退出码：
#   0 - 检查通过
#   1 - 检查发现问题

set -euo pipefail

FIX=0
STRICT=1
TARGETS=("app" "tests")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fix)
            FIX=1
            shift
            ;;
        --no-strict)
            STRICT=0
            shift
            ;;
        --strict)
            STRICT=1
            shift
            ;;
        --help|-h)
            sed -n '2,18p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

echo "=== 代码静态检查 ==="
echo "目标: ${TARGETS[*]}"
echo " 修复: $([[ ${FIX} -eq 1 ]] && echo '是' || echo '否')"
echo

HAS_ERRORS=0

# ──────────────────────────────────────────────
# ruff 检查
# ──────────────────────────────────────────────

if ! command -v ruff >/dev/null 2>&1; then
    echo "[ERROR] 未找到 ruff，请先安装：" >&2
    echo "    pip install ruff" >&2
    exit 1
fi

echo "--- ruff 检查 ---"
if [[ ${FIX} -eq 1 ]]; then
    set +e
    ruff check --fix "${TARGETS[@]}"
    EXIT_CODE=$?
    set -e
else
    set +e
    ruff check "${TARGETS[@]}"
    EXIT_CODE=$?
    set -e
fi

if [[ ${EXIT_CODE} -ne 0 ]]; then
    echo "[WARN] ruff 检查发现问题"
    HAS_ERRORS=1
else
    echo "[OK] ruff 检查通过"
fi
echo

# ──────────────────────────────────────────────
# mypy 类型检查
# ──────────────────────────────────────────────

if ! command -v mypy >/dev/null 2>&1; then
    echo "[ERROR] 未找到 mypy，请先安装：" >&2
    echo "    pip install mypy" >&2
    exit 1
fi

echo "--- mypy 类型检查 ---"
set +e
mypy "${TARGETS[@]}"
EXIT_CODE=$?
set -e

if [[ ${EXIT_CODE} -ne 0 ]]; then
    echo "[WARN] mypy 类型检查发现问题"
    HAS_ERRORS=1
else
    echo "[OK] mypy 类型检查通过"
fi
echo

# ──────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────

if [[ ${HAS_ERRORS} -eq 0 ]]; then
    echo "[OK] 全部静态检查通过"
    exit 0
else
    echo "[FAIL] 静态检查发现问题"
    if [[ ${STRICT} -eq 1 ]]; then
        exit 1
    fi
    exit 0
fi
