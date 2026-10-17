# Reservation and listing maintenance

The `maintenance-sweep` Flask command releases expired reservation holds,
finishes expired failed-item title-transfer decisions, and deactivates listings
that have passed the 30-day freshness window. It is safe to rerun; the existing
reservation transitions are locked and status-checked, and listings are only
deactivated while still approved and available.

The command intentionally does not process account deletion requests. Account
deletion is permanent and remains a separate, manually operated process.

## Hostinger/Linux systemd timer

The unit files in `deploy/systemd` use the Hostinger paths and service account
from `HOSTINGER_LAUNCH_RUNBOOK.md`. Adjust `User`, `Group`, `WorkingDirectory`,
the virtualenv path, and `EnvironmentFile` in
`barterex-maintenance.service` if the deployment differs.

Install and enable the timer on the application host:

```bash
sudo install -m 0644 deploy/systemd/barterex-maintenance.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/barterex-maintenance.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now barterex-maintenance.timer
sudo systemctl status barterex-maintenance.timer
```

The sweep runs two minutes after boot and then on five-minute calendar
boundaries. systemd will not start a second instance while the previous
oneshot service is still running. Check individual run results and failures with:

```bash
sudo systemctl list-timers barterex-maintenance.timer
sudo journalctl -u barterex-maintenance.service
```

Run a one-off sweep manually from the application directory with:

```bash
/var/www/barterex/venv/bin/flask --app app:app maintenance-sweep
```

The command applies due transitions immediately; it is not a preview or
dry-run. No database migration is required for these maintenance tasks.
