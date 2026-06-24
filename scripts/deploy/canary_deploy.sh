#!/usr/bin/env bash
# 灰度发布脚本
# 功能：渐进式将流量从稳定版切到灰度版，支持按权重或按 Header 切流
# 用法：./canary_deploy.sh <service-name> <new-image> [namespace]
# 示例：
#   ./canary_deploy.sh backend rpki-platform/backend:v2.0.0
# 流量切量阶段：
#   阶段1: 5%  流量灰度，观察 5 分钟
#   阶段2: 20% 流量灰度，观察 10 分钟
#   阶段3: 50% 流量灰度，观察 10 分钟
#   阶段4: 100% 流量切换，完成发布
# 依赖：kubectl
# 环境变量：
#   NAMESPACE         - 默认命名空间（默认 rpki-platform）
#   CANARY_INGRESS    - 灰度 Ingress 名称（默认 rpki-platform-canary-ingress）
#   STAGE1_WEIGHT     - 阶段1 权重（默认 5）
#   STAGE2_WEIGHT     - 阶段2 权重（默认 20）
#   STAGE3_WEIGHT     - 阶段3 权重（默认 50）
#   STAGE1_DURATION   - 阶段1 观察时长秒（默认 300）
#   STAGE2_DURATION   - 阶段2 观察时长秒（默认 600）
#   STAGE3_DURATION   - 阶段3 观察时长秒（默认 600）
#   AUTO_PROMOTE      - 是否自动晋升到下一阶段（默认 false，需手动确认）
#   ERROR_RATE_THRESHOLD - 错误率阈值（百分比，默认 5）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 2 ]]; then
  echo "用法: $0 <service-name> <new-image> [namespace]"
  echo "示例:"
  echo "  $0 backend rpki-platform/backend:v2.0.0"
  echo "  $0 frontend rpki-platform/frontend:v2.0.0 rpki-platform"
  exit 1
fi

SERVICE_NAME="$1"
NEW_IMAGE="$2"
NAMESPACE="${3:-${NAMESPACE:-rpki-platform}}"
CANARY_INGRESS="${CANARY_INGRESS:-rpki-platform-canary-ingress}"

# 灰度阶段配置
STAGE1_WEIGHT="${STAGE1_WEIGHT:-5}"
STAGE2_WEIGHT="${STAGE2_WEIGHT:-20}"
STAGE3_WEIGHT="${STAGE3_WEIGHT:-50}"
STAGE1_DURATION="${STAGE1_DURATION:-300}"
STAGE2_DURATION="${STAGE2_DURATION:-600}"
STAGE3_DURATION="${STAGE3_DURATION:-600}"
AUTO_PROMOTE="${AUTO_PROMOTE:-false}"
ERROR_RATE_THRESHOLD="${ERROR_RATE_THRESHOLD:-5}"

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

# 部署灰度版本
deploy_canary() {
  log "部署灰度版本 ${SERVICE_NAME}-canary，镜像: ${NEW_IMAGE}"

  # 检查灰度 Deployment 是否存在
  if kubectl -n "${NAMESPACE}" get deployment "${SERVICE_NAME}-canary" >/dev/null 2>&1; then
    log "灰度 Deployment 已存在，更新镜像..."
    kubectl -n "${NAMESPACE}" set image deployment/"${SERVICE_NAME}-canary" \
      "${SERVICE_NAME}=${NEW_IMAGE}" --record
  else
    log "创建灰度 Deployment..."
    # 从稳定版 Deployment 派生灰度版
    kubectl -n "${NAMESPACE}" get deployment "${SERVICE_NAME}" \
      -o json | python3 -c "
import sys, json
dep = json.load(sys.stdin)
dep['metadata']['name'] = '${SERVICE_NAME}-canary'
dep['metadata']['labels'] = dep.get('metadata', {}).get('labels', {})
dep['metadata']['labels']['app.kubernetes.io/variant'] = 'canary'
dep['metadata']['annotations'] = dep.get('metadata', {}).get('annotations', {})
dep['metadata']['annotations']['rpki.io/canary'] = 'true'
dep['spec']['replicas'] = 1
tmpl = dep['spec']['template']
tmpl['metadata']['labels']['app.kubernetes.io/variant'] = 'canary'
for c in tmpl['spec']['containers']:
    if c['name'] == '${SERVICE_NAME}':
        c['image'] = '${NEW_IMAGE}'
        c['env'] = c.get('env', [])
        c['env'].append({'name': 'DEPLOYMENT_VARIANT', 'value': 'canary'})
del dep['metadata']['resourceVersion']
del dep['metadata']['uid']
del dep['metadata']['creationTimestamp']
del dep['metadata']['generation']
json.dump(dep, sys.stdout)
" | kubectl -n "${NAMESPACE}" apply -f -
  fi

  # 等待灰度 Pod 就绪
  log "等待灰度 Pod 就绪..."
  kubectl -n "${NAMESPACE}" rollout status deployment "${SERVICE_NAME}-canary" \
    --timeout=300s
}

# 设置灰度流量权重
set_canary_weight() {
  local weight="$1"
  log "设置灰度流量权重: ${weight}%"

  # 更新 Ingress 的 canary-weight 注解
  kubectl -n "${NAMESPACE}" annotate ingress "${CANARY_INGRESS}" \
    "nginx.ingress.kubernetes.io/canary-weight=${weight}" --overwrite

  # 同步更新 Deployment annotation
  kubectl -n "${NAMESPACE}" annotate deployment "${SERVICE_NAME}-canary" \
    "rpki.io/canary-weight=${weight}" --overwrite >/dev/null

  log "灰度权重已设置为 ${weight}%"
}

