# Hostinger VPS production deployment guide

This guide deploys the locally tested Barter Express changes, including unlisted
YouTube publishing, to the existing production website.

## Your deployment

| Component | Production setting |
|---|---|
| Website | `https://barterxpress.com` |
| Application | `/opt/barterex/app` |
| Virtual environment | `/opt/barterex/venv-f89c830` |
| Flask entry point | `app:app` |
| Web process | Gunicorn, managed by `barterex.service` |
| Reverse proxy | Nginx, forwarding to `127.0.0.1:8000` |
| Database | Existing PostgreSQL database |
| Deployment | Git, from `main` |
| New process | `barterex-video-publishing.service` |

**Commands marked VPS run in an SSH Bash session on Linux, not in Windows
PowerShell.** Replace placeholders before executing. Run each phase separately
and stop on any error. This guide does not deploy anything by itself.

The website records approvals in PostgreSQL. The separate worker publishes,
checks YouTube processing, activates items, and cleans up temporary storage.
systemd starts the worker automatically at boot and restarts it after a crash.
Users do not authorize YouTube: only the company's channel is authorized.

## 1. Prepare and publish the local code

Before deploying, review all changes in the release. The current work also
includes pre-verification removal, branded emails, and the redesigned receipt;
the deployment is not limited to YouTube.

On your Windows development machine:

```powershell
git status --short
git diff --stat
.\.venv\Scripts\python.exe -m pytest tests\test_video_publishing.py tests\test_activation_video_flow.py tests\test_email_branding.py tests\test_order_receipt.py -q
```

Commit the reviewed application files and migrations, then push them to `main`
using your normal workflow. Review staged files before committing:

```powershell
git diff --cached --stat
git diff --cached --check
```

Never commit `.env`, Google credentials, database files, backups, or generated
test uploads. Never copy your Windows test database onto production.
Do not use a blanket `git add .` without checking what it stages.

## 2. Inspect the existing production service

VPS:

```bash
sudo systemctl cat barterex
sudo systemctl show barterex -p User -p Group -p WorkingDirectory -p EnvironmentFiles
cd /opt/barterex/app
git status --short
git branch --show-current
git rev-parse HEAD
```

Record the current revision for recovery. Confirm the branch is `main` and the
worktree is clean. Do not discard server-side modifications to make deployment
proceed; reconcile them first.

Identify the web service's actual user, group, environment files, and inline
environment settings. Do not publish this output if it contains secrets.
If `User` is empty, the service may run as root: have the operator choose an
appropriate unprivileged account rather than blindly copying that arrangement.

Use the same database, secrets, and Google configuration for web and worker.
Do not overwrite production settings with the development `.env`.

The following steps use **one shared, systemd-compatible environment file**.
If the existing app uses another location, use that location consistently.
If it uses inline `Environment=` values or multiple files, consolidate or
explicitly replicate them before proceeding: systemd environment variables
override values loaded by `load_dotenv()`.

Set these Bash variables to the verified values in this SSH session:

```bash
APP_USER='REPLACE_WITH_WEB_SERVICE_USER'
APP_GROUP='REPLACE_WITH_WEB_SERVICE_GROUP'
ENV_FILE='/etc/barterex/barterex.env'
APP_DIR='/opt/barterex/app'
VENV='/opt/barterex/venv-f89c830'
```

The environment-file path above is a proposed location, not a claim about your
current server. Keep all required production settings, including
`SQLALCHEMY_DATABASE_URI`, `SECRET_KEY`, mail, payment, and other integrations.
Use absolute credential paths and no shell expressions such as `export`,
`$(...)`, or references to other environment variables in this file.

## 3. Prepare the company's Google authorizations

### YouTube

The working company-channel token can be used on the VPS; generating a second
token is not required just because the operating system changes.

Securely configure:

```dotenv
APP_URL=https://barterxpress.com
YOUTUBE_ENABLED=true
YOUTUBE_CLIENT_ID=YOUR_EXISTING_OAUTH_CLIENT_ID
YOUTUBE_CLIENT_SECRET=YOUR_EXISTING_OAUTH_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN=YOUR_WORKING_COMPANY_CHANNEL_REFRESH_TOKEN
YOUTUBE_CHANNEL_ID=UC_YOUR_COMPANY_CHANNEL_ID
```

Check all of these in Google:

