#!/usr/bin/env bash
set -euo pipefail
umask 027
APP_DIR=/opt/analytics-team
COMMIT=${ANALYTICS_REF:-main}
test "$(id -u)" -eq 0
if [ -e "$APP_DIR" ]; then
    echo "$APP_DIR уже существует. Используйте раздел обновления инструкции." >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git python3-venv python3-pip nginx curl postgresql
id analytics-team >/dev/null 2>&1 || useradd --system --home /var/lib/analytics-team --shell /usr/sbin/nologin analytics-team
install -d -o analytics-team -g analytics-team -m 0750 /var/lib/analytics-team
install -d -o root -g analytics-team -m 0750 /etc/analytics-team

DB_NAME=analytics
DB_USER=analytics_app
DB_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
systemctl enable --now postgresql
for attempt in $(seq 1 30); do
    if runuser -u postgres -- pg_isready --quiet; then
        break
    fi
    sleep 1
done
if runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    ROLE_ACTION=ALTER
else
    ROLE_ACTION=CREATE
fi
runuser -u postgres -- psql -v ON_ERROR_STOP=1 <<SQL
$ROLE_ACTION ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';
SQL
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    runuser -u postgres -- createdb -O "$DB_USER" "$DB_NAME"
fi
install -o root -g analytics-team -m 0640 /dev/null /etc/analytics-team/database.env
printf 'ANALYTICS_DATABASE_URL=postgresql://%s:%s@127.0.0.1:5432/%s\n' \
    "$DB_USER" "$DB_PASSWORD" "$DB_NAME" > /etc/analytics-team/database.env

git clone https://github.com/ArtemMitrofanov/analytics_team.git "$APP_DIR"
cd "$APP_DIR"
git checkout --detach "$COMMIT"
set -a
. /etc/analytics-team/database.env
set +a
psql "$ANALYTICS_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$APP_DIR/schema.sql"
python3 -m venv .venv
.venv/bin/python - <<'PY'
import pathlib, tomllib
config = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
pathlib.Path('/etc/analytics-team/requirements.txt').write_text('\n'.join(config['project']['dependencies']) + '\n')
PY
if [ -f "$APP_DIR/requirements.lock.txt" ]; then
    .venv/bin/pip install --no-cache-dir -r "$APP_DIR/requirements.lock.txt"
else
    .venv/bin/pip install --no-cache-dir -r /etc/analytics-team/requirements.txt
fi
.venv/bin/pip freeze > /etc/analytics-team/requirements.lock.txt
.venv/bin/python - <<'PY'
import numpy, pandas, pyarrow
assert pyarrow.Table.from_pandas(pandas.DataFrame({'value': numpy.array([1.5])})).num_rows == 1
PY
if [ ! -e /etc/analytics-team/users.json ]; then
python3 - <<'PY'
import hashlib, json, os, pathlib, secrets
roles = {'admin': 'Администратор', 'guest': 'Гость', 'analyst': 'Аналитик', 'developer': 'Разработчик', 'tester': 'Тестировщик'}
users, lines = {}, ['Team Process Analytics — данные входа', 'В форме входа выберите отображаемое имя пользователя.', '']
for role, name in roles.items():
    password = secrets.token_urlsafe(24)
    users[role] = dict(password_hash=hashlib.sha256(password.encode()).hexdigest(), role=role, display_name=name)
    lines += [f'{name} ({role}): {password}']
pathlib.Path('/etc/analytics-team/users.json').write_text(json.dumps(users, ensure_ascii=False, indent=2) + '\n')
pathlib.Path('/root/analytics-team-credentials.txt').write_text('\n'.join(lines) + '\n')
os.chmod('/root/analytics-team-credentials.txt', 0o600)
PY
fi
chown root:analytics-team /etc/analytics-team/users.json
chmod 0640 /etc/analytics-team/users.json
chown -R root:analytics-team "$APP_DIR"
chmod -R g+rX,o-rwx "$APP_DIR"
cat > /etc/systemd/system/analytics-team.service <<'UNIT'
[Unit]
Description=Team Process Analytics (Streamlit)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=analytics-team
Group=analytics-team
WorkingDirectory=/opt/analytics-team
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=/etc/analytics-team/database.env
Environment=ANALYTICS_USERS_FILE=/etc/analytics-team/users.json
Environment=HOME=/var/lib/analytics-team
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
ExecStart=/opt/analytics-team/.venv/bin/streamlit run main.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false --server.fileWatcherType=none
Restart=always
RestartSec=5
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/analytics-team

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/nginx/sites-available/analytics-team <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 200m;
    server_tokens off;
    add_header X-Content-Type-Options nosniff always;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }
}
NGINX
# На чистой Ubuntu отключаем только стандартный сайт Nginx.
if [ -L /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sfn /etc/nginx/sites-available/analytics-team /etc/nginx/sites-enabled/analytics-team
nginx -t
systemctl daemon-reload
systemctl enable --now analytics-team nginx
systemctl reload nginx
if command -v ufw >/dev/null && ufw status | head -n 1 | grep -q '^Status: active'; then
    ufw allow 80/tcp
fi
for attempt in $(seq 1 30); do
    if curl --fail --silent http://127.0.0.1:8501/_stcore/health; then
        echo
        echo 'Развёртывание завершено. Пароли: /root/analytics-team-credentials.txt'
        exit 0
    fi
    sleep 2
done
journalctl -u analytics-team -n 50 --no-pager
exit 1
