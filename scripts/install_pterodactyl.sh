#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[Pterodactyl helper] ERROR line $LINENO: $BASH_COMMAND" >&2' ERR
DOMAIN="${DOMAIN:-}"; EMAIL="${EMAIL:-}"; DB_PASSWORD="${DB_PASSWORD:-$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)}"
if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then echo "DOMAIN and EMAIL are required"; exit 2; fi
[[ $(id -u) -eq 0 ]] || { echo "Run as root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl unzip tar git nginx mariadb-server redis-server supervisor cron lsb-release python3
if . /etc/os-release && [[ "$ID" == "ubuntu" ]]; then
  apt-get install -y software-properties-common
  if ! apt-cache policy php8.3-cli | grep -q 'Candidate: [0-9]'; then add-apt-repository -y ppa:ondrej/php; apt-get update; fi
fi
apt-get install -y php-cli php-fpm php-mysql php-mbstring php-bcmath php-gd php-xml php-curl php-zip php-tokenizer php-intl php-redis

install -d -o www-data -g www-data /var/www/pterodactyl
cd /var/www/pterodactyl
if [[ ! -f artisan ]]; then
  curl --retry 3 --fail --location https://github.com/pterodactyl/panel/releases/latest/download/panel.tar.gz -o /tmp/pterodactyl.tar.gz
  tar -xzf /tmp/pterodactyl.tar.gz -C /var/www/pterodactyl
fi
[[ -f .env ]] || cp .env.example .env
curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer
composer install --no-dev --optimize-autoloader --no-interaction
systemctl enable --now mariadb redis-server nginx supervisor

mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS panel CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'pterodactyl'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER 'pterodactyl'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON panel.* TO 'pterodactyl'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

# Configure only well-known Laravel environment keys; leave mail/admin creation for the operator.
python3 - "$DOMAIN" "$DB_PASSWORD" <<'PY'
from pathlib import Path
import sys
p=Path('/var/www/pterodactyl/.env'); text=p.read_text()
vals={'APP_URL':'http://'+sys.argv[1],'DB_HOST':'127.0.0.1','DB_PORT':'3306','DB_DATABASE':'panel','DB_USERNAME':'pterodactyl','DB_PASSWORD':sys.argv[2],'CACHE_STORE':'redis','CACHE_DRIVER':'redis','SESSION_DRIVER':'database','QUEUE_CONNECTION':'redis'}
lines=text.splitlines(); out=[]; seen=set()
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        k=line.split('=',1)[0]
        if k in vals: out.append(k+'='+vals[k]); seen.add(k); continue
    out.append(line)
for k,v in vals.items():
    if k not in seen: out.append(k+'='+v)
p.write_text('\n'.join(out)+'\n')
PY
php artisan key:generate --force
php artisan migrate --seed --force
php artisan storage:link || true
chown -R www-data:www-data /var/www/pterodactyl

SOCKET="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || true)"
[[ -n "$SOCKET" ]] || { echo "PHP-FPM socket not found"; exit 1; }
cat >/etc/nginx/sites-available/pterodactyl.conf <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};
    root /var/www/pterodactyl/public;
    index index.php;
    location / { try_files \$uri \$uri/ /index.php?\$query_string; }
    location ~ \.php$ {
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;
        fastcgi_pass unix:${SOCKET};
    }
}
NGINX
ln -sf /etc/nginx/sites-available/pterodactyl.conf /etc/nginx/sites-enabled/pterodactyl.conf
nginx -t
systemctl reload nginx
umask 077; printf 'Pterodactyl DB user: pterodactyl\nPterodactyl DB password: %s\nPterodactyl DB: panel\n' "$DB_PASSWORD" >/root/pterodactyl-db-credentials.txt

echo "Pterodactyl Panel files, database, PHP-FPM, Redis and Nginx are configured for ${DOMAIN}. Add TLS and create the first panel admin before public use."
