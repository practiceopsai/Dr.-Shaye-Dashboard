# Production deployment

The GitHub workflow tests the backend, tests the frontend, and builds the frontend before uploading the repository to Railway. Both services use the same repository snapshot, with explicit Railway service roots. Do not combine these roots with `--path-as-root` or upload only a subfolder.

| Setting | Backend | Frontend |
|---|---|---|
| Root directory | `/backend` | `/frontend` |
| Builder | RAILPACK | RAILPACK |
| Build command | `pip install -r requirements.txt` | `npm ci && npm run build` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `npm start` |
| Health check | `/health` | `/` |
| Health timeout | 120 seconds | 120 seconds |
| Restart policy | ON_FAILURE | ON_FAILURE |
| Persistent mount | `/data` | None |

These settings are configured on the existing Railway services. There is no custom Railway config-file path. Legacy railway.toml files were removed; direct repository rebuilds and CLI uploads now resolve the same service roots.

Backend runtime settings: BACKGROUND_REFRESH_ENABLED=true, DASHBOARD_REFRESH_SECONDS=300, DASHBOARD_STATE_PATH=/data/eli-dashboard.sqlite3. Preserve existing authentication, account routing, origins, and secret values. LIVE_ACTIONS_ENABLED remains false.

The `/health` endpoint reports process health, release version, whether background refresh and persistent writeback are enabled, and the last refresh time/result. A healthy process does not prove provider availability; verify last_refresh_verified and authenticated `/api/status` as well. Do not expose private dashboard content to make deployment checks convenient.

Railway volumes can require deployment downtime. Wait for an in-progress release before starting another; a second release can replace a healthy volume-backed instance before its replacement is ready. For recovery, use the last successful image and preserve the `/data` volume. Never delete the volume to resolve a code or routing problem.

Reference: [Railway monorepo roots](https://docs.railway.com/deployments/monorepo), [build settings](https://docs.railway.com/builds/build-configuration), and [legacy config-file migration notice](https://docs.railway.com/config-as-code).
