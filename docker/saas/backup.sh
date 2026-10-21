#!/bin/sh
# Once a day (the first at start-up): the whole database (pg_dump, compressed) and the companies' files (logos, images), kept
# BACKUP_KEEP_DAYS days. Restore: see INSTALLATION_SAAS.md.
set -e
mkdir -p /backups
while true; do
  stamp=$(date +%Y-%m-%d_%H%M)
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
    -f "/backups/rmsoft_db_$stamp.dump" && echo "base de dados: rmsoft_db_$stamp.dump"
  tar -czf "/backups/rmsoft_uploads_$stamp.tar.gz" -C /uploads . && echo "ficheiros: rmsoft_uploads_$stamp.tar.gz"
  find /backups -type f -mtime +"${BACKUP_KEEP_DAYS:-14}" -delete
  sleep 86400
done
