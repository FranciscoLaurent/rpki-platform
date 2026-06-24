#!/usr/bin/env bash
# 性能测试运行脚本
#
# 运行所有性能测试并输出详细计时结果。
#
# 用法：
#   ./scripts/perf/run_perf_tests.sh              # 运行全部性能测试
#   ./scripts/perf/run_perf_tests.sh prefix_tree  # 仅运行前缀树性能测试
#   ./scripts/perf/run_perf_tests.sh validation   # 仅运行验证性能测试
#   ./scripts/perf/run_perf_tests.sh detection    # 仅运行检测性能测试
#
# 环境变量：
#   PERF_SCALE  性能测试规模倍数（默认 1.0）

set -euo pipefail

# 切换到 backend 目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$BACKEND_DIR"

echo "=========================================="
echo "  RPKI 软件性能测试套件"
echo "=========================================="
echo "工作目录: $(pwd)"
echo "Python: $(python --version 2>&1)"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查 pytest 是否可用
if ! python -m pytest --version >/dev/null 2>&1; then
    echo "[错误] 未找到 pytest，请先安装开发依赖："
    echo "  pip install -r requirements-dev.txt"
    exit 1
fi

# 测试目标选择
TARGET="${1:-all}"

run_prefix_tree_perf() {
    echo "------------------------------------------"
    echo "[1/3] 前缀树性能测试"
    echo "------------------------------------------"
    python -m pytest tests/perf/test_prefix_tree_perf.py -v -s \
        --tb=short \
        -o addopts="" \
        2>&1 | tee /tmp/perf_prefix_tree.log
    echo ""
}

run_validation_perf() {
    echo "------------------------------------------"
    echo "[2/3] RPKI 验证性能测试"
    echo "------------------------------------------"
    python -m pytest tests/perf/test_validation_perf.py -v -s \
        --tb=short \
        -o addopts="" \
        2>&1 | tee /tmp/perf_validation.log
    echo ""
}

run_detection_perf() {
    echo "------------------------------------------"
    echo "[3/3] 检测引擎性能测试"
    echo "------------------------------------------"
    python -m pytest tests/perf/test_detection_perf.py -v -s \
        --tb=short \
        -o addopts="" \
        2>&1 | tee /tmp/perf_detection.log
    echo ""
}

# 根据参数运行对应测试
case "$TARGET" in
    all)
        run_prefix_tree_perf
        run_validation_perf
        run_detection_perf
        ;;
    prefix_tree)
        run_prefix_tree_perf
        ;;
    validation)
        run_validation_perf
        ;;
    detection)
        run_detection_perf
        ;;
    *)
        echo "[错误] 未知测试目标: $TARGET"
        echo "可用目标: all | prefix_tree | validation | detection"
        exit 1
        ;;
esac

echo "=========================================="
echo "  性能测试完成"
echo "=========================================="
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "测试日志:"
echo "  - /tmp/perf_prefix_tree.log"
echo "  - /tmp/perf_validation.log"
echo "  - /tmp/perf_detection.log"
