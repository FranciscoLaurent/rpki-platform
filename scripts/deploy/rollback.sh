#!/usr/bin/env bash
# 版本回退脚本
# 功能：将 Deployment 回退到上一个版本或指定版本
# 用法：./rollback.sh <deployment-name> [revision] [namespace]
# 示例：
#   ./rollback.sh backend                  # 回退到上一版本
#   ./rollback.sh backend 3                # 回退到 revision 3
#   ./rollback.sh backend "" rpki-platform # 指定命名空间
# 依赖：kubectl
# 环境变量：
#   NAMESPACE       - 默认命名空间（默认 rpki-platform）
#   ROLLOUT_TIMEOUT - 滚动超时秒数（默认 600）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <deployment-name> [revision] [namespace]"
  echo "示例:"
  echo "  $0 backend                  # 回退到上一版本"
  echo "  $0 backend 3                # 回退到 revision 3"
  echo "  $0 backend '' rpki-platform # 指定命名空间"
  exit 1
fi

DEPLOYMENT_NAME="$1"
REVISION="${2:-}"
NAMESPACE="${3:-${NAMESPACE:-rpki-platform}}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-600}"

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

check_kubectl() {
  if ! command -v kubectl >/dev/null 2>&1; then
    log "错误：未找到 kubectl 命令" >&2
    exit 1
  fi
}

check_deployment() {
  if ! kubectl -n "${NAMESPACE}" get deployment "${DEPLOYMENT_NAME}" >/dev/null 2>&1; then
    log "错误：Deployment ${NAMESPACE}/${DEPLOYMENT_NAME} 不存在" >&2
    exit 1
  fi
}

# 显示修订历史
show_history() {
  log "当前 Deployment 修订历史:"
  kubectl -n "${NAMESPACE}" rollout history deployment "${DEPLOYMENT_NAME}"
}

# ========== 主流程 ==========
main() {
  log "========================================"
  log "开始版本回退"
  log "Deployment: ${NAMESPACE}/${DEPLOYMENT_NAME}"
  if [[ -n "${REVISION}" ]]; then
    log "目标版本: revision ${REVISION}"
  else
    log "目标版本: 上一版本"
  fi
  log "========================================"

  check_kubectl
  check_deployment
  show_history

  # 执行回退
  log "触发回退..."
  if [[ -n "${REVISION}" ]]; then
    kubectl -n "${NAMESPACE}" rollout undo deployment "${DEPLOYMENT_NAME}" \
      --to-revision="${REVISION}"
  else
    kubectl -n "${NAMESPACE}" rollout undo deployment "${DEPLOYMENT_NAME}"
  fi

  # 等待回退完成
  log "等待回退完成（超时 ${ROLLOUT_TIMEOUT}s）..."
  if kubectl -n "${NAMESPACE}" rollout status deployment "${DEPLOYMENT_NAME}" \
    --timeout="${ROLLOUT_TIMEOUT}s"; then
    log "回退成功完成"
  else
    log "错误：回退超时或失败" >&2
    exit 1
  fi

  # 显示回退后的镜像版本
  local current_image
  current_image="$(kubectl -n "${NAMESPACE}" get deployment "${DEPLOYMENT_NAME}" \
    -o jsonpath='{.spec.template.spec.containers[0].image}')"
  log "当前镜像版本: ${current_image}"

  log "========================================"
  log "版本回退完成"
  log "========================================"
}

main "$@"
