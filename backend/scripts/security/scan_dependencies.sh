#!/usr/bin/env bash
# 依赖漏洞扫描脚本
#
# 使用 pip-audit 或 safety 对项目依赖进行已知漏洞扫描。
# 优先使用 pip-audit（基于 PyPI Advisory 数据库），不可用时降级到 safety。
#
# 用法：
#   ./scripts/security/scan_dependencies.sh [--strict] [--output <file>]
#
# 选项：
#   --strict         发现漏洞时以非零状态码退出（用于 CI 拦截）
#   --output <file>  将扫描报告写入指定文件（默认输出到 stdout）
#
# 退出码：
#   0 - 扫描成功且未发现漏洞（或未启用 --strict）
#   1 - 扫描失败（工具未安装或运行错误）
#   2 - 启用 --strict 且发现漏洞

set -euo pipefail

STRICT=0
OUTPUT_FILE=""
REQUIREMENTS_FILE="requirements.txt"
DEV_REQUIREMENTS_FILE="requirements-dev.txt"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --strict)
            STRICT=1
            shift
            ;;
        --output)
            OUTPUT_FILE="${2:-}"
            shift 2
            ;;
        --help|-h)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

echo "=== 依赖漏洞扫描 ==="
echo "工作目录: $(pwd)"
echo " requirements:   ${REQUIREMENTS_FILE}"
echo " dev-requirements: ${DEV_REQUIREMENTS_FILE}"
echo

# 重定向输出到文件（若指定）
if [[ -n "${OUTPUT_FILE}" ]]; then
    exec > >(tee -a "${OUTPUT_FILE}") 2>&1
fi

# 选择扫描工具
SCAN_TOOL=""
if command -v pip-audit >/dev/null 2>&1; then
    SCAN_TOOL="pip-audit"
elif command -v safety >/dev/null 2>&1; then
    SCAN_TOOL="safety"
else
    echo "[ERROR] 未找到 pip-audit 或 safety，请先安装：" >&2
    echo "    pip install pip-audit" >&2
    echo "  或" >&2
    echo "    pip install safety" >&2
    exit 1
fi

echo "[INFO] 使用扫描工具: ${SCAN_TOOL}"
echo

VULNERABILITIES_FOUND=0

if [[ "${SCAN_TOOL}" == "pip-audit" ]]; then
    # pip-audit 直接扫描 requirements 文件
    set +e
    pip-audit \
        --requirement "${REQUIREMENTS_FILE}" \
        --requirement "${DEV_REQUIREMENTS_FILE}" \
        --disable-pip
    EXIT_CODE=$?
    set -e
    if [[ ${EXIT_CODE} -ne 0 ]]; then
        VULNERABILITIES_FOUND=1
    fi
else
    # safety 扫描
    set +e
    safety check --file "${REQUIREMENTS_FILE}" --full-report
    EXIT_CODE=$?
    set -e
    if [[ ${EXIT_CODE} -ne 0 ]]; then
        VULNERABILITIES_FOUND=1
    fi
fi

echo
if [[ ${VULNERABILITIES_FOUND} -eq 0 ]]; then
    echo "[OK] 未发现已知依赖漏洞"
    exit 0
else
    echo "[WARN] 发现依赖漏洞，请尽快升级受影响的包"
    if [[ ${STRICT} -eq 1 ]]; then
        exit 2
    fi
    exit 0
fi
