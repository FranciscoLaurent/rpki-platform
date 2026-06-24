#!/usr/bin/env bash
# 静态应用安全测试（SAST）脚本
#
# 使用 ruff（代码风格与简化检查）与 bandit（Python 安全漏洞扫描）
# 对项目代码进行静态安全分析。
#
# 用法：
#   ./scripts/security/run_sast.sh [--fix] [--strict] [--output <file>]
#
# 选项：
#   --fix              自动修复 ruff 可修复的问题
#   --strict           严格模式，发现任何问题均以非零状态码退出（默认即严格）
#   --no-strict        非严格模式，发现问题不阻断
#   --output <file>    将扫描报告写入指定文件（默认输出到 stdout）
#   --target <dirs>    指定扫描目标目录（默认 app tests）
#
# 退出码：
#   0 - 检查通过
#   1 - 检查发现问题（严格模式）
#   2 - 工具未安装或运行错误

set -euo pipefail

FIX=0
STRICT=1
OUTPUT_FILE=""
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
        --output)
            OUTPUT_FILE="${2:-}"
            shift 2
            ;;
        --target)
            # 支持以逗号分隔或空格分隔的多个目录
            IFS=',' read -ra TARGETS <<< "${2:-}"
            shift 2
            ;;
        --help|-h)
            sed -n '2,25p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

echo "=== 静态应用安全测试（SAST） ==="
echo "目标: ${TARGETS[*]}"
echo " 修复: $([[ ${FIX} -eq 1 ]] && echo '是' || echo '否')"
echo " 严格: $([[ ${STRICT} -eq 1 ]] && echo '是' || echo '否')"
echo

# 重定向输出到文件（若指定）
if [[ -n "${OUTPUT_FILE}" ]]; then
    exec > >(tee -a "${OUTPUT_FILE}") 2>&1
fi

HAS_ERRORS=0
TOOL_ERROR=0

# ──────────────────────────────────────────────
# ruff 检查（代码风格与简化）
# ──────────────────────────────────────────────

if ! command -v ruff >/dev/null 2>&1; then
    echo "[ERROR] 未找到 ruff，请先安装：" >&2
    echo "    pip install ruff" >&2
    TOOL_ERROR=1
else
    echo "--- ruff 代码风格检查 ---"
    echo "[INFO] ruff 版本: $(ruff --version)"
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
fi

# ──────────────────────────────────────────────
# bandit 安全漏洞扫描
# ──────────────────────────────────────────────

if ! command -v bandit >/dev/null 2>&1; then
    echo "[ERROR] 未找到 bandit，请先安装：" >&2
    echo "    pip install bandit" >&2
    TOOL_ERROR=1
else
    echo "--- bandit 安全漏洞扫描 ---"
    echo "[INFO] bandit 版本: $(bandit --version | head -n 1)"

    # 构造 bandit 扫描目标（排除测试目录以避免误报）
    BANDIT_TARGETS=()
    for target in "${TARGETS[@]}"; do
        if [[ "${target}" != "tests" && "${target}" != "test" ]]; then
            BANDIT_TARGETS+=("${target}")
        fi
    done

    if [[ ${#BANDIT_TARGETS[@]} -eq 0 ]]; then
        echo "[INFO] 无需扫描的非测试目录，跳过 bandit"
    else
        # 使用 -ll 设置最低严重级别为 LOW，-r 递归扫描
        set +e
        bandit -r "${BANDIT_TARGETS[@]}" -ll -ii -iii
        EXIT_CODE=$?
        set -e

        # bandit 退出码：0=无安全问题，1=发现安全问题，2=配置或运行错误
        if [[ ${EXIT_CODE} -eq 1 ]]; then
            echo "[WARN] bandit 发现安全问题"
            HAS_ERRORS=1
        elif [[ ${EXIT_CODE} -eq 2 ]]; then
            echo "[ERROR] bandit 运行错误"
            TOOL_ERROR=1
        else
            echo "[OK] bandit 安全扫描通过"
        fi
    fi
    echo
fi

# ──────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────

if [[ ${TOOL_ERROR} -eq 1 ]]; then
    echo "[FAIL] 部分安全工具未安装或运行错误"
    exit 2
fi

if [[ ${HAS_ERRORS} -eq 0 ]]; then
    echo "[OK] 全部静态安全检查通过"
    exit 0
else
    echo "[FAIL] 静态安全检查发现问题"
    if [[ ${STRICT} -eq 1 ]]; then
        exit 1
    fi
    exit 0
fi
