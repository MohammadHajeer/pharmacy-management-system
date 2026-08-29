# Shared Neon/PostgreSQL Backup and Restore Runbook

Verified against the Neon documentation on **2026-08-29**. This runbook covers the shared Phase 1 database only; it does not add an application-level backup feature.

## Repository connection convention

`config/settings.py` reads the application connection from `DATABASE_URL` through `dj_database_url.config()`. Keep the normal application URL unchanged during backup operations.

For `pg_dump` and `pg_restore`, obtain a **direct/unpooled** URL from Neon by opening **Connect** and turning **Connection pooling** off. A pooled hostname contains `-pooler` and must not be used for these tools.

Use placeholders in commands and keep real URLs only in temporary environment variables or an approved secret store. Never put a connection string in Git, this document, an issue, or team chat. Database dump files contain sensitive data and must also stay outside the repository.

## Choose the recovery method

| Need | Use |
| --- | --- |
| Recover a recent accidental change | Neon instant restore within the configured history window |
| Save a point before a migration or bulk change | Manual Neon snapshot |
| Keep a portable/off-platform copy | `pg_dump` custom-format export |
| Recover from a portable export | `pg_restore` into an empty isolated database, verify, then cut over |

Neon history retention and snapshot limits depend on the current plan. Check **Settings → Instant restore** and **Postgres database → Backup & Restore** before relying on a particular recovery range. Instant restore and snapshot creation apply to **root branches**; confirm that the shared branch is a root branch.

## A. Neon-native backup and recovery

### Create a manual snapshot

Use this before migrations, bulk imports, or other high-risk changes.

1. In the Neon Console, open the shared project and select its root branch.
2. Open **Postgres database → Backup & Restore**. Enable the enhanced view if the snapshot controls are hidden.
3. Select **Create snapshot** and name it `pre-<change>-<YYYYMMDDTHHMMSSZ>` using UTC.
4. Confirm that the snapshot appears in the list with the expected source branch and creation time.
5. Do not delete an older snapshot merely to free a plan limit unless the team has confirmed that it is no longer needed. If no snapshot slot is available, create the external export in section B.

### Restore from a snapshot — preview first

1. Tell the team that a restore is being prepared and stop writes to the shared database before finalizing it.
2. In **Backup & Restore**, locate the snapshot and choose **Restore → Multi-step restore**.
3. Neon creates a separate restored branch while leaving the shared branch unchanged. Use its connection details or SQL Editor to verify key users, medicines, batches, stock movements, invoices, and payments.
4. If verification fails, abandon the restored branch and leave the shared branch unchanged.
5. If verification passes, use Neon's **Migrate connections and settings** action to finalize the restored branch as the shared branch.
6. Confirm application login and representative read-only screens. The shared connection details remain stable after finalization; the replaced branch is retained as `<branch_name> (old)`.
7. Keep the old branch until the team signs off. Delete it later only through the Neon Console and only after confirming that rollback is no longer required.

CLI equivalent for steps 2–5, when the workspace is already linked to the correct Neon project:

```powershell
neon snapshots list
neon snapshots restore <SNAPSHOT_ID> --target-branch <SHARED_ROOT_BRANCH> --name <RESTORED_BRANCH_NAME>
# Inspect the restored branch. Then run the exact finalize command printed above:
neon snapshots finalize <RESTORED_BRANCH_ID>
```

The identifier passed to `snapshots finalize` is the **new restored branch ID**, not the shared target branch ID.

### Point-in-time restore after a recent incident

1. Record the incident time in UTC and tell the team to stop writes.
2. In the Neon Console, select the shared root branch and open **Postgres database → Backup & Restore → Restore from history**.
3. Choose a UTC timestamp immediately before the damaging action. It must fall inside the project's current history window.
4. Use **Preview data** to run read-only checks and compare schemas before restoring.
5. Confirm the target carefully, then select **Restore**.
6. Verify the application and key records. Neon keeps the connection details unchanged and automatically preserves the pre-restore state in a backup branch.

