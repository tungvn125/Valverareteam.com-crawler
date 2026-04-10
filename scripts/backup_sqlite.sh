#!/bin/sh
# Daily SQLite database backup script for VVR-Scraper
# Runs on Alpine sidecar container inside docker-compose

set -e

SOURCE_DIR="/data"
BACKUP_DIR="/backups"
DB_FILE="vvr_library.db"
# Wait, let's backup ALL .db files in /data
# Because jobs.db and library.db might be separate or merged.

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting backup process..."

for DB_PATH in "$SOURCE_DIR"/*.db; do
    if [ -f "$DB_PATH" ]; then
        BASENAME=$(basename "$DB_PATH")
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        TARGET_FILE="$BACKUP_DIR/${BASENAME}_${TIMESTAMP}.db"
        
        echo "[$(date -Iseconds)] Backing up $BASENAME to $TARGET_FILE"
        
        # Use sqlite3 online backup to avoid locking the active app
        sqlite3 "$DB_PATH" ".backup '$TARGET_FILE'"
        
        echo "[$(date -Iseconds)] $BASENAME backup completed."
    fi
done

# Cleanup backups older than 7 days
echo "[$(date -Iseconds)] Cleaning up backups older than 7 days..."
find "$BACKUP_DIR" -name "*.db" -type f -mtime +7 -exec rm -f {} \;
echo "[$(date -Iseconds)] Cleanup complete."
