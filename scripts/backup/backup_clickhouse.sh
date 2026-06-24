#!/usr/bin/env bash
# ClickHouse 备份脚本
# 功能：备份 ClickHouse 数据库表结构与数据
# 用法：./backup_clickhouse.sh
# 依赖：clickhouse-client, tar, gzip
# 环境变量：
#   CH_HOST       - ClickHouse 主机（默认 clickhouse）
#   CH_HTTP_PORT  - ClickHouse HTTP 端口（默认 8123）
#   CH_NATIVE_PORT- ClickHouse Native 端口（默认 9000）
#   CH_USER       - ClickHouse 用户（默认 default）
#   CH_PASSWORD   - ClickHouse 密码（可选）
#   CH_DB         - ClickHouse 数据库名（默认 rpki_platform）
#   BACKUP_DIR    - 备份根目录（默认 /data/backups/clickhouse）
#   BACKUP_RETENTION - 备份保留天数（默认 7）
set -euo pipefail

# ========== 配置 ==========
CH_HOST="${CH_HOST:-clickhouse}"
CH_HTTP_PORT="${CH_HTTP_PORT:-8123}"
CH_NATIVE_PORT="${CH_NATIVE_PORT:-9000}"
CH_USER="${CH_USER:-default}"
CH_PASSWORD="${CH_PASSWORD:-}"
CH_DB="${CH_DB:-rpki_platform}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups/clickhouse}"
BACKUP_RETENTION="${BACKUP_RETENTION:-7}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_SUBDIR="${BACKUP_DIR}/full"
mkdir -p "${BACKUP_SUBDIR}"

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 构造 clickhouse-client 公共参数
ch_client_args() {
  local args=(--host "${CH_HOST}" --port "${CH_NATIVE_PORT}" --user "${CH_USER}")
  if [[ -n "${CH_PASSWORD}" ]]; then
    args+=(--password "${CH_PASSWORD}")
  fi
  printf '%s\n' "${args[@]}"
}

cleanup_old_backups() {
  log "清理 ${BACKUP_RETENTION} 天前的旧备份..."
  find "${BACKUP_SUBDIR}" -type f -name "*.tar.gz" -mtime +"${BACKUP_RETENTION}" -print -delete || true
}

# ========== 主流程 ==========
main() {
  log "=== ClickHouse 备份开始 ==="
  log "主机: ${CH_HOST}:${CH_NATIVE_PORT}"
  log "数据库: ${CH_DB}"

  local backup_file="${BACKUP_SUBDIR}/clickhouse_${TIMESTAMP}.tar.gz"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  local cli_args
  cli_args="$(ch_client_args)"

  # 测试连接
  if ! clickhouse-client ${cli_args} --query "SELECT 1" >/dev/null 2>&1; then
    log "错误：无法连接 ClickHouse" >&2
    exit 1
  fi

  # 导出数据库结构
  log "导出数据库 ${CH_DB} 结构..."
  clickhouse-client ${cli_args} --query "SHOW CREATE DATABASE ${CH_DB}" \
    > "${tmp_dir}/database.sql" 2>/dev/null || echo "CREATE DATABASE IF NOT EXISTS ${CH_DB};" > "${tmp_dir}/database.sql"

  # 获取所有表
  log "获取表列表..."
  local tables
  tables="$(clickhouse-client ${cli_args} --query "SHOW TABLES FROM ${CH_DB}" 2>/dev/null || echo "")"

  if [[ -z "${tables}" ]]; then
    log "警告：数据库 ${CH_DB} 中无表"
  else
    # 导出每张表的结构与数据
    while IFS= read -r table; do
      [[ -z "${table}" ]] && continue
      log "  备份表: ${table}"

      # 表结构
      clickhouse-client ${cli_args} --query "SHOW CREATE TABLE ${CH_DB}.${table}" \
        > "${tmp_dir}/${table}_schema.sql" 2>/dev/null || true

      # 表数据（TSV 格式，便于恢复）
      # 对于大表可改用 Native 格式分块导出
      clickhouse-client ${cli_args} --query "SELECT * FROM ${CH_DB}.${table} FORMAT Native" \
        > "${tmp_dir}/${table}_data.native" 2>/dev/null || true

      # 记录行数
      local row_count
      row_count="$(clickhouse-client ${cli_args} --query "SELECT count() FROM ${CH_DB}.${table}" 2>/dev/null || echo 0)"
      echo "${table}: ${row_count}" >> "${tmp_dir}/row_counts.txt"
    done <<< "${tables}"
  fi

  # 打包备份
  tar -czf "${backup_file}" -C "${tmp_dir}" .
  sha256sum "${backup_file}" > "${backup_file}.sha256"
  log "备份成功: ${backup_file}"

  cleanup_old_backups
  log "=== ClickHouse 备份完成 ==="
}

main "$@"
