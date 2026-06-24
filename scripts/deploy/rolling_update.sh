#!/usr/bin/env bash
# 滚动升级脚本
# 功能：触发 Kubernetes Deployment 滚动更新，并等待滚动完成
# 用法：./rolling_update.sh <deployment-name> <new-image> [namespace]
# 示例：
#   ./rolling_update.sh backend rpki-platform/backend:v1.2.0
#   ./rolling_update.sh frontend rpki-platform/frontend:v1.2.0 rpki-platform
# 依赖：kubectl
# 环境变量：
#   NAMESPACE      - 默认命名空间（默认 rpki-platform）
#   ROLLOUT_TIMEOUT- 滚动超时秒数（默认 600）
#   MAX_UNAVAILABLE- 最大不可用比例（默认 25%）
#   MAX_SURGE      - 最大超出比例（默认 25%）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 2 ]]; then
  echo "用法: $0 <deployment-name> <new-image> [namespace]"
  echo "示例:"
  echo "  $0 backend rpki-platform/backend:v1.2.0"
  echo "  $0 frontend rpki-platform/frontend:v1.2.0 rpki-platform"
  exit 1
fi

DEPLOYMENT_NAME="$1"
NEW_IMAGE="$2"
NAMESPACE="${3:-${NAMESPACE:-rpki-platform}}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-600}"
MAX_UNAVAILABLE="${MAX_UNAVAILABLE:-25%}"
MAX_SURGE="${MAX_SURGE:-25%}"

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 检查 kubectl 是否可用
check_kubectl() {
  if ! command -v kubectl >/dev/null 2>&1; then
    log "错误：未找到 kubectl 命令" >&2
    exit 1
  fi
  if ! kubectl cluster-info >/dev/null 2>&1; then
    log "错误：无法连接 Kubernetes 集群" >&2
    exit 1
  fi
}

# 检查 Deployment 是否存在
check_deployment() {
  if ! kubectl -n "${NAMESPACE}" get deployment "${DEPLOYMENT_NAME}" >/dev/null 2>&1; then
    log "错误：Deployment ${NAMESPACE}/${DEPLOYMENT_NAME} 不存在" >&2
    exit 1
  fi
}

# 记录当前镜像版本（用于回退）
record_current_image() {
  local current_image
  current_image="$(kubectl -n "${NAMESPACE}" get deployment "${DEPLOYMENT_NAME}" \
    -o jsonpath='{.spec.template.spec.containers[0].image}')"
  log "当前镜像版本: ${current_image}"
  log "新镜像版本: ${NEW_IMAGE}"

  # 记录到 annotation 便于回退
  kubectl -n "${NAMESPACE}" annotate deployment "${DEPLOYMENT_NAME}" \
    "rpki.io/previous-image=${current_image}" --overwrite >/dev/null
}

# 等待滚动完成
wait_for_rollout() {
  log "等待滚动更新完成（超时 ${ROLLOUT_TIMEOUT}s）..."
  if kubectl -n "${NAMESPACE}" rollout status deployment "${DEPLOYMENT_NAME}" \
    --timeout="${ROLLOUT_TIMEOUT}s"; then
    log "滚动更新成功完成"
  else
    log "错误：滚动更新超时或失败" >&2
    log "可执行回退: kubectl -n ${NAMESPACE} rollout undo deployment ${DEPLOYMENT_NAME}" >&2
    exit 1
  fi
}

# 健康检查
health_check() {
  log "执行健康检查..."
  local pods
  pods="$(kubectl -n "${NAMESPACE}" get pods -l "app.kubernetes.io/name=${DEPLOYMENT_NAME}" \
    -o jsonpath='{.items[*].metadata.name}')"

  if [[ -z "${pods}" ]]; then
    log "警告：未找到 ${DEPLOYMENT_NAME} 的 Pod"
    return
  fi

  local all_ready=true
  for pod in ${pods}; do
    local ready
    ready="$(kubectl -n "${NAMESPACE}" get pod "${pod}" \
      -o jsonpath='{.status.containerStatuses[0].ready}')"
    if [[ "${ready}" != "true" ]]; then
      log "  Pod ${pod} 未就绪"
      all_ready=false
    else
      log "  Pod ${pod} 就绪"
    fi
  done

  if [[ "${all_ready}" == "true" ]]; then
    log "所有 Pod 均已就绪"
  else
    log "警告：部分 Pod 未就绪，请检查" >&2
  fi
}

# ========== 主流程 ==========
main() {
  log "========================================"
  log "开始滚动更新"
  log "Deployment: ${NAMESPACE}/${DEPLOYMENT_NAME}"
  log "新镜像: ${NEW_IMAGE}"
  log "========================================"

  check_kubectl
  check_deployment
  record_current_image

  # 更新镜像
  log "触发滚动更新..."
  kubectl -n "${NAMESPACE}" set image deployment/"${DEPLOYMENT_NAME}" \
    "${DEPLOYMENT_NAME}=${NEW_IMAGE}" --record

  # 等待完成
  wait_for_rollout

  # 健康检查
  health_check

  log "========================================"
  log "滚动更新完成"
  log "如需回退，请执行:"
  log "  kubectl -n ${NAMESPACE} rollout undo deployment ${DEPLOYMENT_NAME}"
  log "或:"
  log "  ./rollback.sh ${DEPLOYMENT_NAME}"
  log "========================================"
}

main "$@"
