# Private stolen-item reporting

## User flow

The small **Report as stolen** link on the item details page opens a sign-in
protected form. It accepts a claim description (30-5,000 characters), an
optional 15-digit IMEI, serial number, police reference, and up to five
JPG/PNG/WebP evidence images (5 MB each). At least one image or identifier is
required, along with a good-faith declaration. The account email is saved for
follow-up; no separate public email input is needed.
After a successful submission, the user is redirected to their dashboard with
a confirmation message and report reference. Invalid submissions remain on the form.

The app validates image content, not just filenames. Evidence is stored as
private database attachments with deferred binary loading, not in static files,
public cloud buckets, item images, or public URLs. Original validated bytes are
preserved; reviewers download files through authenticated, permission-checked
routes with attachment, no-store, and nosniff headers. Keep original evidence.

An account can have only one open report per item and submit up to five reports
per hour. The per-account count is persisted in the database; a PostgreSQL row
lock serializes submissions across workers. Submission errors do not save
partial reports or images.

## Admin flow

The **Stolen-item reports** permission (`reports.manage`) grants queue, report,
and evidence access. Super admins have access automatically; grant the new
permission explicitly to appropriate existing sub-admins through Manage Admins.
Account/project email ownership does not confer application review permissions.

New reports queue an email alert to active authorized admins. Emails contain
the report/item reference and private review link, not claim details or evidence.
Delivery uses the existing post-commit email mechanism; inspect mail logs if
an alert is missing. The database queue remains the source of truth.

The dashboard, navbar shortcut, and report queue display open counts.
Pending and Under review are open; Confirmed and Dismissed are closed.
The default queue filter is Open reports; other status filters and pagination
are available. An admin must supply internal review notes (10-5,000 characters)
when changing status. The latest notes, reviewer and timestamp are retained;
status transitions are recorded in the existing audit log.

Reports are allegations until verified. Neither submission nor confirmation
automatically changes listing availability, seller status, reservations, credits,
or custody. Handle appropriate restrictions and communication separately.
Reporter identities and identifiers must not be exposed on item pages.

## Deployment and operations

Back up the production database, deploy this code, and run migrations using
the production application's environment:

```bash
flask --app app:app db upgrade
```

Migration `add_stolen_item_reports` follows `add_durable_video_publishing`.
Restart web and background services after deployment. No new storage credentials,
cloud bucket, or worker is needed for evidence. Configure the reverse proxy to
accept the intended multipart request size (up to 25 MB of images plus form
overhead), while retaining an appropriate maximum request limit.

Evidence increases database and backup size. Restrict backup access, monitor
growth, and establish an appropriate retention/deletion policy before launch.
There is no automatic evidence purge in this implementation.
Deleting a referenced item/account preserves the report snapshot and attachments
via nullable `SET NULL` foreign keys. Do not downgrade this migration without
preserving reports: downgrade drops these tables.

Acceptance checks:

- Guest clicks lead to login; signed-in users can submit a claim with evidence.
- Invalid/missing evidence is rejected without partial records.
- Listing availability and credits remain unchanged.
- Only reviewers with `reports.manage` can see claims and download attachments.
- The new report appears in the queue, alerts the review team, and increments
  their pending badge; reading alone does not clear it.
- Review updates require valid CSRF, status and notes; closing clears the badge
  and records an audit event.
- Evidence survives service restarts and is covered by database backups.
