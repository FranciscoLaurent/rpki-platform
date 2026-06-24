#!/usr/bin/env bash
# Redis 备份脚本
# 功能：通过 RDB 快照与 AOF 文件备份 Redis 数据
# 用法：./backup_redis.sh
# 依赖：redis-cli, tar, gzip
# 环境变量：
#   REDIS_HOST     - Redis 主机（默认 redis）
#   REDIS_PORT     - Redis 端口（默认 6379）
#   REDIS_PASSWORD - Redis 密码（可选）
#   REDIS_DB       - Redis 数据库编号（默认 0，留空表示所有）
#   BACKUP_DIR     - 备份根目录（默认 /data/backups/redis）
#   BACKUP_RETENTION - 备份保留天数（默认 7）
set -euo pipefail

# ========== 配置 ==========
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_DB="${REDIS_DB:-0}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups/redis}"
BACKUP_RETENTION="${BACKUP_RETENTION:-7}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_SUBDIR="${BACKUP_DIR}/full"
mkdir -p "${BACKUP_SUBDIR}"

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 构造 redis-cli 公共参数
redis_cli_args() {
  local args=(-h "${REDIS_HOST}" -p "${REDIS_PORT}")
  if [[ -n "${REDIS_PASSWORD}" ]]; then
    args+=(-a "${REDIS_PASSWORD}")
  fi
  printf '%s\n' "${args[@]}"
}

cleanup_old_backups() {
  log "清理 ${BACKUP_RETENTION} 天前的旧备份..."
  find "${BACKUP_SUBDIR}" -type f -name "*.tar.gz" -mtime +"${BACKUP_RETENTION}" -print -delete || true
}

# ========== 主流程 ==========
main() {
  log "=== Redis 备份开始 ==="
  log "主机: ${REDIS_HOST}:${REDIS_PORT}"

  local backup_file="${BACKUP_SUBDIR}/redis_${TIMESTAMP}.tar.gz"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  # 测试连接
  local cli_args
  cli_args="$(redis_cli_args)"
  if ! redis-cli ${cli_args} ping >/dev/null 2>&1; then
    log "错误：无法连接 Redis" >&2
    exit 1
  fi

  # 触发 BGSAVE 生成 RDB 快照
  log "触发 BGSAVE 生成 RDB 快照..."
  redis-cli ${cli_args} BGSAVE >/dev/null

  # 等待 BGSAVE 完成
  log "等待 BGSAVE 完成..."
  local wait_count=0
  while [[ ${wait_count} -lt 60 ]]; do
    local last_save
    last_save="$(redis-cli ${cli_args} LASTSAVE)"
    sleep 2
    local current_save
    current_save="$(redis-cli ${cli_args} LASTSAVE)"
    if [[ "${last_save}" != "${current_save}" ]]; then
      log "BGSAVE 完成"
      break
    fi
    wait_count=$((wait_count + 1))
  done

  # 通过 CONFIG GET 获取 RDB 与 AOF 路径
  local rdb_path aof_path
  rdb_path="$(redis-cli ${cli_args} CONFIG GET dir | tail -n1)"
  local rdb_filename
  rdb_filename="$(redis-cli ${cli_args} CONFIG GET dbfilename | tail -n1)"
  rdb_path="${rdb_path}/${rdb_filename}"

  local aof_enabled
  aof_enabled="$(redis-cli ${cli_args} CONFIG GET appendonly | tail -n1)"

  # 复制 RDB 文件
  if [[ -f "${rdb_path}" ]]; then
    log "复制 RDB 文件: ${rdb_path}"
    cp "${rdb_path}" "${tmp_dir}/dump.rdb"
  else
    log "警告：RDB 文件不存在: ${rdb_path}"
  fi

  # 复制 AOF 文件（如启用）
  if [[ "${aof_enabled}" == "yes" ]]; then
    local aof_dir aof_filename
    aof_dir="$(redis-cli ${cli_args} CONFIG GET dir | tail -n1)"
    aof_filename="$(redis-cli ${cli_args} CONFIG GET appendfilename | tail -n1)"
    aof_path="${aof_dir}/${aof_filename}"
    if [[ -f "${aof_path}" ]]; then
      log "复制 AOF 文件: ${aof_path}"
      cp "${aof_path}" "${tmp_dir}/appendonly.aof"
    fi
  fi

  # 导出指定 DB 的键值（作为逻辑备份补充）
  if [[ -n "${REDIS_DB}" ]]; then
    log "导出 DB ${REDIS_DB} 的键值到 JSON..."
    redis-cli ${cli_args} -n "${REDIS_DB}" --scan | while read -r key; do
      local type value
      type="$(redis-cli ${cli_args} -n "${REDIS_DB}" TYPE "${key}")"
      case "${type}" in
        string)
          value="$(redis-cli ${cli_args} -n "${REDIS_DB}" GET "${key}" | base64 -w0)"
          ;;
        *)
          value="$(redis-cli ${cli_args} -n "${REDIS_DB}" DUMP "${key}" | base64 -w0)"
          ;;
      esac
      printf '{"key":"%s","type":"%s","value":"%s"}\n' "${key}" "${type}" "${value}"
    done > "${tmp_dir}/db_${REDIS_DB}_dump.jsonl" 2>/dev/null || true
  fi

  # 打包备份
  tar -czf "${backup_file}" -C "${tmp_dir}" .
  sha256sum "${backup_file}" > "${backup_file}.sha256"
  log "备份成功: ${backup_file}"

  cleanup_old_backups
  log "=== Redis 备份完成 ==="
}

main "$@"
