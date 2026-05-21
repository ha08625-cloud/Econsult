# Deployment Checklist

This checklist covers everything required before starting the application for
the first time in a new environment. Complete every step in order. The
application will refuse to start with a clear error message if any step is
missed.

---

## 1. Provision the Database

- Postgres 15 or later must be running and reachable.
- Set `DATABASE_URL` in the environment (Railway injects this automatically).
- Run Alembic migrations to create the schema:

```
python -m alembic upgrade head
```

The application runs this automatically at startup, but running it manually
first lets you verify the database connection before proceeding.

---

## 2. Set Required Environment Variables

All variables marked **Required** must be set before the application starts.
Variables marked **Dev only** must not be set in production.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Required | Postgres connection string |
| `PRACTICE_ID` | Required | Unique identifier for the practice (e.g. `my-practice`) |
| `ALLOWED_ADMIN_DOMAINS` | Required | Comma-separated list of permitted admin email domains (e.g. `nhs.net,gov.uk`) |
| `EMAIL_FROM` | Required | Sender address for all outgoing emails |
| `MAILGUN_API_KEY` | Required* | Mailgun API key. Required unless using SMTP. |
| `MAILGUN_DOMAIN` | Required* | Mailgun sending domain. Required if `MAILGUN_API_KEY` is set. |
| `SMTP_HOST` | Required* | SMTP server hostname. Required unless using Mailgun. |
| `SMTP_USER` | Required* | SMTP username. Required if using SMTP. |
| `SMTP_PASSWORD` | Required* | SMTP password. Required if using SMTP. |
| `SMTP_PORT` | Optional | SMTP port. Defaults to 587. |
| `SMTP_TIMEOUT` | Optional | SMTP connection timeout in seconds. Defaults to 30. |
| `ADMIN_URL` | Required | Full URL of the admin portal (e.g. `https://my-practice.up.railway.app/admin`). Included in admin invitation emails. |

*Either Mailgun or SMTP must be fully configured. Both sets of variables need
not be present, but one complete set is required.

---

## 3. Insert the Practice Record

The practice record must exist before the application starts. This is a
one-time operation. Run it directly against the database using `psql` or
any Postgres client:

```sql
INSERT INTO practices (practice_id, name, email)
VALUES ('your-practice-id', 'Your Practice Name', 'submissions@your-practice.nhs.uk');
```

Replace the values with the correct practice identifier, display name, and
the email address where patient consultation submissions should be delivered.

Verify the row exists before proceeding:

```sql
SELECT practice_id, name, email FROM practices;
```

Exactly one row must be present. The application will abort on startup if
zero rows or more than one row exists.

---

## 4. Create the First Admin User

Run the management command once to insert the first admin user:

```
python scripts/create_admin_user.py admin@your-practice.nhs.uk
```

The command requires `DATABASE_URL`, `PRACTICE_ID`, and
`ALLOWED_ADMIN_DOMAINS` to be set in the environment. It will validate that
the email domain is in `ALLOWED_ADMIN_DOMAINS` and exit with a clear error
if not.

The command is idempotent. Running it again with the same email prints a
message and exits cleanly without creating a duplicate.

Additional admin users can be added the same way, or via the admin UI after
the system is running.

---

## 5. Remove Deprecated Environment Variables

The following variable was used in earlier versions of this system and must
be removed from the environment if present:

- `INITIAL_ADMIN_EMAIL` — no longer read by the application. Remove it from
  Railway environment variables to avoid confusion.

In Railway: go to your service, open the Variables tab, and delete
`INITIAL_ADMIN_EMAIL` if it exists.

---

## 6. Verify Startup

Run the following command to perform a dry-run startup check. It imports
`main.py`, which runs all startup validation, then exits:

```
python -c "from main import app; print('Startup OK')"
```

If any configuration is missing or the database is not correctly set up, this
will print a clear error message describing exactly what needs to be fixed.

Do not proceed until this command exits with `Startup OK`.

---

## 7. First Login

Once the application is running:

1. Navigate to `/admin` in a browser.
2. Enter the admin email address inserted in step 4.
3. Check the inbox for the MFA code email.
4. Enter the code to complete login.

If the MFA email does not arrive, verify the email delivery configuration
(`MAILGUN_API_KEY` / `MAILGUN_DOMAIN` / `EMAIL_FROM`) and check the
application logs for delivery errors.