#!/usr/bin/env bash
# 统一恢复入口脚本
# 功能：从指定备份目录恢复 PostgreSQL、Redis、ClickHouse 数据
# 用法：./restore_all.sh <备份时间戳或目录>
# 示例：
#   ./restore_all.sh 20240101_120000
#   ./restore_all.sh /data/backups
# 依赖：restore_postgres.sh, restore_redis.sh, restore_clickhouse.sh
# 环境变量：继承各子脚本的环境变量
#   BACKUP_DIR       - 统一备份根目录（默认 /data/backups）
#   DROP_EXISTING    - 是否先删除现有数据（默认 false）
#   RESTORE_SERVICES - 要恢复的服务列表（默认 "postgres redis clickhouse"）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <备份时间戳或目录>"
  echo "示例:"
  echo "  $0 20240101_120000              # 按时间戳恢复"
  echo "  $0 /data/backups                # 按目录恢复"
  exit 1
fi

BACKUP_TARGET="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DROP_EXISTING="${DROP_EXISTING:-false}"
RESTORE_SERVICES="${RESTORE_SERVICES:-postgres redis clickhouse}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${BACKUP_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/restore_all_${TIMESTAMP}.log"

declare -A RESTORE_RESULTS=()

# ========== 工具函数 ==========
log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "${msg}" | tee -a "${LOG_FILE}"
}

# 查找指定服务的最新备份文件
find_backup_file() {
  local service="$1"
  local target="${BACKUP_TARGET}"

  # 如果是时间戳，则在备份目录中查找匹配文件
  if [[ ! -d "${target}" ]]; then
    local pattern
    case "${service}" in
      postgres)
        pattern="${BACKUP_DIR}/postgres/full/postgres_full_${target}.sql.gz"
        ;;
      redis)
        pattern="${BACKUP_DIR}/redis/full/redis_${target}.tar.gz"
        ;;
      clickhouse)
        pattern="${BACKUP_DIR}/clickhouse/full/clickhouse_${target}.tar.gz"
        ;;
    esac
    if [[ -f "${pattern}" ]]; then
      echo "${pattern}"
      return 0
    fi
  else
    # 如果是目录，查找目录中最新的备份文件
    local search_dir
    case "${service}" in
      postgres)
        search_dir="${target}/postgres/full"
        ;;
      redis)
        search_dir="${target}/redis/full"
        ;;
      clickhouse)
        search_dir="${target}/clickhouse/full"
        ;;
    esac
    if [[ -d "${search_dir}" ]]; then
      local latest
      latest="$(ls -t "${search_dir}"/*.{sql.gz,tar.gz} 2>/dev/null | head -n1 || true)"
      if [[ -n "${latest}" ]]; then
        echo "${latest}"
        return 0
      fi
    fi
  fi
  return 1
}

# 执行单个恢复
run_restore() {
  local service="$1"
  local script="${SCRIPT_DIR}/restore_${service}.sh"

  if [[ ! -f "${script}" ]]; then
    log "错误：恢复脚本不存在: ${script}"
    RESTORE_RESULTS["${service}"]="failed:script-missing"
    return 1
  fi

  local backup_file
  if ! backup_file="$(find_backup_file "${service}")"; then
    log "错误：未找到 ${service} 的备份文件"
    RESTORE_RESULTS["${service}"]="failed:no-backup"
    return 1
  fi

  log ">>> 开始恢复 ${service}，备份文件: ${backup_file}"
  local service_log="${LOG_DIR}/restore_${service}_${TIMESTAMP}.log"

  if bash "${script}" "${backup_file}" > "${service_log}" 2>&1; then
    log "<<< ${service} 恢复成功"
    RESTORE_RESULTS["${service}"]="success"
  else
    log "<<< ${service} 恢复失败，详见 ${service_log}"
    RESTORE_RESULTS["${service}"]="failed"
    return 1
  fi
}

# ========== 主流程 ==========
main() {
  log "========================================"
  log "RPKI 平台统一恢复开始"
  log "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  log "备份目标: ${BACKUP_TARGET}"
  log "DROP_EXISTING: ${DROP_EXISTING}"
  log "恢复服务: ${RESTORE_SERVICES}"
  log "========================================"

  # 安全确认
  log "警告：恢复操作将覆盖现有数据！"
  read -r -p "确认继续恢复？请输入 'RESTORE' 确认: " confirm
  if [[ "${confirm}" != "RESTORE" ]]; then
    log "已取消恢复"
    exit 0
  fi

  local overall_status="success"
  local failed_services=()

  # 顺序恢复（恢复操作不建议并行）
  for service in ${RESTORE_SERVICES}; do
    if ! run_restore "${service}"; then
      overall_status="failed"
      failed_services+=("${service}")
    fi
  done

  # 汇总结果
  log "========================================"
  log "恢复结果汇总:"
  for service in ${RESTORE_SERVICES}; do
    log "  ${service}: ${RESTORE_RESULTS[${service}]:-unknown}"
  done

  if [[ "${overall_status}" == "success" ]]; then
    log "所有恢复均成功完成"
    log "建议："
    log "  1. 验证各服务数据完整性"
    log "  2. 重启应用服务以刷新缓存与连接"
    log "  3. 检查应用日志确认无异常"
  else
    log "部分恢复失败: ${failed_services[*]:-unknown}"
    log "请检查日志文件并手动处理"
  fi

  log "日志文件: ${LOG_FILE}"
  log "========================================"

  if [[ "${overall_status}" != "success" ]]; then
    exit 1
  fi
}

main "$@"
