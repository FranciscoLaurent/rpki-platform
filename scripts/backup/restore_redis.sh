#!/usr/bin/env bash
# Redis 恢复脚本
# 功能：从 RDB/AOF 备份恢复 Redis 数据
# 用法：./restore_redis.sh <备份文件路径>
# 依赖：redis-cli, tar, gunzip
# 环境变量：
#   REDIS_HOST     - Redis 主机（默认 redis）
#   REDIS_PORT     - Redis 端口（默认 6379）
#   REDIS_PASSWORD - Redis 密码（可选）
#   REDIS_DB       - 目标数据库编号（默认 0）
#   FLUSH_BEFORE   - 恢复前是否清空目标 DB（默认 false）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <备份文件路径>"
  echo "示例: $0 /data/backups/redis/full/redis_20240101_120000.tar.gz"
  exit 1
fi

BACKUP_FILE="$1"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_DB="${REDIS_DB:-0}"
FLUSH_BEFORE="${FLUSH_BEFORE:-false}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "错误：备份文件不存在: ${BACKUP_FILE}" >&2
  exit 1
fi

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

redis_cli_args() {
  local args=(-h "${REDIS_HOST}" -p "${REDIS_PORT}")
  if [[ -n "${REDIS_PASSWORD}" ]]; then
    args+=(-a "${REDIS_PASSWORD}")
  fi
  printf '%s\n' "${args[@]}"
}

verify_checksum() {
  local checksum_file="${BACKUP_FILE}.sha256"
  if [[ -f "${checksum_file}" ]]; then
    log "校验备份文件完整性..."
    if sha256sum -c "${checksum_file}" --quiet; then
      log "校验通过"
    else
      log "错误：校验失败，备份文件可能已损坏" >&2
      exit 1
    fi
  fi
}

# ========== 主流程 ==========
main() {
  log "=== Redis 恢复开始 ==="
  log "备份文件: ${BACKUP_FILE}"
  log "目标主机: ${REDIS_HOST}:${REDIS_PORT}"

  verify_checksum

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  # 解压备份
  tar -xzf "${BACKUP_FILE}" -C "${tmp_dir}"
  log "备份已解压到: ${tmp_dir}"

  local cli_args
  cli_args="$(redis_cli_args)"

  # 测试连接
  if ! redis-cli ${cli_args} ping >/dev/null 2>&1; then
    log "错误：无法连接 Redis" >&2
    exit 1
  fi

  # 可选：恢复前清空目标 DB
  if [[ "${FLUSH_BEFORE}" == "true" ]]; then
    log "警告：即将清空 DB ${REDIS_DB}"
    read -r -p "确认继续？(yes/no): " confirm
    if [[ "${confirm}" != "yes" ]]; then
      log "已取消"
      exit 0
    fi
    redis-cli ${cli_args} -n "${REDIS_DB}" FLUSHDB
    log "DB ${REDIS_DB} 已清空"
  fi

  # 优先使用逻辑备份恢复（JSONL 格式）
  local jsonl_file="${tmp_dir}/db_${REDIS_DB}_dump.jsonl"
  if [[ -f "${jsonl_file}" ]]; then
    log "从逻辑备份恢复 DB ${REDIS_DB}..."
    local count=0
    while IFS= read -r line; do
      local key type value
      key="$(echo "${line}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])' 2>/dev/null || true)"
      type="$(echo "${line}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["type"])' 2>/dev/null || true)"
      value="$(echo "${line}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["value"])' 2>/dev/null || true)"

      if [[ -z "${key}" || -z "${value}" ]]; then
        continue
      fi

      case "${type}" in
        string)
          echo "${value}" | base64 -d | redis-cli ${cli_args} -n "${REDIS_DB}" -x SET "${key}"
          ;;
        *)
          # 使用 RESTORE 恢复其他类型
          echo "${value}" | base64 -d | redis-cli ${cli_args} -n "${REDIS_DB}" -x RESTORE "${key}" 0 REPLACE
          ;;
      esac
      count=$((count + 1))
    done < "${jsonl_file}"
    log "逻辑恢复完成，共恢复 ${count} 个键"
  else
    log "未找到逻辑备份文件，将提示手动恢复 RDB/AOF"
    log "RDB 恢复方式："
    log "  1. 停止 Redis 服务"
    log "  2. 替换 ${tmp_dir}/dump.rdb 到 Redis 数据目录"
    log "  3. 启动 Redis 服务"
    if [[ -f "${tmp_dir}/appendonly.aof" ]]; then
      log "AOF 恢复方式："
      log "  1. 停止 Redis 服务"
      log "  2. 替换 ${tmp_dir}/appendonly.aof 到 Redis 数据目录"
      log "  3. 启动 Redis 服务"
    fi
  fi

  log "=== Redis 恢复完成 ==="
}

main "$@"
