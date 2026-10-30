# Verification video storage

Activation requires a finite, positive saved AI valuation that rounds to at
least 1 BXC. Video approval sets the marketplace value and credits provisional
BXC using that same rounded amount, recording an activation ledger entry.
Missing or invalid AI estimates block approval before publishing to YouTube;
an admin-entered value is not a substitute. Repeating approval must not grant
credits again. Admin approval queues publishing; failed publishing never grants
credits or lists the item.

## Durable unlisted publishing

`ItemVideo` is also the durable job record. The states are:

`pending` -> `queued` -> `publishing` -> `approved`.

Temporary errors enter `retry_wait` with exponential backoff (60, 120, 240,
480 seconds). The fifth error stops the job in `publish_failed` and notifies
the reviewer team and owner. Permanent processing/visibility errors stop
immediately. Admins can retry without discarding the saved upload session or
YouTube ID. Upload progress is recorded after each acknowledged chunk and is
visible in Video Review. Refresh that page to see updates; 100% means uploaded,
not necessarily processed or activated.

The worker saves the resumable session before sending bytes. After a crash it
probes the same session and resumes at YouTube's acknowledged offset. The
YouTube ID is committed separately before activation. Activation, provisional
credits, final status, audit, and notification queuing then commit together.
Temporary cloud deletion runs only after approval/rejection commits and is
retried independently, with a maximum six-hour delay between cleanup attempts.
Already-deleted cloud objects count as successful cleanup.

All uploads explicitly use **unlisted** visibility. Anyone possessing the link
can view/share it; this is not authenticated access limited to the item page.
The worker checks authorized channel ownership, unlisted visibility and
YouTube processing before activation. Processing is polled every 30 seconds
and stops for review if the job is still processing 24 hours after it started.
A YouTube API project restricted to private
uploads must resolve Google's restrictions before these checks can pass.

Before creating a new upload session, the worker checks that the OAuth token
can access a YouTube channel and, when set, that it matches `YOUTUBE_CHANNEL_ID`.
A missing or mismatched channel stops publishing for operator attention without
starting an upload. A valid Google login alone does not establish channel access.
Re-run `get_youtube_refresh_token.py` and select the official YouTube channel
(including its Brand Account, if applicable), update `YOUTUBE_REFRESH_TOKEN`,
restart the worker, then retry the job in Video Review. Resuming a saved session
still probes that session directly; channel ownership is checked before activation.

### Ambiguous completion and manual recovery

If YouTube acknowledges an upload but the response/DB write is lost, probing
the persisted session can recover the video ID without uploading again.
If that session has expired or disappeared, the job stops instead of creating
a possible duplicate. Open YouTube Studio on the official channel, locate the
exact item video, and enter its 11-character ID under **Recover an upload already
on the official channel**. Every new upload description begins with its item and
submission reference. The app verifies that reference, channel ownership and
unlisted visibility, records the reconciliation, and queues activation.

Never reset/delete a saved upload session just to bypass this check. If no video
exists, an operator must establish that before arranging a replacement submission;
automatic re-upload is deliberately blocked when completion cannot be determined.
The database uniquely constrains YouTube IDs so one channel video cannot be
linked to multiple submission records.

## Production deployment

For the existing Hostinger VPS, follow the
[Hostinger production deployment guide](hostinger-production-deployment.md),
which includes the actual application paths, production-environment checks,
backup procedure, worker installation, and live acceptance checklist.

1. Back up the production database. Deploy the code with both web and publishing
   workers stopped, run `flask --app app:app db upgrade`, then restart the web app.
   The migration follows `remove_item_preverification_stage`. Existing pending,
   approved and rejected videos keep their states; old undeleted copies become
   eligible for cleanup. Do not roll back the queue migration while jobs exist.
2. Configure the **same persistent database and environment** for web and worker.
   PostgreSQL is recommended for production; neither an in-memory database nor
   process-local background threads are the queue.
3. Set `APP_URL` to the deployed HTTPS origin so worker-generated notification
   links do not point at localhost.
4. Keep `GCS_BUCKET_NAME` and production credentials available to the service
   user. Prefer attached workload identity/ADC or a protected service-account
   credential file. Development `gcloud` credentials in your Windows account are
   not automatically available to a Linux service account. The account needs
   object read/delete access and permission to sign upload/read URLs; impersonation
   also requires the configured IAM permissions. Never commit credential files.