- YouTube Data API v3 is enabled in the OAuth client's project.
- The token authorizes the company channel, including its Brand Account where
  applicable, and grants `youtube.upload` and `youtube.readonly`.
- The OAuth consent configuration is suitable for production. External apps
  left in Testing commonly receive refresh tokens that expire after seven days.
  Switching status does not automatically repair an already expired token.
- The API project is permitted to publish unlisted videos. Some unaudited
  projects are restricted to private uploads; consent-screen publishing alone
  does not remove that separate restriction.
- The project's available quota supports your planned volume. Check current
  limits in Google Cloud rather than assuming unlimited uploads.

Cloud project ownership is not channel authorization. Do not use the personal
channel's refresh token or leave its channel ID configured.

### Google Cloud Storage

Windows `gcloud` credentials do not automatically exist on the VPS.

Prefer managed workload identity/federation where available. For a VPS without
that setup, a service-account key is an operational option **only if your
organization permits key creation**. Never bypass an organization policy.
If keys are prohibited, configure supported workload identity/federation and
service-account impersonation before proceeding.

For the direct service-account-key approach:

1. Use a dedicated production service account.
2. Grant it object create/read/delete access on the specific temporary-video
   bucket, for example bucket-scoped Storage Object User. Avoid project Owner,
   Editor, or public bucket access.
3. Securely transfer its JSON credential to a protected location outside Git,
   for example `/etc/barterex/gcs-service-account.json`.
4. Make it readable by the web/worker service account, not other users.
5. Configure:

```dotenv
GCS_BUCKET_NAME=YOUR_TEMP_VIDEO_BUCKET
GOOGLE_APPLICATION_CREDENTIALS=/etc/barterex/gcs-service-account.json
GCS_SERVICE_ACCOUNT_EMAIL=
GCS_SIGNED_URL_MINUTES=20
```

Leaving `GCS_SERVICE_ACCOUNT_EMAIL` empty selects direct credentials in this
code. The private key signs URLs locally; no Windows user login is involved.
For intentional impersonation instead, configure the source identity, target
service account, IAM Credentials API, and required token/signing permissions.

Example permissions for the credential file, after setting the variables above:

```bash
sudo chown root:"$APP_GROUP" /etc/barterex/gcs-service-account.json
sudo chmod 640 /etc/barterex/gcs-service-account.json
```

The parent directory must also permit service-account traversal. Protect the
shared environment file; it contains database and OAuth secrets. If Flask
loads it directly, the application user must be able to read it.

## 4. Configure production bucket CORS

Inspect the bucket's current CORS configuration first, using an authorized
administrator's Google Cloud CLI:

```bash
gcloud storage buckets describe gs://YOUR_TEMP_VIDEO_BUCKET --format="default(cors_config)"
```

Merge production origins with rules that must remain. The required rule is:

```json
[
  {
    "origin": ["https://barterxpress.com"],
    "method": ["PUT"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
```

Add `https://www.barterxpress.com` only if the app actually runs at that origin.
Preserve local origins if you still need local testing. Save the merged rules
as `gcs-cors.production.json` on the administrator's machine and apply them:

```bash
gcloud storage buckets update gs://YOUR_TEMP_VIDEO_BUCKET --cors-file=gcs-cors.production.json
```

This command replaces the bucket's CORS rules; it does not merge them.
Keep the bucket private. Do not apply short lifecycle deletion rules to pending
or retrying submissions: their source must survive until activation completes.

## 5. Maintenance window, backup, and deployment

Schedule a quiet maintenance window. Use your existing maintenance-page
procedure if available. Stop any other scheduled application writers during
the release as well; do not assume stopping Gunicorn stops every writer.

VPS:

```bash
sudo systemctl stop barterex
```

If a publishing worker is already installed, stop it too:

```bash
sudo systemctl stop barterex-video-publishing
```

Do not treat "unit not found" on a first installation as evidence that an
existing worker is safely stopped; inspect any other process manager in use.

Take a PostgreSQL backup **before migration**. Use the actual database name
from production configuration, not the example below. For local PostgreSQL:

```bash
set -o pipefail
sudo install -d -m 700 /var/backups/barterex
BACKUP="/var/backups/barterex/pre-video-release-$(date +%Y%m%d-%H%M%S).dump"
sudo -u postgres pg_dump -Fc -d REPLACE_WITH_PRODUCTION_DATABASE_NAME | sudo tee "$BACKUP" >/dev/null
```

