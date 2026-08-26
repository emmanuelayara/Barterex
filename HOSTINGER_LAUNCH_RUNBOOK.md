# Hostinger VPS Launch Runbook (Barterex)

This runbook is a practical, step-by-step guide to move this project to Hostinger VPS and launch it successfully.

It is written for this repository structure and current Flask setup.

## Quick Summary

Target stack:

- Ubuntu VPS
- Python virtual environment
- Flask app served by Gunicorn
- Nginx reverse proxy
- PostgreSQL database
- Persistent uploads in shared disk path
- HTTPS via Let's Encrypt

App assumptions from this repo:

- Flask entrypoint: `app:app`
- App code location: `/var/www/barterex/app`
- Upload URL path: `/static/uploads/<filename>`
- Persistent upload folder on VPS: `/var/www/barterex/shared/uploads`

---

## Phase 0: Pre-Migration Checklist

Before touching production:

1. Confirm domain access (DNS control panel).
2. Confirm Hostinger VPS access (root SSH).
3. Take Render backups:
   - DB export
   - current environment variables
   - uploaded images archive (if available)
4. Freeze deployment window.

Example backup commands:

```bash
# Database backup from Render (replace with your Render DB URL)
pg_dump "<RENDER_DATABASE_URL>" > barterex_render_backup.sql

# Optional: compress uploads folder if you have one locally
zip -r uploads_backup.zip static/uploads
```

---

## Phase 1: Prepare Hostinger VPS

## 1.1 Update server and install packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip nginx git postgresql postgresql-contrib ufw
```

## 1.2 Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Expected:

- OpenSSH allowed
- Nginx Full allowed

## 1.3 Create app user and folders

```bash
sudo adduser --system --group --home /var/www/barterex barterex
sudo mkdir -p /var/www/barterex/{app,shared/uploads,logs,releases}
sudo chown -R barterex:barterex /var/www/barterex
```

---

## Phase 2: Deploy Repository Code

## 2.1 Clone repo

```bash
sudo -u barterex git clone https://github.com/emmanuelayara/Barterex.git /var/www/barterex/app
```

## 2.2 Create virtual environment and install dependencies

```bash
sudo -u barterex python3 -m venv /var/www/barterex/venv
sudo -u barterex /var/www/barterex/venv/bin/pip install --upgrade pip
sudo -u barterex /var/www/barterex/venv/bin/pip install -r /var/www/barterex/app/requirements.txt
```

## 2.3 Verify Gunicorn import path

```bash
cd /var/www/barterex/app
sudo -u barterex /var/www/barterex/venv/bin/python -c "from app import app; print('OK:', app.name)"
```

Expected output example:

```text
OK: app
```

---

## Phase 3: Configure Environment Variables

Create env file:

```bash
sudo mkdir -p /etc/barterex
sudo nano /etc/barterex/barterex.env
```

Use this template (replace values):

```env
SECRET_KEY=replace_with_a_long_random_secret
SQLALCHEMY_DATABASE_URI=postgresql://barterex_user:replace_db_password@127.0.0.1:5432/barterex_db
SQLALCHEMY_TRACK_MODIFICATIONS=False

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=Barter Express,info.barterex@gmail.com
MAIL_DEBUG=False

SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
WTF_CSRF_ENABLED=True
WTF_CSRF_TIME_LIMIT=3600

FILE_UPLOAD_MAX_SIZE=10485760
FILE_UPLOAD_ENABLE_VIRUS_SCAN=False

UPLOAD_FOLDER=static/uploads
```

Set permissions:

```bash
sudo chown root:barterex /etc/barterex/barterex.env
sudo chmod 640 /etc/barterex/barterex.env
```

---

## Phase 4: PostgreSQL Setup and Data Import

## 4.1 Create DB and user

```bash
sudo -u postgres psql
```

Run:

```sql
CREATE DATABASE barterex_db;
CREATE USER barterex_user WITH PASSWORD 'replace_db_password';
GRANT ALL PRIVILEGES ON DATABASE barterex_db TO barterex_user;
\q
```

## 4.2 Import Render dump

```bash
psql "postgresql://barterex_user:replace_db_password@127.0.0.1:5432/barterex_db" < barterex_render_backup.sql
```

## 4.3 Run migrations (safe even if already up)

```bash
cd /var/www/barterex/app
sudo -u barterex /var/www/barterex/venv/bin/flask db upgrade
```

---

## Phase 5: Persistent Upload Storage (Critical)

Goal: keep user-uploaded images after deploys/restarts.

## 5.1 Link static/uploads to shared storage

```bash
sudo -u barterex rm -rf /var/www/barterex/app/static/uploads
sudo -u barterex ln -s /var/www/barterex/shared/uploads /var/www/barterex/app/static/uploads
sudo chown -R barterex:barterex /var/www/barterex/shared/uploads
sudo chmod -R 775 /var/www/barterex/shared/uploads
```

## 5.2 Copy old uploaded images

If you have old uploads backup:

```bash
sudo rsync -avh ./uploads_backup/ /var/www/barterex/shared/uploads/
```

Validation example:

```bash
ls -lah /var/www/barterex/shared/uploads | head
```

---

## Phase 6: Configure Gunicorn Service

Create service file:

```bash
sudo nano /etc/systemd/system/barterex.service
```

Paste:

```ini
[Unit]
Description=Barterex Flask App
After=network.target

