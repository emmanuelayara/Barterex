# Verification video storage

Activation requires a finite, positive saved AI valuation that rounds to at
least 1 BXC. Video approval sets the marketplace value and credits provisional
BXC using that same rounded amount, recording an activation ledger entry.
Missing or invalid AI estimates block approval before publishing to YouTube;
an admin-entered value is not a substitute. Repeating approval must not grant
credits again. Failed publishing leaves the video pending and grants no credit.

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
