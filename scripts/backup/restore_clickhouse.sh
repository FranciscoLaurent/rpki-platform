#!/usr/bin/env bash
# ClickHouse 恢复脚本
# 功能：从备份恢复 ClickHouse 数据库表结构与数据
# 用法：./restore_clickhouse.sh <备份文件路径>
# 依赖：clickhouse-client, tar, gunzip
# 环境变量：
#   CH_HOST       - ClickHouse 主机（默认 clickhouse）
#   CH_NATIVE_PORT- ClickHouse Native 端口（默认 9000）
#   CH_USER       - ClickHouse 用户（默认 default）
#   CH_PASSWORD   - ClickHouse 密码（可选）
#   CH_DB         - ClickHouse 数据库名（默认 rpki_platform）
#   DROP_EXISTING - 是否先删除现有数据库（默认 false）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <备份文件路径>"
  echo "示例: $0 /data/backups/clickhouse/full/clickhouse_20240101_120000.tar.gz"
  exit 1
fi

BACKUP_FILE="$1"
CH_HOST="${CH_HOST:-clickhouse}"
CH_NATIVE_PORT="${CH_NATIVE_PORT:-9000}"
CH_USER="${CH_USER:-default}"
CH_PASSWORD="${CH_PASSWORD:-}"
CH_DB="${CH_DB:-rpki_platform}"
DROP_EXISTING="${DROP_EXISTING:-false}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "错误：备份文件不存在: ${BACKUP_FILE}" >&2
  exit 1
fi

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

ch_client_args() {
  local args=(--host "${CH_HOST}" --port "${CH_NATIVE_PORT}" --user "${CH_USER}")
  if [[ -n "${CH_PASSWORD}" ]]; then
    args+=(--password "${CH_PASSWORD}")
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
  log "=== ClickHouse 恢复开始 ==="
  log "备份文件: ${BACKUP_FILE}"
  log "目标主机: ${CH_HOST}:${CH_NATIVE_PORT}"
  log "目标数据库: ${CH_DB}"

  verify_checksum

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  tar -xzf "${BACKUP_FILE}" -C "${tmp_dir}"
  log "备份已解压到: ${tmp_dir}"

  local cli_args
  cli_args="$(ch_client_args)"

  # 测试连接
  if ! clickhouse-client ${cli_args} --query "SELECT 1" >/dev/null 2>&1; then
    log "错误：无法连接 ClickHouse" >&2
    exit 1
  fi

  # 可选：删除现有数据库
  if [[ "${DROP_EXISTING}" == "true" ]]; then
    log "警告：即将删除并重建数据库 ${CH_DB}"
    read -r -p "确认继续？(yes/no): " confirm
    if [[ "${confirm}" != "yes" ]]; then
      log "已取消"
      exit 0
    fi
    clickhouse-client ${cli_args} --query "DROP DATABASE IF EXISTS ${CH_DB}"
  fi

  # 创建数据库
  if [[ -f "${tmp_dir}/database.sql" ]]; then
    log "创建数据库 ${CH_DB}..."
    clickhouse-client ${cli_args} --queries-file "${tmp_dir}/database.sql" 2>/dev/null || \
      clickhouse-client ${cli_args} --query "CREATE DATABASE IF NOT EXISTS ${CH_DB}"
  else
    clickhouse-client ${cli_args} --query "CREATE DATABASE IF NOT EXISTS ${CH_DB}"
  fi

  # 恢复表结构与数据
  local restored_tables=0
  for schema_file in "${tmp_dir}"/*_schema.sql; do
    [[ -e "${schema_file}" ]] || continue
    local table
    table="$(basename "${schema_file}" _schema.sql)"
    log "  恢复表: ${table}"

    # 创建表结构
    clickhouse-client ${cli_args} --queries-file "${schema_file}" 2>/dev/null || {
      log "    警告：表 ${table} 结构创建失败，可能已存在"
    }

    # 导入数据
    local data_file="${tmp_dir}/${table}_data.native"
    if [[ -f "${data_file}" && -s "${data_file}" ]]; then
      log "    导入数据..."
      cat "${data_file}" | clickhouse-client ${cli_args} \
        --query "INSERT INTO ${CH_DB}.${table} FORMAT Native" 2>/dev/null || \
        log "    警告：表 ${table} 数据导入失败"
    fi

    restored_tables=$((restored_tables + 1))
  done

  log "共恢复 ${restored_tables} 张表"

  # 显示恢复后的行数统计
  if [[ -f "${tmp_dir}/row_counts.txt" ]]; then
    log "原始行数统计:"
    cat "${tmp_dir}/row_counts.txt"
  fi

  log "=== ClickHouse 恢复完成 ==="
}

main "$@"
