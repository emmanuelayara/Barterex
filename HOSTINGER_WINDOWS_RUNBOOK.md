# Hostinger Migration Runbook for Windows (Barterex)

This guide is for running the migration from a Windows machine while deploying to a Linux Hostinger VPS.

Important:

- Your VPS should still be Ubuntu/Linux.
- You run migration commands from Windows PowerShell using SSH.

## 1. What Is Different on Windows

Only your local operator machine changes. The server steps stay Linux.

From Windows you will use:

- PowerShell
- OpenSSH client (`ssh`, `scp`)
- Optional: PostgreSQL tools (`pg_dump`, `psql`) for DB import/export

## 2. One-Time Setup on Windows

## 2.1 Install or verify OpenSSH client

PowerShell:

```powershell
ssh -V
scp -V
```

If missing, install in Windows Settings:

- Settings -> Apps -> Optional Features -> Add OpenSSH Client

## 2.2 Install Git (optional, local repo management)

```powershell
git --version
```

Download if needed: https://git-scm.com/download/win

## 2.3 Install PostgreSQL client tools (for backup/restore)

Option A: install full PostgreSQL for Windows
- https://www.postgresql.org/download/windows/

Option B: use a temporary Docker postgres client image if you prefer containerized tools.

Verify:

```powershell
pg_dump --version
psql --version
```

## 2.4 (Recommended) Use an SSH key

Generate key (if you do not have one):

```powershell
ssh-keygen -t ed25519 -C "barterex-hostinger"
```

Default key path:

- `C:\Users\<you>\\.ssh\\id_ed25519`

Copy the public key (`id_ed25519.pub`) into Hostinger VPS authorized keys.

---

## 3. Connect to Hostinger VPS from Windows

```powershell
ssh root@<YOUR_VPS_IP>
```

If using key explicitly:

```powershell
ssh -i C:\Users\<you>\\.ssh\\id_ed25519 root@<YOUR_VPS_IP>
```

---

## 4. Server Setup (Run on VPS after SSH)

Run these inside the SSH session (Linux commands):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip nginx git postgresql postgresql-contrib ufw
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Create app user and folders:

```bash
sudo adduser --system --group --home /var/www/barterex barterex
sudo mkdir -p /var/www/barterex/{app,shared/uploads,logs}
sudo chown -R barterex:barterex /var/www/barterex
```

---

## 5. Deploy App Code (Run on VPS)

```bash
sudo -u barterex git clone https://github.com/emmanuelayara/Barterex.git /var/www/barterex/app
sudo -u barterex python3 -m venv /var/www/barterex/venv
sudo -u barterex /var/www/barterex/venv/bin/pip install --upgrade pip
sudo -u barterex /var/www/barterex/venv/bin/pip install -r /var/www/barterex/app/requirements.txt
```

---

## 6. Configure Production .env (Run on VPS)

```bash
sudo mkdir -p /etc/barterex
sudo nano /etc/barterex/barterex.env
```

Paste and edit values:

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

Permissions:

```bash
sudo chown root:barterex /etc/barterex/barterex.env
sudo chmod 640 /etc/barterex/barterex.env
```

---

## 7. Persistent Uploads (Run on VPS)

```bash
sudo -u barterex rm -rf /var/www/barterex/app/static/uploads
sudo -u barterex ln -s /var/www/barterex/shared/uploads /var/www/barterex/app/static/uploads
sudo chown -R barterex:barterex /var/www/barterex/shared/uploads
sudo chmod -R 775 /var/www/barterex/shared/uploads
```

This is the key fix that prevents image loss across deploy/restart.

---

## 8. Database Migration From Windows

## 8.1 Export from old Render database (run on Windows PowerShell)

```powershell
pg_dump "<RENDER_DATABASE_URL>" > barterex_render_backup.sql
```

## 8.2 Upload SQL dump from Windows to VPS

```powershell
scp .\barterex_render_backup.sql root@<YOUR_VPS_IP>:/root/
```

## 8.3 Import on VPS

SSH into VPS:

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE barterex_db;
CREATE USER barterex_user WITH PASSWORD 'replace_db_password';
GRANT ALL PRIVILEGES ON DATABASE barterex_db TO barterex_user;
\q
```

Import dump:

```bash
psql "postgresql://barterex_user:replace_db_password@127.0.0.1:5432/barterex_db" < /root/barterex_render_backup.sql
```

Run migrations:

```bash
cd /var/www/barterex/app
sudo -u barterex /var/www/barterex/venv/bin/flask db upgrade
```

---

## 9. Upload Existing Image Files From Windows

If you have local uploads backup on Windows:

```powershell
scp -r .\uploads_backup\* root@<YOUR_VPS_IP>:/var/www/barterex/shared/uploads/
```

Fix ownership on VPS:

```bash
sudo chown -R barterex:barterex /var/www/barterex/shared/uploads
```

---

## 10. Gunicorn Service (Run on VPS)

Create service file:

```bash
sudo nano /etc/systemd/system/barterex.service
```

Content:

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

Start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable barterex
sudo systemctl start barterex
sudo systemctl status barterex
```

---

## 11. Nginx Setup (Run on VPS)

```bash
sudo nano /etc/nginx/sites-available/barterex
```

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

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/barterex /etc/nginx/sites-enabled/barterex
sudo nginx -t
sudo systemctl reload nginx
```

---

## 12. DNS + SSL

In Hostinger DNS panel:

- A record `@` -> VPS IP
- A record `www` -> VPS IP

Then on VPS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d barterexpress.com -d www.barterexpress.com
sudo certbot renew --dry-run
```

---

## 13. Launch Verification

Checks to run:

1. Site opens on HTTPS.
2. Login/register works.
3. Marketplace images load.
4. Upload a test image.
5. Confirm file is present:

```bash
ls -lah /var/www/barterex/shared/uploads | tail
```

6. Restart app and confirm image still shows:

```bash
sudo systemctl restart barterex
```

7. Check logs:

```bash
sudo journalctl -u barterex -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

---

## 14. Day-2 Deployment From Windows

From PowerShell, connect and deploy:

```powershell
ssh root@<YOUR_VPS_IP>
```

On VPS:

```bash
cd /var/www/barterex/app
sudo -u barterex git pull origin main
sudo -u barterex /var/www/barterex/venv/bin/pip install -r requirements.txt
sudo -u barterex /var/www/barterex/venv/bin/flask db upgrade
sudo systemctl restart barterex
```

---

## 15. Common Windows-Side Errors

## Error: `ssh` not recognized

Fix: install OpenSSH Client in Windows Optional Features.

## Error: `pg_dump` not recognized

Fix: install PostgreSQL tools and restart PowerShell.

## Error: `scp` permission denied

Fixes:

- Ensure destination path ownership allows write.
- Upload to `/root/` first, then move with `sudo mv`.

## Error: line endings in scripts

If you create shell scripts from Windows, convert CRLF -> LF:

```bash
sudo apt install -y dos2unix
dos2unix your_script.sh
```

---

## 16. Completion Criteria

Migration is complete when:

1. `https://barterexpress.com` is live.
2. Gunicorn is `active (running)`.
3. New uploads persist after restart/deploy.
4. DB read/write operations succeed.
5. SSL renew dry-run passes.