The `pipefail` setting prevents a `pg_dump` failure from being hidden by `tee`.
Confirm the command succeeded and inspect its contents:

```bash
sudo pg_restore --list "$BACKUP"
```

A readable archive list is not a full restore test. Verify restoration in an
isolated test database or use an already tested backup procedure before making
schema changes. For remote/managed PostgreSQL, use its approved backup method.
Keep database passwords out of command history; protect backups and retain an
off-server copy according to your backup policy.

Then update the code:

```bash
cd "$APP_DIR"
git pull --ff-only origin main
git rev-parse HEAD
```

Record the new revision. Confirm it is the intended release.

## 6. Run application commands with the production service environment

An SSH shell may not inherit the web service's environment. To prevent
accidentally migrating SQLite, run checks and migrations as transient systemd
services with the same user, directory, and shared environment file.

Define this Bash function for the current SSH session:

```bash
run_app() {
  sudo systemd-run --wait --pipe --collect \
    --property="User=$APP_USER" \
    --property="Group=$APP_GROUP" \
    --property="WorkingDirectory=$APP_DIR" \
    --property="EnvironmentFile=$ENV_FILE" \
    "$@"
}
```

If your systemd version does not support these options, stop and adapt this
procedure with the operator; do not fall back to an unconfigured Flask command.

Install release dependencies as the deployment account with permission to
update this virtual environment; do not change ownership blindly:

```bash
"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
```

Check PostgreSQL connectivity without printing its credentials:

```bash
run_app "$VENV/bin/python" -c 'from app import app, db; from sqlalchemy import text; ctx = app.app_context(); ctx.push(); assert db.engine.dialect.name == "postgresql", "STOP: not PostgreSQL"; db.session.execute(text("SELECT 1")); print("PostgreSQL connection OK")'
```

Do not continue unless this succeeds. Then:

```bash
run_app "$VENV/bin/flask" --app app:app db current
run_app "$VENV/bin/flask" --app app:app db upgrade
run_app "$VENV/bin/flask" --app app:app db current
run_app "$VENV/bin/flask" --app app:app db heads
```

The current revision should match the deployed migration head. This release's
queue migration is `add_durable_video_publishing`, following
`remove_item_preverification_stage`. Do not use `db stamp` to bypass a failed
migration, and do not call `db.create_all()` as a replacement.

## 7. Check production Google access before opening the website

These commands use the actual service identity and environment.

Check YouTube channel access without uploading:

```bash
run_app "$VENV/bin/python" -c 'from app import app; from services import youtube_publisher as y; ctx = app.app_context(); ctx.push(); client = y._authorized_session(); channels = y._authorized_channel_ids(client); client.close(); print("Authorized channel check OK:", len(channels))'
```

Check bucket access and signing without creating an object:

```bash
run_app "$VENV/bin/python" -c 'from app import app; from services import video_service as v; ctx = app.app_context(); ctx.push(); client = v._client(); list(client.list_blobs(v._bucket_name(), max_results=1)); result = v.generate_upload_url("deployment-check/not-uploaded.mp4", "video/mp4"); assert result.get("success"), "URL signing failed; inspect service logs"; print("Bucket access and upload URL signing OK")'
```

Do not print signed URLs, access tokens, refresh tokens, or credential JSON.
These checks do not prove browser CORS, upload/delete permissions, or successful
YouTube processing. The live acceptance test below is still mandatory.

## 8. Install the continuous systemd worker

The repository's generic service template has example paths that do not match
this VPS. Create a tailored unit using the verified variables from step 2.
This writes a system unit and requires sudo.

VPS:

```bash
sudo tee /etc/systemd/system/barterex-video-publishing.service >/dev/null <<EOF
[Unit]
Description=Barter Express video publishing and cleanup worker
After=network-online.target barterex.service
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/flask --app app:app video-publishing-worker
Restart=on-failure
RestartSec=10
TimeoutStopSec=90
KillSignal=SIGTERM
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
```

Make sure `barterex.service` also uses the chosen shared environment file.
If a change is needed, preserve all existing service configuration and remove
or update conflicting inline environment settings. Do not replace the entire
working Gunicorn service with this worker unit.

Validate, reload, and start:

```bash
sudo systemd-analyze verify /etc/systemd/system/barterex-video-publishing.service
sudo systemctl daemon-reload
sudo systemctl start barterex
sudo systemctl enable --now barterex-video-publishing
sudo systemctl status barterex --no-pager
sudo systemctl status barterex-video-publishing --no-pager
sudo systemctl is-enabled barterex-video-publishing
sudo journalctl -u barterex-video-publishing -n 100 --no-pager
curl -I https://barterxpress.com
```

