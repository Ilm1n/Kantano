#!/usr/bin/env bash

set -Eeuo pipefail

readonly RESTIC_IMAGE="${RESTIC_IMAGE:-restic/restic:0.19.1}"
readonly RESTIC_HOST="kantano-prod"
readonly RESTIC_TAG="kantano-db"
readonly RESTIC_FILENAME="kantano.dump"
readonly LOCK_FILE="/tmp/kantano-db-backup.lock"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly APP_DIR
readonly COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
readonly BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-${APP_DIR}/.env.backup}"

backup_tmp_dir=""
pingzen_url=""

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

ping_pingzen() {
    local suffix="$1"

    if [[ -z "${pingzen_url}" ]]; then
        return
    fi

    if ! curl --fail --silent --show-error --retry 3 --max-time 15 \
        "${pingzen_url}${suffix}" >/dev/null; then
        log "PingZen signal failed; backup result is still preserved locally."
    fi
}

cleanup() {
    local exit_status=$?
    trap - EXIT

    if [[ -n "${backup_tmp_dir}" && -d "${backup_tmp_dir}" ]]; then
        rm -rf -- "${backup_tmp_dir}"
    fi

    if [[ ${exit_status} -eq 0 ]]; then
        ping_pingzen "/success"
        log "Database backup completed successfully."
    else
        ping_pingzen "/fail"
        log "Database backup failed with exit status ${exit_status}."
    fi

    exit "${exit_status}"
}

require_environment() {
    local variable_name
    local variable_value
    local required_variables=(
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
        AWS_DEFAULT_REGION
        RESTIC_REPOSITORY
        RESTIC_PASSWORD
        BACKUP_PINGZEN_URL
    )

    for variable_name in "${required_variables[@]}"; do
        variable_value="$(read_backup_environment_value "${variable_name}")"
        if [[ -z "${variable_value}" ]]; then
            log "Required backup setting ${variable_name} is missing."
            exit 1
        fi
    done
}

read_backup_environment_value() {
    local variable_name="$1"
    local matching_line

    matching_line="$(grep -E "^${variable_name}=" "${BACKUP_ENV_FILE}" | tail -n 1 || true)"
    printf '%s' "${matching_line#*=}"
}

restic() {
    docker run --rm --env-file "${BACKUP_ENV_FILE}" -i "${RESTIC_IMAGE}" "$@"
}

main() {
    if [[ ! -r "${BACKUP_ENV_FILE}" ]]; then
        log "Backup environment file is missing or unreadable."
        exit 1
    fi

    pingzen_url="$(read_backup_environment_value BACKUP_PINGZEN_URL)"
    require_environment

    exec 9>"${LOCK_FILE}"
    if ! flock -n 9; then
        log "Another database backup is already running; skipping this invocation."
        exit 0
    fi

    trap cleanup EXIT
    ping_pingzen "/start"

    cd "${APP_DIR}"
    docker compose -f "${COMPOSE_FILE}" exec -T db pg_isready -U lighttask_user -d lighttask

    backup_tmp_dir="$(mktemp -d /tmp/kantano-db-backup.XXXXXX)"
    local dump_file="${backup_tmp_dir}/${RESTIC_FILENAME}"

    log "Creating PostgreSQL dump."
    docker compose -f "${COMPOSE_FILE}" exec -T db sh -ec \
        'exec pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --compress=0' \
        >"${dump_file}"

    test -s "${dump_file}"
    docker run --rm \
        --mount "type=bind,source=${backup_tmp_dir},target=/backup,readonly" \
        postgres:15.6-alpine3.19 pg_restore --list "/backup/${RESTIC_FILENAME}" >/dev/null

    log "Uploading encrypted Restic snapshot."
    restic cat config >/dev/null
    restic backup --stdin --stdin-filename "${RESTIC_FILENAME}" \
        --host "${RESTIC_HOST}" --tag "${RESTIC_TAG}" <"${dump_file}"
    restic snapshots --host "${RESTIC_HOST}" --tag "${RESTIC_TAG}" --latest 1 >/dev/null

    log "Applying retention policy."
    restic forget --host "${RESTIC_HOST}" --tag "${RESTIC_TAG}" --group-by host,tags \
        --keep-daily 3 --keep-last 1 --prune
    restic check
}

main "$@"
