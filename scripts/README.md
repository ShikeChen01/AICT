# AICT Deployment Scripts

## Local

**Start full dev environment (backend + frontend):**

```powershell
cd c:\Personal-Project\AICT\AICT
.\scripts\local\start.ps1
```

This starts:
- Backend at http://localhost:8000
- Frontend at http://localhost:3000

**Run backend only (uses Cloud SQL from .env.development):**

```powershell
.\scripts\local\run.ps1
```

**Run frontend only (requires backend running):**

```powershell
.\scripts\local\frontend.ps1
```

**Verify local stage (while backend is running):**

```powershell
.\scripts\local\verify.ps1
```

**Run migrations (Cloud SQL dev):**

```powershell
.\scripts\local\migrate.ps1
```

**Optional: use local Docker Postgres instead of Cloud SQL:**

```powershell
.\scripts\local\db.up.ps1          # start Postgres container
$env:DATABASE_URL = "postgresql+asyncpg://aict:aict@localhost:5432/aict"
.\scripts\local\migrate.ps1 -UseLocalDb
.\scripts\local\run.ps1             # still needs ENV=development for other keys
```

---

## Cloud (Cloud Run + Artifact Registry)

**1. Build and push image:**

```powershell
.\scripts\cloud\build.ps1
```

**2. Run migrations against Cloud SQL** (before first deploy or after schema changes):

```powershell
.\scripts\cloud\migrate.ps1
```

**3. Deploy to Cloud Run:**

```powershell
.\scripts\cloud\deploy.ps1
```

**4. Verify cloud stage:**

```powershell
.\scripts\cloud\verify.ps1
```

This checks:
- `GET /api/v1/health`
- `GET /internal/agent/health`
- Authenticated API smoke flow (`projects` -> `agents` -> create/update/delete task)

---

## Requirements

- **Local:** Python 3.11+, `.env.development` with DATABASE_URL and API keys
- **Cloud:** `gcloud` CLI, project with Cloud Run + Cloud SQL + Artifact Registry enabled