Confirm the site responds as expected and the worker remains active. A worker
startup message alone does not establish that it can publish.
No Nginx upload-size increase is needed for these direct-to-GCS video uploads.
No Redis/Celery installation or new public worker port is required.

## 9. Live acceptance test: release gate

Use a controlled production account and test item. Use the normal valuation
flow; the local manual 500-BXC test override is not part of this deployment.

- [ ] Open the HTTPS site from a real phone and submit a short item video.
- [ ] Browser upload to GCS succeeds; admin preview plays.
- [ ] Admin approval returns promptly and queues the job.
- [ ] Worker progresses through uploading and processing.
- [ ] YouTube Studio shows the video on the company channel as **unlisted**.
- [ ] The item activates only after the video is processed.
- [ ] Marketplace value matches the saved valuation.
- [ ] Exactly one provisional-credit ledger entry is recorded for activation.
- [ ] The item video link plays from another browser/account.
- [ ] The temporary GCS object is deleted after activation commits.
- [ ] During a separate controlled test, stop the worker, approve a submission,
      verify it remains queued, then restart and verify it completes.
- [ ] On a controlled upload, restarting the worker resumes saved progress
      without duplicate uploads or credits; lease recovery can take five minutes.
- [ ] In a scheduled reboot test, verify web and worker start automatically.

Do not declare production ready just because a local test worked.
Unlisted is link-accessible, not private or restricted to your website.

## 10. Monitoring, troubleshooting, and later deployments

Inspect:

```bash
sudo systemctl is-active barterex-video-publishing
sudo journalctl -u barterex-video-publishing -n 100 --no-pager
sudo journalctl -u barterex -n 100 --no-pager
```

Monitor worker uptime, old queued jobs, publishing failures, cloud-cleanup
failures, YouTube quota, and bucket storage growth. Failed jobs notify the
reviewer team and item owner, but that is not a substitute for an external
service-health alert: a stopped worker cannot process failures.

| Symptom | Action |
|---|---|
| Jobs remain queued | Check worker status, logs, matching database/environment, due time, and lease expiry. |
| Refresh token expired/revoked | Reauthorize the company channel locally, securely update the server token, restart web and worker, then retry. |
| No channel or channel mismatch | Select the correct company/Brand Account during authorization and verify `YOUTUBE_CHANNEL_ID`. |
| HTTP 401/403 | Check authorization, scopes, account/channel, API enablement and quota; do not assume every 403 is a quota error. |
| Browser upload blocked | Inspect OPTIONS/PUT in browser developer tools; check exact CORS origin, signing, permissions, and VPS clock. |
| Video forced private | Resolve Google's API-project publishing restrictions; do not bypass the unlisted check. |
| Saved upload session expired | Check the official channel for the video and use admin reconciliation; never clear the saved session to force a duplicate upload. |
| Upload reaches 100% but item is not live | Check processing/activation stage; 100% means uploaded, not activated. |
| Temporary object remains | Inspect cleanup errors and bucket delete permission; cleanup retries independently. |

After code or credentials change, restart both services:

```bash
sudo systemctl restart barterex
sudo systemctl restart barterex-video-publishing
```

Renewing local credentials does not update a running server process.
Do not switch channels while jobs have personal-channel sessions or video IDs
without reviewing those jobs first.

For future releases, stop relevant writers, back up, deploy, migrate with the
production environment, restart both services, and verify health again.

## 11. Failure and recovery

If a migration or critical acceptance check fails:

1. Keep the site in maintenance mode and stop the worker to prevent further
   uploads or credits while investigating.
2. Preserve logs, the pre-deployment revision, backup, and affected job records.
   Treat logs and dumps as potentially sensitive.
3. Do not automatically downgrade the schema or start old code against an
   incompatible new schema.
4. Prefer a reviewed forward fix. Restore the backup only through a planned,
   tested PostgreSQL recovery procedure, with all writers stopped and an
   explicit understanding of any transactions lost since the backup.
5. Reconcile YouTube and GCS side effects before restarting jobs: restoring a
   database does not undo videos already uploaded or cloud objects deleted.

See [video-storage.md](video-storage.md) for queue semantics and reconciliation.
