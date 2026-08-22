# Render -> Hostinger VPS Migration Guide (Barterex)

This guide is tailored to this repository and focuses on solving image persistence, deployment stability, and production readiness.

## 1. Target Architecture

- App runtime: Flask + Gunicorn
- Reverse proxy: Nginx
- Database: PostgreSQL
- Persistent uploads: Hostinger VPS disk path outside release code directory

Recommended directory layout:

- `/var/www/barterex/app` -> Git repository checkout
- `/var/www/barterex/venv` -> Python virtual environment
- `/var/www/barterex/shared/uploads` -> Persistent user-uploaded images
- `/var/www/barterex/logs` -> Application logs
- `/etc/barterex/barterex.env` -> Environment variables

## 2. Provision Hostinger VPS

1. Choose Ubuntu 22.04 or 24.04.
2. Point DNS records:
   - `barterexpress.com` -> VPS public IP
   - `www.barterexpress.com` -> VPS public IP
3. SSH into VPS and update packages:

```bash
sudo apt update && sudo apt upgrade -y
```

## 3. Install Required Packages

```bash
sudo apt install -y python3 python3-venv python3-pip nginx git postgresql postgresql-contrib ufw
```

Firewall setup:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 4. Create Service User and Directories

```bash
sudo adduser --system --group --home /var/www/barterex barterex
sudo mkdir -p /var/www/barterex/app
sudo mkdir -p /var/www/barterex/shared/uploads
sudo mkdir -p /var/www/barterex/logs
sudo chown -R barterex:barterex /var/www/barterex
```

## 5. Deploy Repository

```bash
sudo -u barterex git clone https://github.com/emmanuelayara/Barterex.git /var/www/barterex/app
sudo -u barterex python3 -m venv /var/www/barterex/venv
sudo -u barterex /var/www/barterex/venv/bin/pip install --upgrade pip
sudo -u barterex /var/www/barterex/venv/bin/pip install -r /var/www/barterex/app/requirements.txt
```

## 6. Exact Production .env File

Create file: `/etc/barterex/barterex.env`

```env
SECRET_KEY=replace_with_long_random_secret
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

# Keep this for current code behavior
UPLOAD_FOLDER=static/uploads
```

Permissions:

```bash
sudo mkdir -p /etc/barterex
sudo chown root:barterex /etc/barterex/barterex.env
sudo chmod 640 /etc/barterex/barterex.env
```

## 7. Upload Path Settings (Persistent Images)

Current code writes to `app.config['UPLOAD_FOLDER']` (default `static/uploads`).

To ensure persistence across deployments:

1. Use a symlink from repo static folder to shared persistent folder.
2. Keep URLs unchanged (`/static/uploads/...`) so templates and DB data continue to work.

Commands:

```bash
sudo -u barterex rm -rf /var/www/barterex/app/static/uploads
sudo -u barterex ln -s /var/www/barterex/shared/uploads /var/www/barterex/app/static/uploads
sudo chown -R barterex:barterex /var/www/barterex/shared/uploads
sudo chmod -R 775 /var/www/barterex/shared/uploads
```

Optional code hardening in `app.py`:

```python
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'static/uploads/')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
```

## 8. PostgreSQL Setup

```bash
sudo -u postgres psql
```

Inside PostgreSQL shell:

```sql
CREATE DATABASE barterex_db;
CREATE USER barterex_user WITH PASSWORD 'replace_db_password';
GRANT ALL PRIVILEGES ON DATABASE barterex_db TO barterex_user;
\q
```

Run migrations:

```bash
cd /var/www/barterex/app
sudo -u barterex /var/www/barterex/venv/bin/flask db upgrade
```

## 9. Gunicorn Systemd Service

Create `/etc/systemd/system/barterex.service` with:

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

## 10. Nginx Site Config

Create `/etc/nginx/sites-available/barterex` with:

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

## 11. HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d barterexpress.com -d www.barterexpress.com
sudo certbot renew --dry-run
```

## 12. Migrate Data from Render

### Database

```bash
pg_dump "<RENDER_DATABASE_URL>" > barterex.sql
psql "postgresql://barterex_user:replace_db_password@127.0.0.1:5432/barterex_db" < barterex.sql
```

### Uploaded files

Copy existing upload files into:

- `/var/www/barterex/shared/uploads`

Ensure owner and permissions stay correct:

```bash
sudo chown -R barterex:barterex /var/www/barterex/shared/uploads
sudo chmod -R 775 /var/www/barterex/shared/uploads
```

## 13. Validate After Cutover

1. Open homepage, marketplace, dashboard.
2. Confirm old images render.
3. Upload a new image and confirm file appears in `/var/www/barterex/shared/uploads`.
4. Restart services and re-test.

```bash
sudo systemctl restart barterex
sudo systemctl restart nginx
```

Logs:

```bash
sudo journalctl -u barterex -f
sudo tail -f /var/log/nginx/error.log
```

## 14. Optional Cloudinary Removal Cleanup

If you are fully committing to VPS local storage:

1. Remove cloudinary from `requirements.txt`.
2. Delete Cloudinary-only docs if no longer needed:
   - `CLOUDINARY_QUICK_START.md`
   - `CLOUDINARY_SETUP_GUIDE.md`
   - `CLOUDINARY_TECHNICAL_DOCS.md`
   - `RENDER_CLOUDINARY_SETUP_FINAL.md`

## 15. Rollback Plan

If deploy fails:

1. Keep previous VPS snapshot before migration.
2. Keep Render service active until Hostinger validation is complete.
3. Restore DB backup and re-point DNS back if needed.

---

If you want, the next step can be an automated deployment script (`deploy_hostinger.sh`) added to this repo using these exact paths.
