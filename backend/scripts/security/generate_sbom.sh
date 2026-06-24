#!/usr/bin/env bash
# SBOM (Software Bill of Materials) 生成脚本
#
# 使用 cyclonedx-py 生成项目依赖的 SBOM 文档，输出为 CycloneDX 标准格式。
# 支持输出 JSON 与 XML 两种格式。
#
# 用法：
#   ./scripts/security/generate_sbom.sh [--format json|xml] [--output <file>]
#
# 选项：
#   --format <fmt>    SBOM 格式：json（默认）或 xml
#   --output <file>   输出文件路径（默认：sbom.<format>）
#
# 退出码：
#   0 - SBOM 生成成功
#   1 - 工具未安装或生成失败

set -euo pipefail

FORMAT="json"
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --format)
            FORMAT="${2:-json}"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="${2:-}"
            shift 2
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

case "${FORMAT}" in
    json|xml) ;;
    *)
        echo "[ERROR] 不支持的格式: ${FORMAT}（仅支持 json 或 xml）" >&2
        exit 1
        ;;
esac

if [[ -z "${OUTPUT_FILE}" ]]; then
    OUTPUT_FILE="sbom.${FORMAT}"
fi

echo "=== SBOM 生成 ==="
echo "格式: ${FORMAT}"
echo "输出: ${OUTPUT_FILE}"
echo

# 检查 cyclonedx-py 是否安装
if ! command -v cyclonedx-py >/dev/null 2>&1; then
    echo "[ERROR] 未找到 cyclonedx-py，请先安装：" >&2
    echo "    pip install cyclonedx-bom" >&2
    exit 1
fi

# 使用 cyclonedx-py 从 requirements.txt 生成 SBOM
# 优先使用 requirements.txt；若存在 pyproject.toml 也可使用
if [[ -f "requirements.txt" ]]; then
    echo "[INFO] 基于 requirements.txt 生成 SBOM"
    set +e
    if [[ "${FORMAT}" == "json" ]]; then
        cyclonedx-py --format json --output "${OUTPUT_FILE}" -r -i requirements.txt
    else
        cyclonedx-py --format xml --output "${OUTPUT_FILE}" -r -i requirements.txt
    fi
    EXIT_CODE=$?
    set -e
else
    echo "[ERROR] 未找到 requirements.txt" >&2
    exit 1
fi

if [[ ${EXIT_CODE} -ne 0 ]]; then
    echo "[ERROR] SBOM 生成失败" >&2
    exit 1
fi

echo
echo "[OK] SBOM 已生成: ${OUTPUT_FILE}"
echo "     文件大小: $(du -h "${OUTPUT_FILE}" | cut -f1)"
exit 0