5. Apply bucket CORS rules for the exact production HTTPS origin(s), allowing PUT
   and Content-Type. Preserve existing origins when changing bucket rules. Set
   suitable cloud retention/lifecycle policies for truly abandoned uploads, but
   do not delete pending/retrying videos prematurely: the worker needs their
   source until activation commits.
6. Enable YouTube Data API v3. **Reauthorize the official channel** using
   `get_youtube_refresh_token.py`: it now requests `youtube.upload` and
   `youtube.readonly`. An existing upload-only refresh token cannot perform the
   new ownership/processing checks. Store the new token/client settings in the
   production environment, keep `YOUTUBE_ENABLED=true`, and preferably set
   `YOUTUBE_CHANNEL_ID` to the official `UC...` channel ID. Use a production OAuth
   consent configuration; testing-mode tokens may expire. Verify Google's quota
   and publishing restrictions for your API project.
7. Start and enable the continuous worker using
   [barterex-video-publishing.service](../deploy/systemd/barterex-video-publishing.service).
   Adjust the account, working directory, virtualenv and EnvironmentFile paths
   to match your server. Install it in systemd's service directory, reload systemd,
   and enable/start `barterex-video-publishing.service`. Inspect its status and
   journal after deployment. Restart it whenever code or credentials change.
   No Redis/Celery service is required.

For a local foreground worker:

```powershell
.\.venv\Scripts\flask.exe --app app:app video-publishing-worker
```

To process a single due publish/cleanup job:

```powershell
.\.venv\Scripts\flask.exe --app app:app video-publishing-worker --once
```

Each job is claimed with a five-minute lease and a unique fencing token.
HTTP operations have 60-second timeouts and progress callbacks renew the lease.
Overlapping workers cannot commit another worker's job. If a worker is killed,
its due job is reclaimable after lease expiry. A single worker is the normal
starting point; keep it running independently of web-server worker timeouts.
Allow enough RAM for the video (up to 200 MB) and upload request buffers: uploads
avoid persistent VPS disk storage, not VPS memory/network traffic.

### Deployment acceptance checks

- Approve one controlled item: the web request should queue immediately without
  waiting for YouTube.
- Observe queued/uploading/processing states and confirm unlisted playback from
  the item page, listing activation and exactly one provisional-credit entry.
- Confirm the source cloud object is deleted only after activation.
- Restart the worker during an upload; verify it resumes the saved session.
- Stop the worker: jobs must remain queued in the DB. Restart it and check recovery.
- Confirm the official channel, production browser CORS, worker credentials,
  notification links and cleanup count. Local success alone does not prove the
  production service user has Google permissions.

Videos upload directly from the browser to Google Cloud Storage using signed
PUT URLs. A successful upload-URL request does not prove that the browser can
upload: bucket CORS rules must also allow the page's exact origin.

## Local development CORS

The configuration in [gcs-cors.local.json](../deploy/gcs-cors.local.json) allows
PUT uploads from `http://127.0.0.1:5000` and `http://localhost:5000`.

Inspect the current bucket rules before changing them:

```powershell
gcloud storage buckets describe gs://YOUR_BUCKET_NAME --format="default(cors_config)"
```

Applying a CORS file replaces the bucket's existing CORS configuration. If rules
already exist, merge the local origins into those rules rather than overwriting
production access. If no existing rules need preserving, run from the repository
root:

```powershell
gcloud storage buckets update gs://YOUR_BUCKET_NAME --cors-file=deploy\gcs-cors.local.json
```

This requires `storage.buckets.get` to inspect the configuration and
`storage.buckets.update` to change it. Object upload permissions alone are not
sufficient. Have the bucket administrator apply the change if necessary.

For production, explicitly allow the deployed site's HTTPS origin. Do not use
the local-only configuration as a replacement for production rules.

Retry after the update. In browser developer tools, the storage upload's OPTIONS
response must include `Access-Control-Allow-Origin` matching the page origin and
allow PUT and Content-Type. Then check the PUT response separately for upload
permissions or signature errors. Do not share signed URLs; they grant temporary
access to the object.