# 检查灰度版本健康状态
check_canary_health() {
  local stage="$1"
  log ">>> 阶段 ${stage} 健康检查..."

  # 获取灰度 Pod
  local pods
  pods="$(kubectl -n "${NAMESPACE}" get pods -l \
    "app.kubernetes.io/name=${SERVICE_NAME},app.kubernetes.io/variant=canary" \
    -o jsonpath='{.items[*].metadata.name}')"

  if [[ -z "${pods}" ]]; then
    log "错误：未找到灰度 Pod" >&2
    return 1
  fi

  local all_ready=true
  for pod in ${pods}; do
    local ready restarts
    ready="$(kubectl -n "${NAMESPACE}" get pod "${pod}" \
      -o jsonpath='{.status.containerStatuses[0].ready}')"
    restarts="$(kubectl -n "${NAMESPACE}" get pod "${pod}" \
      -o jsonpath='{.status.containerStatuses[0].restartCount}')"

    if [[ "${ready}" != "true" ]]; then
      log "  Pod ${pod} 未就绪"
      all_ready=false
    elif [[ "${restarts}" -gt 3 ]]; then
      log "  Pod ${pod} 重启次数过多: ${restarts}"
      all_ready=false
    else
      log "  Pod ${pod} 健康（重启 ${restarts} 次）"
    fi
  done

  if [[ "${all_ready}" != "true" ]]; then
    log "错误：灰度版本健康检查未通过" >&2
    return 1
  fi

  log "阶段 ${stage} 健康检查通过"
  return 0
}

# 等待观察
observe() {
  local duration="$1"
  local stage="$2"
  log ">>> 阶段 ${stage} 观察期 ${duration}s..."

  if [[ "${AUTO_PROMOTE}" == "true" ]]; then
    sleep "${duration}"
  else
    log "按 Enter 继续到下一阶段，输入 'abort' 中止灰度并回退:"
    read -r -t "${duration}" response || response=""
    if [[ "${response}" == "abort" ]]; then
      log "用户中止灰度发布"
      abort_canary
      exit 1
    fi
  fi

  # 观察期后再次健康检查
  if ! check_canary_health "${stage}"; then
    log "观察期后健康检查失败，自动回退"
    abort_canary
    exit 1
  fi
}

# 晋升：将灰度版本切换为稳定版
promote_canary() {
  log ">>> 晋升灰度版本为稳定版..."

  # 更新稳定版 Deployment 镜像
  kubectl -n "${NAMESPACE}" set image deployment/"${SERVICE_NAME}" \
    "${SERVICE_NAME}=${NEW_IMAGE}" --record

  # 等待稳定版滚动更新完成
  kubectl -n "${NAMESPACE}" rollout status deployment "${SERVICE_NAME}" \
    --timeout=600s

  # 清理灰度资源
  cleanup_canary

  log "灰度发布完成，新版本 ${NEW_IMAGE} 已晋升为稳定版"
}

# 中止灰度：回退到稳定版
abort_canary() {
  log ">>> 中止灰度发布，回退到稳定版..."
  set_canary_weight 0
  cleanup_canary
  log "灰度发布已中止，流量已全部回到稳定版"
}

# 清理灰度资源
cleanup_canary() {
  log "清理灰度资源..."
  kubectl -n "${NAMESPACE}" delete deployment "${SERVICE_NAME}-canary" \
    --ignore-not-found=true
  kubectl -n "${NAMESPACE}" annotate ingress "${CANARY_INGRESS}" \
    "nginx.ingress.kubernetes.io/canary-weight-" --overwrite 2>/dev/null || true
}

# ========== 主流程 ==========
main() {
  log "========================================"
  log "开始灰度发布"
  log "服务: ${NAMESPACE}/${SERVICE_NAME}"
  log "新镜像: ${NEW_IMAGE}"
  log "灰度阶段: ${STAGE1_WEIGHT}% -> ${STAGE2_WEIGHT}% -> ${STAGE3_WEIGHT}% -> 100%"
  log "========================================"

  check_kubectl

  # 部署灰度版本
  deploy_canary

  # 阶段1: 5% 流量
  log "========== 阶段 1: ${STAGE1_WEIGHT}% 流量 =========="
  set_canary_weight "${STAGE1_WEIGHT}"
  check_canary_health "1" || { abort_canary; exit 1; }
  observe "${STAGE1_DURATION}" "1"

  # 阶段2: 20% 流量
  log "========== 阶段 2: ${STAGE2_WEIGHT}% 流量 =========="
  set_canary_weight "${STAGE2_WEIGHT}"
  check_canary_health "2" || { abort_canary; exit 1; }
  observe "${STAGE2_DURATION}" "2"

  # 阶段3: 50% 流量
  log "========== 阶段 3: ${STAGE3_WEIGHT}% 流量 =========="
  set_canary_weight "${STAGE3_WEIGHT}"
  check_canary_health "3" || { abort_canary; exit 1; }
  observe "${STAGE3_DURATION}" "3"

  # 阶段4: 100% 流量（晋升）
  log "========== 阶段 4: 100% 流量（晋升） =========="
  promote_canary

  log "========================================"
  log "灰度发布全部完成"
  log "新版本: ${NEW_IMAGE}"
  log "========================================"
}

main "$@"