Important: point-in-time restore is a complete replacement, not a merge. It restores schema and data for **every database on the selected branch**, drops changes made after the selected time, and temporarily interrupts existing connections.

## B. Portable export with `pg_dump`

### Create and verify the export

1. Install PostgreSQL client tools matching the Neon project's PostgreSQL major version.
2. In Neon **Connect**, select the shared branch and database, turn connection pooling off, and copy the direct URL into a temporary PowerShell variable.
3. Choose a secure backup directory outside the repository and run:

```powershell
$env:BACKUP_DATABASE_URL = "<DIRECT_UNPOOLED_SOURCE_DATABASE_URL>"
pg_dump -V
pg_dump -Fc -v -d "$env:BACKUP_DATABASE_URL" -f "<SECURE_BACKUP_DIR>\pharmacy_<YYYYMMDDTHHMMSSZ>.dump"
pg_restore -l "<SECURE_BACKUP_DIR>\pharmacy_<YYYYMMDDTHHMMSSZ>.dump" | Select-Object -First 20
Get-FileHash -Algorithm SHA256 "<SECURE_BACKUP_DIR>\pharmacy_<YYYYMMDDTHHMMSSZ>.dump"
Remove-Item Env:BACKUP_DATABASE_URL
```

4. Treat the export as successful only if `pg_dump` exits successfully, the archive is non-empty, and `pg_restore -l` can read its table of contents.
5. Record the UTC timestamp, source branch/database names, PostgreSQL client version, file size, and SHA-256 hash without recording the URL or password.
6. Store the dump in the team's approved protected location. Do not commit it.

## C. Restore a portable export

Do not test a dump by restoring it over the shared database.

1. In Neon, create an isolated recovery branch or temporary project and create a **new empty database** for the restore.
2. Get that empty database's direct/unpooled URL and set it only for the current shell.
3. Restore the archive:

```powershell
$env:RESTORE_DATABASE_URL = "<DIRECT_UNPOOLED_EMPTY_TARGET_DATABASE_URL>"
pg_restore -v -O --single-transaction -d "$env:RESTORE_DATABASE_URL" "<SECURE_BACKUP_DIR>\pharmacy_<YYYYMMDDTHHMMSSZ>.dump"
Remove-Item Env:RESTORE_DATABASE_URL
```

`-O` makes the restoring Neon role own the restored objects and avoids source-owner errors. `--single-transaction` prevents a failed restore from leaving a partially restored database.

4. Point a local test session—not the shared deployment—at the recovered database using its pooled application URL, then run:

```powershell
$env:DATABASE_URL = "<POOLED_RECOVERED_DATABASE_URL>"
uv run manage.py check --database default
uv run manage.py showmigrations --plan
Remove-Item Env:DATABASE_URL
```

5. Verify login and representative counts/records for users, medicines, batches, stock movements, invoices, and payments.
6. For an actual cutover, stop writes, update the deployment's secret `DATABASE_URL` to the recovered database's **pooled** application URL, restart the application, and repeat the verification. Keep the previous database untouched until team sign-off.

## Failure and rollback rules

- If the restore point, source branch, target branch, or database is uncertain, stop; do not restore.
- If a preview or dump restore fails validation, do not cut over.
- Do not run Django migrations as part of backup verification. The restored schema must come from the snapshot or dump being tested.
- Preserve Neon's automatically created old/backup branch and the prior deployment URL until the team confirms recovery.
- Clear temporary connection variables after every operation and never paste their values into logs or documentation.

## Current Neon references

- [Backup and restore](https://neon.com/docs/guides/backup-restore)
- [Instant restore](https://neon.com/docs/introduction/branch-restore)
- [History window](https://neon.com/docs/introduction/history-window)
- [Neon CLI snapshots](https://neon.com/docs/cli/snapshots)
- [Backups with pg_dump](https://neon.com/docs/manage/backup-pg-dump)
- [Connection pooling](https://neon.com/docs/connect/connection-pooling)
