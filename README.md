# trimble-worksmanager-notion-sync

Production Cloud Run Job that reads Trimble WorksManager / Site Management API
data (read-only) and upserts Projects, Devices, and Machines into three **existing**
Notion databases.

## Architecture

```
Trimble Site Management API (GET only)
        ↓
Cloud Run Job (this repo)
        ↓
Notion (existing WorksManager databases)
```

## Google Cloud

| Setting | Value |
|--------|--------|
| Project | `work-projects-486912` |
| Region | `us-west1` |
| Job | `trimble-worksmanager-notion-sync` |
| Version | `0.01.00` (see `VERSION`) |

## Safety

- Trimble: **read-only** (OAuth client credentials, scope `site-management`).
- Notion: upsert only; **no** database creation, deletes, or archives in v0.01.00.
- Secrets from Secret Manager / environment — never committed.
- Match keys: `Trimble Project ID`, `Trimble Device ID`, `Trimble Machine ID`.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | When true, no Notion writes |
| `GOOGLE_CLOUD_PROJECT` | `work-projects-486912` | GCP project for Secret Manager |
| `TRIMBLE_ACCOUNT_TRN` | (known account TRN) | Account filter |
| `TRIMBLE_CLIENT_ID` | — | Secret Manager `TRIMBLE_CLIENT_ID` |
| `TRIMBLE_CLIENT_SECRET` | — | Secret Manager `TRIMBLE_CLIENT_SECRET` |
| `NOTION_TOKEN` | — | Secret Manager `Notion_Google_Cloud_Sync` |

Notion database / data source IDs default to the three existing WorksManager
databases documented in the project brief.

## Local development

```powershell
python -m pip install -r requirements.txt
$env:DRY_RUN = "true"
python main.py
```

## Tests

```powershell
pytest -q
```

## Deploy (Cloud Run Job)

```powershell
gcloud run jobs deploy trimble-worksmanager-notion-sync `
  --project work-projects-486912 `
  --region us-west1 `
  --source . `
  --max-retries 0 `
  --task-timeout 1800 `
  --set-env-vars "DRY_RUN=false,GOOGLE_CLOUD_PROJECT=work-projects-486912" `
  --set-secrets "TRIMBLE_CLIENT_ID=TRIMBLE_CLIENT_ID:latest,TRIMBLE_CLIENT_SECRET=TRIMBLE_CLIENT_SECRET:latest,NOTION_TOKEN=Notion_Google_Cloud_Sync:latest"
```

Execute once:

```powershell
gcloud run jobs execute trimble-worksmanager-notion-sync `
  --project work-projects-486912 `
  --region us-west1 `
  --wait
```

## Cloud Scheduler (weekdays, Pacific)

| Job | Schedule | Cron |
|-----|----------|------|
| `trimble-worksmanager-notion-sync-0900` | 9:00 AM | `0 9 * * 1-5` |
| `trimble-worksmanager-notion-sync-1300` | 1:00 PM | `0 13 * * 1-5` |

Both invoke only `trimble-worksmanager-notion-sync` via Run API v2 `:run`.
Timezone: `America/Los_Angeles`. OAuth: `564809734796-compute@developer.gserviceaccount.com`.

Production: job `DRY_RUN=false`; both schedulers **ENABLED** (go-live approved 2026-10-02).

## CI

- GitHub Actions: `.github/workflows/deploy.yml` (pytest + Cloud Build)
- Cloud Build: `cloudbuild.yaml`