[Service]
User=barterex
Group=www-data
WorkingDirectory=/var/www/barterex/app
EnvironmentFile=/etc/barterex/barterex.env
ExecStart=/var/www/barterex/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --timeout 120 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable barterex
sudo systemctl start barterex
sudo systemctl status barterex
```

Expected service state:

- `active (running)`

---

## Phase 7: Configure Nginx

Create site config:

```bash
sudo nano /etc/nginx/sites-available/barterex
```

Paste:

```nginx
server {
    listen 80;
    server_name barterexpress.com www.barterexpress.com;

    client_max_body_size 50M;

    location /static/uploads/ {
        alias /var/www/barterex/shared/uploads/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    location /static/ {
        alias /var/www/barterex/app/static/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/barterex /etc/nginx/sites-enabled/barterex
sudo nginx -t
sudo systemctl reload nginx
```

---

## Phase 8: DNS and SSL

## 8.1 DNS

In your DNS panel:

- A record `@` -> your VPS IP
- A record `www` -> your VPS IP

Wait for propagation (usually minutes to a few hours).

## 8.2 SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d barterexpress.com -d www.barterexpress.com
sudo certbot renew --dry-run
```

Expected:

- HTTPS loads without browser warnings

---

## Phase 9: Launch Validation (Go-Live Checklist)

Check all items before announcing launch:

1. Home page loads over HTTPS.
2. Login and registration work.
3. Marketplace loads item images.
4. Upload a new item image.
5. Confirm new image physically exists in shared path:

```bash
ls -lah /var/www/barterex/shared/uploads | tail
```

6. Restart app and confirm uploaded image still visible:

```bash
sudo systemctl restart barterex
```

7. Review logs for errors:

```bash
sudo journalctl -u barterex -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

---

## Phase 10: Ongoing Operations

## 10.1 Deploy app updates

```bash
cd /var/www/barterex/app
sudo -u barterex git pull origin main
sudo -u barterex /var/www/barterex/venv/bin/pip install -r requirements.txt
sudo -u barterex /var/www/barterex/venv/bin/flask db upgrade
sudo systemctl restart barterex
```

## 10.2 Daily backup examples

Database backup:

```bash
pg_dump "postgresql://barterex_user:replace_db_password@127.0.0.1:5432/barterex_db" > /var/backups/barterex_db_$(date +%F).sql
```

Uploads backup:

```bash
tar -czf /var/backups/barterex_uploads_$(date +%F).tar.gz /var/www/barterex/shared/uploads
```

---

## Troubleshooting Guide

## Issue: 502 Bad Gateway

Checks:

```bash
sudo systemctl status barterex
sudo journalctl -u barterex -n 100 --no-pager
```

Likely causes:

- Gunicorn not running
- wrong `app:app` entry
- invalid env file

## Issue: Uploaded images not showing

Checks:

```bash
ls -lah /var/www/barterex/shared/uploads
ls -lah /var/www/barterex/app/static/uploads
```

Likely causes:

- symlink missing
- wrong folder permissions
- old DB paths pointing to missing filenames

## Issue: Static files not loading

Checks:

```bash
sudo nginx -t
sudo tail -n 100 /var/log/nginx/error.log
```

Likely causes:

- wrong `alias` path
- Nginx config typo

---

## Rollback Plan

If launch fails critically:

1. Keep old platform live until Hostinger passes all checks.
2. Re-point DNS to previous host.
3. Restore latest DB and uploads backups.

---

## Final Acceptance Criteria

You can consider migration complete when all are true:

1. App is reachable at `https://barterexpress.com`.
2. Gunicorn service is stable after reboot.
3. Images persist after deploy and restart.
4. DB reads/writes work.
5. Backups are running on schedule.
