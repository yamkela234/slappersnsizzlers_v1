# Deploying

## Vercel

Vercel detects `manage.py`, reads `WSGI_APPLICATION`, runs `collectstatic` and
serves `/static/` from its CDN. `pyproject.toml` points the build at
`vercel_build.py`, which runs `migrate` and `seed_menu`.

1. **Database.** In the Vercel project go to Storage and create a Postgres
   database (Neon), or paste a `DATABASE_URL` from any hosted Postgres into the
   project's environment variables.
2. **Environment variables** (Settings > Environment Variables):

   | Key | Value |
   |---|---|
   | `SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
   | `DATABASE_URL` | set automatically by the Neon integration; otherwise paste it |

   `DEBUG`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` default to production
   values on Vercel (`*.vercel.app`). Add your own domain to
   `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` if you attach one.
3. **Deploy.** Import the GitHub repo in the Vercel dashboard, or run
   `npx vercel` from the project folder.
4. **Admin user.** Vercel has no shell, so create the first superuser from
   your machine against the production database:

   ```bash
   DATABASE_URL="<the production url>" python manage.py createsuperuser
   ```

   (On Windows PowerShell: `$env:DATABASE_URL="<url>"; python manage.py createsuperuser`.)

Notes:

- The filesystem is read-only, so photo uploads through Django admin will not
  work there. The menu uses the bundled photos in `static/img/`
  (`MenuItem.static_image`). For real uploads add `django-storages` with S3 or
  Cloudinary as the default storage.
- Functions sleep when idle; the first request afterwards takes a few seconds.

## Render

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<you>/slappersnsizzlers.git
git push -u origin main
```

Make sure `.env` is not committed (`git ls-files | grep .env` should only show `.env.example`).

### 2. Create the services

Either point Render at the repo as a Blueprint (`render.yaml` describes the web service and the Postgres database), or create them manually:

- **PostgreSQL** – free plan, note the Internal Database URL.
- **Web service** – runtime Python, build command `./build.sh`, start command `gunicorn slappersnsizzlers_v1.wsgi:application`.

### 3. Environment variables

| Key | Value |
|---|---|
| `DATABASE_URL` | Internal Database URL from the Postgres service |
| `SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `your-service.onrender.com` (no scheme) |
| `CSRF_TRUSTED_ORIGINS` | `https://your-service.onrender.com` (with scheme) |
| `PYTHON_VERSION` | `3.12.0` |

### 4. Seed data

From the service's Shell tab:

```bash
python manage.py seed_menu
python manage.py createsuperuser
```

### Free-tier notes

- The filesystem is ephemeral: uploaded images in `media/` are lost on every deploy. Re-run `seed_menu` to restore the bundled photos, or move media to Cloudinary/S3 by swapping the `default` storage backend in `settings.py`.
- The free Postgres instance expires after 30 days. Back it up with `pg_dump` before then.
- Free web services sleep after ~15 minutes idle; the first request afterwards takes ~30 seconds.

### Troubleshooting

| Symptom | Fix |
|---|---|
| No CSS | Check the build log for `collectstatic`; WhiteNoise must sit right after `SecurityMiddleware` |
| 400 on every page | `ALLOWED_HOSTS` must match the Render hostname exactly, without `https://` |
| CSRF failures on every POST | `CSRF_TRUSTED_ORIGINS` must include the scheme |
| `Missing staticfiles manifest entry` | A `{% static %}` path points at a file that doesn't exist |
| Data gone after a deploy | `DATABASE_URL` is not set, so the app is using SQLite |
| `permission denied: ./build.sh` | `git update-index --chmod=+x build.sh` |
