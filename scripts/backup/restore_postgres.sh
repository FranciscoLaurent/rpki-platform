#!/usr/bin/env bash
# PostgreSQL 恢复脚本
# 功能：从全量备份或增量备份恢复 PostgreSQL 数据库
# 用法：./restore_postgres.sh <备份文件路径>
# 依赖：pg_restore, psql, gunzip
# 环境变量：
#   DB_HOST          - PostgreSQL 主机（默认 postgres）
#   DB_PORT          - PostgreSQL 端口（默认 5432）
#   DB_USER          - PostgreSQL 用户（默认 rpki）
#   DB_NAME          - PostgreSQL 数据库名（默认 rpki_platform）
#   PGPASSWORD       - PostgreSQL 密码（必填）
#   DROP_EXISTING    - 是否先删除现有数据库（默认 false）
set -euo pipefail

# ========== 参数校验 ==========
if [[ $# -lt 1 ]]; then
  echo "用法: $0 <备份文件路径>"
  echo "示例: $0 /data/backups/postgres/full/postgres_full_20240101_120000.sql.gz"
  exit 1
fi

BACKUP_FILE="$1"
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-rpki}"
DB_NAME="${DB_NAME:-rpki_platform}"
DROP_EXISTING="${DROP_EXISTING:-false}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：请通过环境变量 PGPASSWORD 设置数据库密码" >&2
  exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "错误：备份文件不存在: ${BACKUP_FILE}" >&2
  exit 1
fi

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 校验文件完整性
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
  else
    log "警告：未找到校验和文件，跳过校验"
  fi
}

# ========== 恢复主流程 ==========
main() {
  log "=== PostgreSQL 恢复开始 ==="
  log "备份文件: ${BACKUP_FILE}"
  log "目标主机: ${DB_HOST}:${DB_PORT}"
  log "目标数据库: ${DB_NAME}"

  verify_checksum

  # 可选：删除现有数据库
  if [[ "${DROP_EXISTING}" == "true" ]]; then
    log "警告：即将删除并重建数据库 ${DB_NAME}"
    read -r -p "确认继续？(yes/no): " confirm
    if [[ "${confirm}" != "yes" ]]; then
      log "已取消"
      exit 0
    fi
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres \
      -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres \
      -c "CREATE DATABASE \"${DB_NAME}\";"
  fi

  # 根据文件类型选择恢复方式
  case "${BACKUP_FILE}" in
    *.sql.gz)
      log "从 SQL 文本备份恢复..."
      gunzip -c "${BACKUP_FILE}" | psql \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --quiet --set ON_ERROR_STOP=on
      ;;
    *.dump.gz|*.backup.gz)
      log "从自定义格式备份恢复..."
      local tmp_file="/tmp/restore_$(date +%s).dump"
      gunzip -c "${BACKUP_FILE}" > "${tmp_file}"
      pg_restore \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --no-owner --no-privileges --clean --if-exists \
        --jobs=4 \
        "${tmp_file}" || true
      rm -f "${tmp_file}"
      ;;
    *.tar.gz)
      log "从 WAL 归档增量备份恢复..."
      log "警告：增量备份恢复需要配合基础全量备份与 PITR 配置"
      log "请将 WAL 文件还原到归档目录后使用 pg_basebackup + recovery 进行 PITR 恢复"
      local restore_dir="${WAL_RESTORE_DIR:-/var/lib/postgresql/wal_restore}"
      mkdir -p "${restore_dir}"
      tar -xzf "${BACKUP_FILE}" -C "${restore_dir}"
      log "WAL 文件已解压到: ${restore_dir}"
      ;;
    *)
      log "错误：不支持的备份文件格式: ${BACKUP_FILE}" >&2
      exit 1
      ;;
  esac

  log "=== PostgreSQL 恢复完成 ==="
  log "建议：执行数据库一致性检查与统计信息更新"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -c "ANALYZE;" >/dev/null || true
}

main "$@"
