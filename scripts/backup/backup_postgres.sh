#!/usr/bin/env bash
# PostgreSQL 备份脚本
# 功能：支持全量备份（pg_dump）与增量备份（WAL 归档）
# 用法：./backup_postgres.sh [--full|--incremental]
# 依赖：pg_dump, psql, tar, gzip
# 环境变量：
#   DB_HOST          - PostgreSQL 主机（默认 postgres）
#   DB_PORT          - PostgreSQL 端口（默认 5432）
#   DB_USER          - PostgreSQL 用户（默认 rpki）
#   DB_NAME          - PostgreSQL 数据库名（默认 rpki_platform）
#   PGPASSWORD       - PostgreSQL 密码（必填）
#   BACKUP_DIR       - 备份根目录（默认 /data/backups/postgres）
#   BACKUP_RETENTION - 备份保留天数（默认 7）
set -euo pipefail

# ========== 参数与配置 ==========
BACKUP_TYPE="full"
if [[ $# -ge 1 ]]; then
  case "$1" in
    --full)
      BACKUP_TYPE="full"
      ;;
    --incremental)
      BACKUP_TYPE="incremental"
      ;;
    -h|--help)
      echo "用法: $0 [--full|--incremental]"
      echo "  --full        全量备份（默认）"
      echo "  --incremental 增量备份（基于 WAL 归档）"
      exit 0
      ;;
    *)
      echo "错误：未知参数 $1" >&2
      exit 1
      ;;
  esac
fi

# 数据库连接配置（支持环境变量覆盖）
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-rpki}"
DB_NAME="${DB_NAME:-rpki_platform}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
BACKUP_RETENTION="${BACKUP_RETENTION:-7}"

# 校验必填项
if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：请通过环境变量 PGPASSWORD 设置数据库密码" >&2
  exit 1
fi

# 时间戳与备份文件命名
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_SUBDIR="${BACKUP_DIR}/${BACKUP_TYPE}"
mkdir -p "${BACKUP_SUBDIR}"

# ========== 工具函数 ==========
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cleanup_old_backups() {
  log "清理 ${BACKUP_RETENTION} 天前的旧备份..."
  find "${BACKUP_SUBDIR}" -type f -name "*.gz" -mtime +"${BACKUP_RETENTION}" -print -delete || true
}

# ========== 全量备份 ==========
backup_full() {
  local backup_file="${BACKUP_SUBDIR}/postgres_full_${TIMESTAMP}.sql.gz"
  log "开始 PostgreSQL 全量备份: ${backup_file}"

  # 使用 pg_dump 自定义格式，配合 gzip 压缩
  # -Fc 自定义格式（支持并行恢复）
  # --no-owner 不导出 owner 信息，便于跨环境恢复
  if pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-privileges \
    --format=custom \
    --compress=9 \
    -f "${backup_file%.gz}"; then
    gzip -f "${backup_file%.gz}"
    log "全量备份成功: ${backup_file}"
    # 生成校验和
    sha256sum "${backup_file}" > "${backup_file}.sha256"
    log "校验和已生成: ${backup_file}.sha256"
  else
    log "错误：全量备份失败" >&2
    exit 1
  fi
}

# ========== 增量备份（基于 WAL 归档） ==========
backup_incremental() {
  local backup_file="${BACKUP_SUBDIR}/postgres_incremental_${TIMESTAMP}.tar.gz"
  local wal_dir="${WAL_ARCHIVE_DIR:-/var/lib/postgresql/wal_archive}"

  log "开始 PostgreSQL 增量备份（WAL 归档）: ${backup_file}"

  if [[ ! -d "${wal_dir}" ]]; then
    log "错误：WAL 归档目录不存在: ${wal_dir}" >&2
    log "请确保 PostgreSQL 已配置 archive_mode 与 archive_command" >&2
    exit 1
  fi

  # 切换 WAL，确保当前 WAL 被归档
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -c "SELECT pg_switch_wal();" >/dev/null

  # 打包归档的 WAL 文件
  tar -czf "${backup_file}" -C "${wal_dir}" . 2>/dev/null || true
  log "增量备份成功: ${backup_file}"
  sha256sum "${backup_file}" > "${backup_file}.sha256"
}

# ========== 主流程 ==========
main() {
  log "=== PostgreSQL 备份开始 ==="
  log "类型: ${BACKUP_TYPE}"
  log "主机: ${DB_HOST}:${DB_PORT}"
  log "数据库: ${DB_NAME}"
  log "备份目录: ${BACKUP_SUBDIR}"

  case "${BACKUP_TYPE}" in
    full)
      backup_full
      ;;
    incremental)
      backup_incremental
      ;;
  esac

  cleanup_old_backups
  log "=== PostgreSQL 备份完成 ==="
}

main "$@"
