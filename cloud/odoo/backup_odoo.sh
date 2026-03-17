#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$HOME/ai-employee/backups/odoo"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d_%H%M%S)
sudo docker exec odoo-db pg_dump -U odoo odoo | gzip > "$BACKUP_DIR/odoo_${DATE}.sql.gz"
ls -t "$BACKUP_DIR"/odoo_*.sql.gz | tail -n +8 | xargs -r rm
echo "[$(date -u)] Odoo backup complete: odoo_${DATE}.sql.gz"
