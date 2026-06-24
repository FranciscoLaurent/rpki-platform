#!/usr/bin/env bash
# 统一备份入口脚本
# 功能：依次执行 PostgreSQL、Redis、ClickHouse 备份，并汇总结果
# 用法：./backup_all.sh [--parallel|--sequential]
# 依赖：backup_postgres.sh, backup_redis.sh, backup_clickhouse.sh
# 环境变量：继承各子脚本的环境变量
#   BACKUP_DIR       - 统一备份根目录（默认 /data/backups）
#   BACKUP_MODE      - 备份模式 parallel/sequential（默认 sequential）
#   NOTIFY_WEBHOOK   - 备份完成通知 webhook（可选）
set -euo pipefail

# ========== 配置 ==========
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
BACKUP_MODE="${BACKUP_MODE:-sequential}"
NOTIFY_WEBHOOK="${NOTIFY_WEBHOOK:-}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${BACKUP_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/backup_all_${TIMESTAMP}.log"

# 备份结果状态
declare -A BACKUP_RESULTS=(
  ["postgres"]="pending"
  ["redis"]="pending"
  ["clickhouse"]="pending"
)

# ========== 工具函数 ==========
log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "${msg}" | tee -a "${LOG_FILE}"
}

# 发送通知
send_notification() {
  local status="$1"
  local message="$2"
  if [[ -n "${NOTIFY_WEBHOOK}" ]]; then
    local payload
    payload=$(cat <<EOF
{
  "status": "${status}",
  "message": "${message}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_dir": "${BACKUP_DIR}"
}
EOF
)
    curl -s -X POST "${NOTIFY_WEBHOOK}" \
      -H "Content-Type: application/json" \
      -d "${payload}" >/dev/null 2>&1 || true
  fi
}

# 执行单个备份
run_backup() {
  local service="$1"
  local script="${SCRIPT_DIR}/backup_${service}.sh"
  local service_log="${LOG_DIR}/backup_${service}_${TIMESTAMP}.log"

  if [[ ! -x "${script}" && ! -f "${script}" ]]; then
    log "错误：备份脚本不存在: ${script}"
    BACKUP_RESULTS["${service}"]="failed"
    return 1
  fi

  log ">>> 开始备份 ${service}..."
  local start_time
  start_time=$(date +%s)

  if bash "${script}" > "${service_log}" 2>&1; then
    local end_time duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    log "<<< ${service} 备份成功（耗时 ${duration}s）"
    BACKUP_RESULTS["${service}"]="success"
  else
    local end_time duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    log "<<< ${service} 备份失败（耗时 ${duration}s），详见 ${service_log}"
    BACKUP_RESULTS["${service}"]="failed"
    return 1
  fi
}

# ========== 主流程 ==========
main() {
  log "========================================"
  log "RPKI 平台统一备份开始"
  log "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  log "备份目录: ${BACKUP_DIR}"
  log "备份模式: ${BACKUP_MODE}"
  log "========================================"

  local overall_status="success"
  local failed_services=()

  if [[ "${BACKUP_MODE}" == "parallel" ]]; then
    # 并行备份（注意：并行备份对 IO 压力较大，建议在低峰期执行）
    log "启动并行备份..."
    local pids=()
    for service in postgres redis clickhouse; do
      run_backup "${service}" &
      pids+=($!)
    done

    # 等待所有备份完成
    local exit_codes=()
    for pid in "${pids[@]}"; do
      wait "${pid}" && exit_codes+=("0") || exit_codes+=("1")
    done

    for i in "${!exit_codes[@]}"; do
      if [[ "${exit_codes[$i]}" != "0" ]]; then
        overall_status="failed"
      fi
    done
  else
    # 顺序备份（默认，更安全）
    for service in postgres redis clickhouse; do
      if ! run_backup "${service}"; then
        overall_status="failed"
        failed_services+=("${service}")
      fi
    done
  fi

  # 汇总结果
  log "========================================"
  log "备份结果汇总:"
  for service in postgres redis clickhouse; do
    log "  ${service}: ${BACKUP_RESULTS[${service}]}"
  done

  if [[ "${overall_status}" == "success" ]]; then
    log "所有备份均成功完成"
    send_notification "success" "RPKI 平台备份全部成功"
  else
    log "部分备份失败: ${failed_services[*]:-unknown}"
    send_notification "failed" "RPKI 平台部分备份失败: ${failed_services[*]:-unknown}"
  fi

  log "日志文件: ${LOG_FILE}"
  log "========================================"

  if [[ "${overall_status}" != "success" ]]; then
    exit 1
  fi
}

main "$@"
