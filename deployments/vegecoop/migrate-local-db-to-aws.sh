#!/usr/bin/env bash
#
# Overwrite the AWS/EC2 Postgres database with a dump of your LOCAL Postgres database.
#
# This is destructive on the AWS side: every table in the remote `plane` database is
# dropped and recreated from your local dump. A safety backup of the CURRENT remote
# database is always taken first (in addition to the automatic per-deploy backups),
# so you can roll back — see "ROLLBACK" printed at the end of a successful run.
#
# Usage:
#   EC2_KEY=/path/to/key.pem ./deployments/vegecoop/migrate-local-db-to-aws.sh
#
# Optional overrides (defaults shown):
#   EC2_HOST=13.230.86.17
#   EC2_USER=ec2-user
#   REMOTE_APP_DIR=/home/ec2-user/plane
#   REMOTE_BACKUP_DIR=/home/ec2-user/backups
#   LOCAL_COMPOSE_FILE=docker-compose-local.yml
#   POSTGRES_USER=plane
#   POSTGRES_DB=plane

set -euo pipefail

EC2_HOST="${EC2_HOST:-13.230.86.17}"
EC2_USER="${EC2_USER:-ec2-user}"
EC2_KEY="${EC2_KEY:-}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/home/ec2-user/plane}"
REMOTE_BACKUP_DIR="${REMOTE_BACKUP_DIR:-/home/ec2-user/backups}"
LOCAL_COMPOSE_FILE="${LOCAL_COMPOSE_FILE:-docker-compose-local.yml}"
POSTGRES_USER="${POSTGRES_USER:-plane}"
POSTGRES_DB="${POSTGRES_DB:-plane}"

if [ -z "$EC2_KEY" ]; then
  echo "Error: set EC2_KEY to the path of the .pem file for $EC2_USER@$EC2_HOST" >&2
  exit 1
fi
if [ ! -f "$EC2_KEY" ]; then
  echo "Error: EC2_KEY '$EC2_KEY' does not exist" >&2
  exit 1
fi

SSH="ssh -i $EC2_KEY -o StrictHostKeyChecking=accept-new $EC2_USER@$EC2_HOST"
SCP="scp -i $EC2_KEY -o StrictHostKeyChecking=accept-new"
TS="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "== Checking local DB container =="
LOCAL_DB_CID="$(docker compose -f "$LOCAL_COMPOSE_FILE" ps -q plane-db)"
if [ -z "$LOCAL_DB_CID" ]; then
  echo "Error: local plane-db container is not running (docker compose -f $LOCAL_COMPOSE_FILE up -d plane-db)" >&2
  exit 1
fi

echo "== Checking SSH connectivity to $EC2_USER@$EC2_HOST =="
$SSH "echo ok" >/dev/null

cat <<EOF

##############################################################################
  DANGER: this will PERMANENTLY OVERWRITE the AWS database at $EC2_HOST
  with your local database ($POSTGRES_DB on this machine).

  A backup of the CURRENT remote database will be taken and downloaded to
  $WORKDIR before anything is touched, but once the restore runs, whatever
  is live on AWS right now is replaced.
##############################################################################

Type OVERWRITE to continue:
EOF
read -r CONFIRM
if [ "$CONFIRM" != "OVERWRITE" ]; then
  echo "Aborted, nothing was touched."
  exit 1
fi

echo "== Backing up CURRENT remote database (safety net) =="
$SSH "docker exec plane-db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/pre-migration.pgdump'"
$SSH "docker cp plane-db:/tmp/pre-migration.pgdump $REMOTE_BACKUP_DIR/pre-migration-$TS.pgdump && docker exec plane-db rm /tmp/pre-migration.pgdump"
echo "   Remote pre-overwrite backup saved to $EC2_USER@$EC2_HOST:$REMOTE_BACKUP_DIR/pre-migration-$TS.pgdump"

echo "== Dumping local database =="
docker exec "$LOCAL_DB_CID" sh -c "pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/local-migration.pgdump"
docker cp "$LOCAL_DB_CID:/tmp/local-migration.pgdump" "$WORKDIR/local-migration-$TS.pgdump"
docker exec "$LOCAL_DB_CID" rm /tmp/local-migration.pgdump

echo "== Uploading local dump to EC2 =="
$SCP "$WORKDIR/local-migration-$TS.pgdump" "$EC2_USER@$EC2_HOST:$REMOTE_BACKUP_DIR/local-migration-$TS.pgdump"

echo "== Stopping app containers that write to the DB =="
$SSH "cd $REMOTE_APP_DIR && docker compose -f docker-compose.yml stop api worker live migrator"

echo "== Restoring local dump into the remote database =="
$SSH "docker cp $REMOTE_BACKUP_DIR/local-migration-$TS.pgdump plane-db:/tmp/restore.pgdump"
$SSH "docker exec plane-db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/restore.pgdump'"
$SSH "docker exec plane-db rm /tmp/restore.pgdump"

echo "== Restarting all services (also re-runs pending migrations) =="
$SSH "cd $REMOTE_APP_DIR && docker compose -f docker-compose.yml up -d"

echo "== Waiting for services to settle =="
sleep 20

echo "== Health check =="
ok=0
for i in 1 2 3 4 5 6; do
  code="$($SSH "curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost/api/instances/")"
  if [ "$code" = "200" ]; then
    echo "Health check passed (HTTP $code)"
    ok=1
    break
  fi
  echo "Attempt $i: got HTTP $code, retrying in 10s..."
  sleep 10
done

if [ "$ok" != "1" ]; then
  echo
  echo "Health check FAILED after 6 attempts. The app may be broken." >&2
fi

cat <<EOF

== Done ==
Remote DB was overwritten with your local dump.

ROLLBACK (restore the pre-migration state):
  ssh -i $EC2_KEY $EC2_USER@$EC2_HOST
  cd $REMOTE_APP_DIR
  docker compose -f docker-compose.yml stop api worker live migrator
  docker cp $REMOTE_BACKUP_DIR/pre-migration-$TS.pgdump plane-db:/tmp/rollback.pgdump
  docker exec plane-db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/rollback.pgdump'
  docker exec plane-db rm /tmp/rollback.pgdump
  docker compose -f docker-compose.yml up -d
EOF
