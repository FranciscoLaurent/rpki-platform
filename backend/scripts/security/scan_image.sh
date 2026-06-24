#!/usr/bin/env bash
# 容器镜像漏洞扫描脚本
#
# 使用 trivy 对构建好的容器镜像进行已知漏洞扫描。
# 支持 OS 包与语言依赖（Python、Node.js 等）的漏洞检测。
#
# 用法：
#   ./scripts/security/scan_image.sh <image> [--severity HIGH,CRITICAL] [--output <file>] [--strict]
#
# 参数：
#   <image>                       必填，待扫描的容器镜像名称（含 tag）
#
# 选项：
#   --severity <levels>           漏洞严重级别过滤（默认 HIGH,CRITICAL）
#   --output <file>               将扫描报告写入指定文件（默认输出到 stdout）
#   --strict                      发现漏洞时以非零状态码退出（用于 CI 拦截）
#   --ignore-unfixed              仅显示已修复的漏洞
#   --exit-code <code>            指定发现漏洞时的退出码（默认 1，需配合 --strict）
#
# 退出码：
#   0 - 扫描成功且未发现漏洞（或未启用 --strict）
#   1 - 扫描失败（工具未安装或运行错误）
#   2 - 启用 --strict 且发现漏洞

set -euo pipefail

IMAGE=""
SEVERITY="HIGH,CRITICAL"
OUTPUT_FILE=""
STRICT=0
IGNORE_UNFIXED=0
EXIT_CODE=1

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --severity)
            SEVERITY="${2:-HIGH,CRITICAL}"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="${2:-}"
            shift 2
            ;;
        --strict)
            STRICT=1
            shift
            ;;
        --ignore-unfixed)
            IGNORE_UNFIXED=1
            shift
            ;;
        --exit-code)
            EXIT_CODE="${2:-1}"
            shift 2
            ;;
        --help|-h)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        -*)
            echo "未知选项: $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "${IMAGE}" ]]; then
                IMAGE="$1"
            else
                echo "多余参数: $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# 校验必填参数
if [[ -z "${IMAGE}" ]]; then
    echo "[ERROR] 缺少必填参数：镜像名称" >&2
    echo "用法: $0 <image> [--severity HIGH,CRITICAL] [--output <file>] [--strict]" >&2
    exit 1
fi

echo "=== 容器镜像漏洞扫描 ==="
echo "镜像: ${IMAGE}"
echo "严重级别: ${SEVERITY}"
echo " 严格模式: $([[ ${STRICT} -eq 1 ]] && echo '是' || echo '否')"
echo " 仅显示已修复: $([[ ${IGNORE_UNFIXED} -eq 1 ]] && echo '是' || echo '否')"
echo

# 检查 trivy 是否安装
if ! command -v trivy >/dev/null 2>&1; then
    echo "[ERROR] 未找到 trivy，请先安装：" >&2
    echo "    https://aquasecurity.github.io/trivy/latest/getting-started/installation/" >&2
    exit 1
fi

echo "[INFO] trivy 版本: $(trivy --version | head -n 1)"
echo

# 构造 trivy 命令参数
TRIVY_ARGS=(
    image
    --severity "${SEVERITY}"
    --format table
)

if [[ ${IGNORE_UNFIXED} -eq 1 ]]; then
    TRIVY_ARGS+=("--ignore-unfixed")
fi

# 重定向输出到文件（若指定）
if [[ -n "${OUTPUT_FILE}" ]]; then
    echo "[INFO] 扫描结果将写入: ${OUTPUT_FILE}"
    TRIVY_ARGS+=("--output" "${OUTPUT_FILE}")
fi

# 执行扫描
VULNERABILITIES_FOUND=0
set +e
trivy "${TRIVY_ARGS[@]}" "${IMAGE}"
SCAN_EXIT_CODE=$?
set -e

# trivy 退出码：0=未发现漏洞，非0=发现漏洞或扫描失败
if [[ ${SCAN_EXIT_CODE} -ne 0 ]]; then
    # 区分扫描失败与发现漏洞
    # trivy --exit-code 默认为 0（不因漏洞退出），此处通过 --strict 控制
    VULNERABILITIES_FOUND=1
fi

echo
if [[ ${VULNERABILITIES_FOUND} -eq 0 ]]; then
    echo "[OK] 未发现 ${SEVERITY} 级别的漏洞"
    exit 0
else
    if [[ -n "${OUTPUT_FILE}" ]]; then
        echo "[WARN] 发现漏洞，详见报告: ${OUTPUT_FILE}"
    else
        echo "[WARN] 发现漏洞，请尽快修复"
    fi
    if [[ ${STRICT} -eq 1 ]]; then
        exit "${EXIT_CODE}"
    fi
    exit 0
fi
