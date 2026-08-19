"""Seed realistic Hermes session history into a profile's state.db.

Demo tooling. It writes sessions, messages (with real Hermes tool call and
result shapes), token counters and auxiliary usage rows through the same
SessionDB API the agent uses, and prices every session with Hermes' own
estimate_usage_cost, so spend figures are what a real session would have
recorded. Timestamps are then back-dated across the requested window.

Run it with the Hermes venv Python from the hermes-agent checkout so the
imports resolve, for example on Windows:

  %LOCALAPPDATA%\\hermes\\hermes-agent\\venv\\Scripts\\python.exe \\
      C:\\Developer\\Hermes\\ledgerline\\tools\\seed\\seed_history.py \\
      --profile homelab --preset homelab --days 35 --seed 7

Nothing here touches the default profile unless you point it there.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def find_hermes_root() -> Path:
    for candidate in [
        os.environ.get("HERMES_AGENT_ROOT"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "hermes-agent"),
        os.path.expanduser("~/.hermes/hermes-agent"),
    ]:
        if candidate and Path(candidate, "hermes_state.py").exists():
            return Path(candidate)
    raise SystemExit("hermes-agent checkout not found; set HERMES_AGENT_ROOT")


ROOT = find_hermes_root()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from hermes_state import SessionDB  # noqa: E402
from agent.usage_pricing import CanonicalUsage, estimate_usage_cost  # noqa: E402


# ---------------------------------------------------------------------------
# tool result shapes, as the real tools return them
# ---------------------------------------------------------------------------

def r_terminal(output: str, code: int = 0) -> str:
    return json.dumps({"output": output, "exit_code": code})


def r_terminal_fail(err: str, code: int = 1) -> str:
    return json.dumps({"output": "", "exit_code": code, "error": err})


def r_read(text: str) -> str:
    return text


def r_read_missing(path: str) -> str:
    return json.dumps({"error": f"File not found: {path}"})


def r_write(path: str, n: int) -> str:
    return json.dumps({"bytes_written": n, "path": path})


def r_patch_ok(path: str) -> str:
    return json.dumps({"success": True, "path": path, "hunks_applied": 1})


def r_patch_fail(path: str) -> str:
    return json.dumps({"success": False, "message": f"hunk 1 failed to apply cleanly to {path}"})


def r_search(hits: list[str]) -> str:
    return "\n".join(hits) if hits else "No matches."


def r_web(summary: str) -> str:
    return json.dumps({"results": [{"title": summary, "url": "https://docs.example.dev/" + summary.lower().replace(" ", "-")[:40]}]})


def r_delegate(results: list[dict]) -> str:
    return json.dumps({"results": results, "total_duration_seconds": sum(r.get("duration_seconds", 0) for r in results)})


# ---------------------------------------------------------------------------
# session templates: (title, first prompt, steps, final reply, size)
# steps: list of (tool, args, result_text, verdict) where verdict is only for
# our own bookkeeping; the result text is what decides how it reads.
# size: 's' | 'm' | 'l' | 'xl' drives token volumes.
# ---------------------------------------------------------------------------

REPO = "~/code/api-gateway"
REPO2 = "~/code/ledger-web"
INFRA = "~/infra/homelab"

TITLE_VARIANTS = {
 "Trim the container image size": ["Shrink the api-gateway image", "Get the Docker image under 400 MB", "Slim image for api-gateway"],
 "Add retries to the outbound webhook client": ["Webhook retries with backoff", "Make webhook delivery retry", "Backoff for outbound webhooks"],
 "Find out why the dev DB migration hangs": ["alembic upgrade hangs on dev", "Migration stuck on the dev database", "What is the migration waiting on"],
 "Rotate the API keys for the staging tenants": ["Staging tenant key rotation", "Rotate staging keys", "New API keys for staging"],
 "Write a smoke test for the release pipeline": ["Post-deploy smoke test", "Smoke job after deploy", "Fail the pipeline on a bad deploy"],
 "Reduce log noise from the scheduler": ["Scheduler logs are too loud", "Quiet the scheduler at INFO", "Cut scheduler log volume"],
 "Set up the new mini PC as a k3s worker": ["Join mini-01 to k3s", "New k3s worker for batch jobs", "Move ingest cronjobs to the mini PC"],
 "Answer the question about our retention policy": ["How long do we keep payloads", "Retention policy answer", "Ingest retention, one paragraph"],
 "Profile the slow test suite": ["Why do tests take 6 minutes", "Speed up the test suite", "Slowest tests in api-gateway"],
 "Check the SSL renewals across the homelab": ["Cert expiry check", "Which certs expire soon", "SSL renewals in the homelab"],'Migrate CI to uv and cache the venv': ['Move the CI workflow to uv', 'Cache the venv in GitHub Actions', 'uv in CI for api-gateway'], 'Debug flaky websocket reconnect': ['Websocket client never reconnects', 'Flaky reconnect after gateway restart', 'Fix ws reconnect guard'], 'Add rate limiting to /v1/ingest': ['Token bucket for the ingest route', 'Rate limit ingest per API key', '429s for noisy ingest clients'], 'Why is the nightly backup 3x slower': ['Restic backup got slow', 'Nightly backup takes 40 minutes now', 'Look at the restic timings'], 'Write the ledger-web onboarding doc': ['ONBOARDING.md for ledger-web', 'Onboarding notes for the ledger UI', 'Document how to run ledger-web'], 'Fix the failing Dockerfile build': ['docker build broken on main', 'Dockerfile fails since yesterday', 'Repair the uv lock in the image build'], 'Investigate 502s from the ingress': ['Burst of 502s at 14:10', 'Ingress 502s on /v1/ingest', 'Which upstream threw the 502s'], 'Refactor settings loading into one module': ['Centralise env reads in settings.py', 'One settings module with pydantic', 'Stop reading os.environ everywhere'], 'Set up Grafana alert for disk usage': ['Disk usage alert to Telegram', 'Grafana rule for root disk over 85%', 'Alert when a node runs out of disk'], "Summarise this week's PRs for the changelog": ['Changelog entries for this week', 'Draft the Unreleased changelog section', 'What merged this week'], 'Port the search endpoint to async and add tests in parallel': ['Async search endpoint plus tests, in parallel', 'Two subagents: async port and tests', 'Parallel work on /v1/search'], 'Clean up the photos share': ['Find duplicate photos by hash', 'Dedupe the phone photo syncs', 'How much of the photos share is duplicates'], 'Explain the auth middleware to me': ['How does API key auth work here', 'Walk me through auth.py', 'Where is the API key cache'], 'Upgrade Postgres 15 to 16 on the NAS': ['Postgres 16 upgrade on the NAS', 'pg_upgrade the homelab database', 'Move the NAS Postgres to 16'], 'Add dark mode to ledger-web': ['Dark theme toggle for ledger-web', 'Ledger UI dark mode', 'Remember the theme choice in ledger-web'], "What's on my calendar tomorrow": ["Tomorrow's agenda", 'Anything tomorrow morning', 'Calendar check'], 'Remind me about the car service': ['Reminder for Friday', 'Set a reminder', 'Ping me on Friday morning'], 'Translate this message to Hebrew': ['Translate to Hebrew', 'Hebrew translation for the courier', 'Quick translation'], 'Quick unit conversion': ['Gallons to liters', 'Convert units', 'How many liters'], 'Summarise the thread about the office move': ['Office move thread summary', 'Catch me up on the office move', 'What was decided about the move']}

TEMPLATES = [
    dict(
        title="Migrate CI to uv and cache the venv",
        prompt="Our GitHub Actions workflow still uses pip. Move it to uv, cache the venv between runs, and keep the matrix (3.11, 3.12).",
        steps=[
            ("read_file", {"path": f"{REPO}/.github/workflows/ci.yml"}, r_read("name: ci\non: [push, pull_request]\njobs:\n  test:\n    strategy:\n      matrix:\n        python: ['3.11', '3.12']\n    steps:\n      - uses: actions/checkout@v4\n      - run: pip install -r requirements.txt\n      - run: pytest -q\n")),
            ("search_files", {"workdir": REPO, "pattern": "requirements"}, r_search(["requirements.txt", "requirements-dev.txt", "Makefile:12: pip install -r requirements.txt"])),
            ("write_file", {"path": f"{REPO}/.github/workflows/ci.yml", "content": "..."}, r_write(f"{REPO}/.github/workflows/ci.yml", 1042)),
            ("terminal", {"command": "cd ~/code/api-gateway && uv lock && uv sync --frozen"}, r_terminal("Resolved 84 packages in 1.9s\nInstalled 84 packages in 3.4s")),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest -q"}, r_terminal("......................... 25 passed in 4.12s")),
        ],
        reply="Done. The workflow now installs with `uv sync --frozen`, caches `.venv` keyed on `uv.lock`, and keeps the 3.11/3.12 matrix. Local run: 25 passed.",
        size="m",
    ),
    dict(
        title="Debug flaky websocket reconnect",
        prompt="The websocket client sometimes never reconnects after the gateway restarts. Find out why and fix it.",
        steps=[
            ("search_files", {"workdir": REPO, "pattern": "reconnect"}, r_search(["src/ws/client.ts:88: scheduleReconnect()", "src/ws/client.ts:131: private reconnectTimer", "src/ws/client.test.ts:40: it('reconnects after close'"])),
            ("read_file", {"path": f"{REPO}/src/ws/client.ts"}, r_read("export class WsClient {\n  private reconnectTimer: any\n  ...\n  private scheduleReconnect() {\n    if (this.reconnectTimer) return\n    this.reconnectTimer = setTimeout(() => this.connect(), this.backoff())\n  }\n")),
            ("terminal", {"command": "cd ~/code/api-gateway && npx vitest run src/ws/client.test.ts"}, r_terminal_fail("FAIL src/ws/client.test.ts > reconnects after close\nAssertionError: expected 1 to be 2", 1)),
            ("patch", {"path": f"{REPO}/src/ws/client.ts", "patch": "@@ -131,7 +131,9 @@"}, r_patch_ok(f"{REPO}/src/ws/client.ts")),
            ("terminal", {"command": "cd ~/code/api-gateway && npx vitest run src/ws/client.test.ts"}, r_terminal("PASS src/ws/client.test.ts (3 tests) 412ms")),
        ],
        reply="Root cause: `reconnectTimer` was never cleared on a successful `open`, so the guard in `scheduleReconnect` returned early forever after the first reconnect. Cleared it in `onOpen`, added a regression test.",
        size="l",
    ),
    dict(
        title="Add rate limiting to /v1/ingest",
        prompt="Add a token bucket rate limiter to POST /v1/ingest, 100 req/min per API key, with a 429 and Retry-After header. Tests please.",
        steps=[
            ("read_file", {"path": f"{REPO}/src/routes/ingest.py"}, r_read("@router.post('/v1/ingest')\nasync def ingest(payload: IngestBody, key: ApiKey = Depends(api_key)):\n    ...")),
            ("write_file", {"path": f"{REPO}/src/middleware/ratelimit.py", "content": "..."}, r_write(f"{REPO}/src/middleware/ratelimit.py", 2210)),
            ("patch", {"path": f"{REPO}/src/routes/ingest.py", "patch": "@@ -1,4 +1,6 @@"}, r_patch_ok(f"{REPO}/src/routes/ingest.py")),
            ("write_file", {"path": f"{REPO}/tests/test_ratelimit.py", "content": "..."}, r_write(f"{REPO}/tests/test_ratelimit.py", 1480)),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest tests/test_ratelimit.py -q"}, r_terminal("....... 7 passed in 1.02s")),
        ],
        reply="Added `TokenBucket` middleware keyed by API key (100/min, burst 20), 429 with `Retry-After`. Seven tests cover refill, burst and header.",
        size="l",
    ),
    dict(
        title="Why is the nightly backup 3x slower",
        prompt="The nightly restic backup went from 12 minutes to 40. Look at the logs from the last week and tell me what changed.",
        steps=[
            ("terminal", {"command": "journalctl -u restic-backup --since '7 days ago' --no-pager | tail -n 200"}, r_terminal("Aug 12 03:00:01 nas restic[8812]: processed 182311 files, 412.1 GiB in 12:04\nAug 15 03:00:01 nas restic[9107]: processed 182390 files, 1.2 TiB in 39:51\n...")),
            ("terminal", {"command": "du -sh /srv/media/* | sort -h | tail -n 5"}, r_terminal("41G  /srv/media/photos\n96G  /srv/media/music\n812G /srv/media/video-raw")),
            ("read_file", {"path": f"{INFRA}/restic/excludes.txt"}, r_read("*.tmp\n.cache/\n")),
            ("patch", {"path": f"{INFRA}/restic/excludes.txt", "patch": "@@ -1,2 +1,3 @@\n+/srv/media/video-raw/"}, r_patch_ok(f"{INFRA}/restic/excludes.txt")),
        ],
        reply="On Aug 14 a new `video-raw` folder (812 GB of camera dumps) landed under `/srv/media`, which restic started scanning. Added it to the excludes; tonight's run should be back near 12 minutes. If you want it backed up, it belongs in a separate repo with a weekly schedule.",
        size="m",
    ),
    dict(
        title="Write the ledger-web onboarding doc",
        prompt="Write an ONBOARDING.md for ledger-web: how to run it, env vars, how tests work, and the release flow. Read the repo first.",
        steps=[
            ("search_files", {"workdir": REPO2, "pattern": "process.env"}, r_search(["src/config.ts:4: process.env.DATABASE_URL", "src/config.ts:5: process.env.SESSION_SECRET", "src/config.ts:9: process.env.SMTP_URL"])),
            ("read_file", {"path": f"{REPO2}/package.json"}, r_read('{"scripts": {"dev": "vite", "test": "vitest", "build": "vite build", "release": "changeset publish"}}')),
            ("read_file", {"path": f"{REPO2}/README.md"}, r_read("# ledger-web\nA small double-entry ledger UI.")),
            ("write_file", {"path": f"{REPO2}/ONBOARDING.md", "content": "..."}, r_write(f"{REPO2}/ONBOARDING.md", 3902)),
        ],
        reply="Wrote ONBOARDING.md: run with `pnpm dev`, three env vars (DATABASE_URL, SESSION_SECRET, SMTP_URL), vitest for tests, changesets for release. Linked it from the README.",
        size="m",
    ),
    dict(
        title="Fix the failing Dockerfile build",
        prompt="docker build fails on main since yesterday. Fix it.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && docker build -t api-gateway:dev . 2>&1 | tail -n 20"}, r_terminal_fail("ERROR: failed to solve: process \"/bin/sh -c uv sync --frozen\" did not complete successfully: exit code: 2\nerror: Failed to parse `uv.lock`", 1)),
            ("terminal", {"command": "cd ~/code/api-gateway && git log --oneline -5 -- uv.lock"}, r_terminal("9c1f0a2 chore: bump httpx\n7b21d9e chore: regenerate lock")),
            ("terminal", {"command": "cd ~/code/api-gateway && uv lock && git diff --stat"}, r_terminal(" uv.lock | 14 +++++++-------\n 1 file changed")),
            ("terminal", {"command": "cd ~/code/api-gateway && docker build -t api-gateway:dev . 2>&1 | tail -n 3"}, r_terminal("=> exporting to image\n=> => naming to docker.io/library/api-gateway:dev")),
        ],
        reply="`uv.lock` was hand-edited in 9c1f0a2 and lost its header. Regenerated it; the image builds again. Suggest a CI step that fails on `uv lock --check`.",
        size="s",
    ),
    dict(
        title="Investigate 502s from the ingress",
        prompt="We got a burst of 502s from the ingress around 14:10 today. Figure out which upstream and why.",
        steps=[
            ("terminal", {"command": "kubectl -n edge logs deploy/ingress --since=2h | grep ' 502 ' | awk '{print $7}' | sort | uniq -c | sort -rn | head"}, r_terminal("  412 /v1/ingest\n   38 /v1/search")),
            ("terminal", {"command": "kubectl -n api get pods -o wide | grep ingest"}, r_terminal("ingest-7d9f8-abc1  0/1  CrashLoopBackOff  6  2h\ningest-7d9f8-def2  1/1  Running  0  9d")),
            ("terminal", {"command": "kubectl -n api logs ingest-7d9f8-abc1 --previous | tail -n 30"}, r_terminal("sqlalchemy.exc.OperationalError: FATAL: too many connections for role \"ingest\"")),
            ("terminal", {"command": "kubectl -n api describe deploy ingest | grep -A2 -i pool"}, r_terminal("  DB_POOL_SIZE: 40\n  DB_POOL_OVERFLOW: 20")),
        ],
        reply="One ingest replica crash-looped after the pool bump to 40+20 pushed the role over its 100-connection limit when both replicas restarted together. Options: pool 25+10, or raise the role limit. I did not change anything yet.",
        size="m",
    ),
    dict(
        title="Refactor settings loading into one module",
        prompt="Settings are read from env in six different files. Centralise them in src/settings.py with pydantic and update the callers.",
        steps=[
            ("search_files", {"workdir": REPO, "pattern": "os.environ"}, r_search([f"src/db.py:11", f"src/cache.py:6", f"src/routes/ingest.py:22", f"src/routes/search.py:9", f"src/auth.py:14", f"src/main.py:31"])),
            ("write_file", {"path": f"{REPO}/src/settings.py", "content": "..."}, r_write(f"{REPO}/src/settings.py", 1611)),
            ("patch", {"path": f"{REPO}/src/db.py", "patch": "..."}, r_patch_ok(f"{REPO}/src/db.py")),
            ("patch", {"path": f"{REPO}/src/cache.py", "patch": "..."}, r_patch_ok(f"{REPO}/src/cache.py")),
            ("patch", {"path": f"{REPO}/src/routes/search.py", "patch": "..."}, r_patch_fail(f"{REPO}/src/routes/search.py")),
            ("read_file", {"path": f"{REPO}/src/routes/search.py"}, r_read("import os\nSEARCH_INDEX = os.environ.get('SEARCH_INDEX', 'main')\n...")),
            ("write_file", {"path": f"{REPO}/src/routes/search.py", "content": "..."}, r_write(f"{REPO}/src/routes/search.py", 2044)),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest -q"}, r_terminal("........................................ 40 passed in 6.8s")),
        ],
        reply="All six readers now import `settings` from `src/settings.py` (pydantic `BaseSettings`, validated at import). One patch did not apply cleanly on `search.py` so I rewrote that file. 40 tests pass.",
        size="l",
    ),
    dict(
        title="Set up Grafana alert for disk usage",
        prompt="Add a Grafana alert rule: fire when any node's root disk goes over 85% for 10 minutes, route it to the ops Telegram.",
        steps=[
            ("read_file", {"path": f"{INFRA}/grafana/alerts/nodes.yaml"}, r_read("groups:\n  - name: nodes\n    rules: []\n")),
            ("write_file", {"path": f"{INFRA}/grafana/alerts/nodes.yaml", "content": "..."}, r_write(f"{INFRA}/grafana/alerts/nodes.yaml", 866)),
            ("terminal", {"command": "cd ~/infra/homelab && ./scripts/grafana-provision.sh --check"}, r_terminal("alerts/nodes.yaml: ok (1 rule)")),
        ],
        reply="Rule `node_root_disk_high` added: `node_filesystem_avail_bytes{mountpoint=\"/\"}` under 15% for 10m, contact point `ops-telegram`. Provision check passes.",
        size="s",
    ),
    dict(
        title="Summarise this week's PRs for the changelog",
        prompt="Look at merged PRs from the last 7 days in api-gateway and draft CHANGELOG entries grouped by area.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && gh pr list --state merged --search 'merged:>=2026-08-10' --json number,title,labels --limit 50"}, r_terminal('[{"number":412,"title":"feat: token bucket on ingest"},{"number":415,"title":"fix: ws reconnect guard"},{"number":418,"title":"chore: uv in CI"}]')),
            ("read_file", {"path": f"{REPO}/CHANGELOG.md"}, r_read("# Changelog\n\n## Unreleased\n")),
            ("patch", {"path": f"{REPO}/CHANGELOG.md", "patch": "..."}, r_patch_ok(f"{REPO}/CHANGELOG.md")),
        ],
        reply="Drafted three entries under Unreleased: API (rate limiting on ingest), Reliability (ws reconnect fix), Tooling (uv in CI).",
        size="s",
    ),
    dict(
        title="Port the search endpoint to async and add tests in parallel",
        prompt="Two things at once: port /v1/search to async SQLAlchemy, and write integration tests for it. Use subagents.",
        steps=[
            ("delegate_task", {"tasks": [{"goal": "Port src/routes/search.py to async SQLAlchemy 2.0 with the existing session factory"}, {"goal": "Write integration tests for /v1/search covering pagination and empty results"}]},
             r_delegate([
                 {"task_index": 0, "status": "completed", "summary": "search.py now uses AsyncSession; query builder unchanged; 3 callers updated.", "api_calls": 9, "duration_seconds": 141.2, "model": "claude-sonnet-5", "exit_reason": "completed", "truncated": False, "tokens": {"input": 48211, "output": 2210}, "cost_usd": 0.1779, "cost_status": "estimated"},
                 {"task_index": 1, "status": "completed", "summary": "Added tests/test_search_api.py with 6 tests; all pass against the sqlite fixture.", "api_calls": 6, "duration_seconds": 97.5, "model": "claude-sonnet-5", "exit_reason": "completed", "truncated": False, "tokens": {"input": 30140, "output": 1730}, "cost_usd": 0.1164, "cost_status": "estimated"},
             ])),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest tests/test_search_api.py -q"}, r_terminal("...... 6 passed in 2.31s")),
        ],
        reply="Both children finished. The async port is in, six integration tests pass. Total delegated cost about $0.29.",
        size="xl",
        children=2,
    ),
    dict(
        title="Clean up the photos share",
        prompt="There are duplicate photos in /srv/media/photos from three phone syncs. Find dupes by hash and list them, don't delete anything.",
        steps=[
            ("terminal", {"command": "find /srv/media/photos -type f \\( -iname '*.jpg' -o -iname '*.heic' \\) | wc -l"}, r_terminal("48213")),
            ("write_file", {"path": "~/scripts/find_dupes.py", "content": "..."}, r_write("~/scripts/find_dupes.py", 1288)),
            ("terminal", {"command": "python3 ~/scripts/find_dupes.py /srv/media/photos --report ~/dupes.txt"}, r_terminal("hashed 48213 files in 6m12s\n3111 duplicate groups, 4.9 GiB reclaimable\nreport: ~/dupes.txt")),
        ],
        reply="3,111 duplicate groups, 4.9 GiB. The report is at `~/dupes.txt`, grouped by hash with the oldest copy first. Nothing deleted.",
        size="m",
    ),
    dict(
        title="Explain the auth middleware to me",
        prompt="Walk me through how src/auth.py verifies API keys and where the cache is.",
        steps=[
            ("read_file", {"path": f"{REPO}/src/auth.py"}, r_read("async def api_key(request):\n    raw = request.headers.get('x-api-key')\n    ...\n    return await _lookup(raw)\n")),
            ("read_file", {"path": f"{REPO}/src/cache.py"}, r_read("_keys = TTLCache(maxsize=10_000, ttl=300)\n")),
        ],
        reply="Keys arrive in `x-api-key`, get hashed with the pepper from settings, and hit a 5-minute TTL cache before the DB. Revocations take up to 5 minutes to land, which is the trade-off to know about.",
        size="s",
    ),
    dict(
        title="Upgrade Postgres 15 to 16 on the NAS",
        prompt="Plan and run the Postgres 15 to 16 upgrade for the homelab container. Back up first, verify after.",
        steps=[
            ("terminal", {"command": "docker exec pg pg_dumpall -U postgres > ~/backups/pg-$(date +%F).sql && ls -la ~/backups | tail -n 2"}, r_terminal("-rw-r--r-- 1 admin admin 2.1G Aug 16 22:14 pg-2026-08-16.sql")),
            ("read_file", {"path": f"{INFRA}/compose/postgres.yml"}, r_read("services:\n  pg:\n    image: postgres:15\n    volumes:\n      - pgdata:/var/lib/postgresql/data\n")),
            ("patch", {"path": f"{INFRA}/compose/postgres.yml", "patch": "-    image: postgres:15\n+    image: postgres:16"}, r_patch_ok(f"{INFRA}/compose/postgres.yml")),
            ("terminal", {"command": "cd ~/infra/homelab && docker compose -f compose/postgres.yml up -d && sleep 8 && docker exec pg psql -U postgres -c 'select version()'"}, r_terminal_fail("FATAL: database files are incompatible with server\nDETAIL: The data directory was initialized by PostgreSQL version 15, which is not compatible with this version 16.", 1)),
            ("terminal", {"command": "cd ~/infra/homelab && docker compose -f compose/postgres.yml down && docker run --rm -v pgdata:/var/lib/postgresql/15/data -v pgdata16:/var/lib/postgresql/16/data tianon/postgres-upgrade:15-to-16"}, r_terminal("Upgrade Complete\n----------------")),
            ("patch", {"path": f"{INFRA}/compose/postgres.yml", "patch": "-      - pgdata:/var/lib/postgresql/data\n+      - pgdata16:/var/lib/postgresql/data"}, r_patch_ok(f"{INFRA}/compose/postgres.yml")),
            ("terminal", {"command": "cd ~/infra/homelab && docker compose -f compose/postgres.yml up -d && sleep 8 && docker exec pg psql -U postgres -c 'select version()'"}, r_terminal("PostgreSQL 16.4 on x86_64-pc-linux-gnu")),
        ],
        reply="Upgraded. The in-place start failed as expected (data dir was 15), so I ran `pg_upgrade` into a new volume and switched the compose file to it. Dump is at `~/backups/pg-2026-08-16.sql`. Old volume `pgdata` is kept for a week.",
        size="l",
    ),
    dict(
        title="Add dark mode to ledger-web",
        prompt="Add a dark theme to ledger-web with a toggle in the header, remembered in localStorage.",
        steps=[
            ("read_file", {"path": f"{REPO2}/src/styles/tokens.css"}, r_read(":root { --bg: #fff; --fg: #111; --accent: #2563eb; }")),
            ("write_file", {"path": f"{REPO2}/src/styles/tokens.css", "content": "..."}, r_write(f"{REPO2}/src/styles/tokens.css", 940)),
            ("write_file", {"path": f"{REPO2}/src/components/ThemeToggle.tsx", "content": "..."}, r_write(f"{REPO2}/src/components/ThemeToggle.tsx", 1120)),
            ("patch", {"path": f"{REPO2}/src/components/Header.tsx", "patch": "..."}, r_patch_ok(f"{REPO2}/src/components/Header.tsx")),
            ("terminal", {"command": "cd ~/code/ledger-web && pnpm vitest run"}, r_terminal("Test Files  9 passed (9)\nTests  41 passed (41)")),
        ],
        reply="Dark theme via `[data-theme=dark]` tokens, a toggle in the header, and the choice kept in localStorage with a system-preference default.",
        size="m",
    ),

    dict(
        title="Trim the container image size",
        prompt="The api-gateway image is 1.4 GB. Get it under 400 MB without breaking the build.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && docker image ls api-gateway:dev --format '{{.Size}}'"}, r_terminal("1.42GB")),
            ("read_file", {"path": f"{REPO}/Dockerfile"}, r_read("FROM python:3.12\nCOPY . /app\nRUN pip install uv && uv sync\nCMD [\"uv\", \"run\", \"api\"]")),
            ("write_file", {"path": f"{REPO}/Dockerfile", "content": "..."}, r_write(f"{REPO}/Dockerfile", 612)),
            ("write_file", {"path": f"{REPO}/.dockerignore", "content": "..."}, r_write(f"{REPO}/.dockerignore", 88)),
            ("terminal", {"command": "cd ~/code/api-gateway && docker build -q -t api-gateway:dev . && docker image ls api-gateway:dev --format '{{.Size}}'"}, r_terminal("362MB")),
        ],
        reply="Two-stage build on `python:3.12-slim`, `.dockerignore` for `.git`, `tests` and the local venv, and `uv sync --no-dev`. 1.42 GB down to 362 MB, tests still pass in the container.",
        size="m",
    ),
    dict(
        title="Add retries to the outbound webhook client",
        prompt="Outbound webhooks fail on the first blip. Add exponential backoff with jitter, max 5 tries, and log each retry.",
        steps=[
            ("read_file", {"path": f"{REPO}/src/webhooks/client.py"}, r_read("async def deliver(url, payload):\n    async with httpx.AsyncClient() as c:\n        return await c.post(url, json=payload)")),
            ("write_file", {"path": f"{REPO}/src/webhooks/client.py", "content": "..."}, r_write(f"{REPO}/src/webhooks/client.py", 1732)),
            ("write_file", {"path": f"{REPO}/tests/test_webhook_retry.py", "content": "..."}, r_write(f"{REPO}/tests/test_webhook_retry.py", 1210)),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest tests/test_webhook_retry.py -q"}, r_terminal(".... 4 passed in 0.88s")),
        ],
        reply="Backoff 0.5s, 1s, 2s, 4s, 8s with 20% jitter, five attempts, a warning log per retry with the attempt number and status. Four tests.",
        size="m",
    ),
    dict(
        title="Find out why the dev DB migration hangs",
        prompt="`alembic upgrade head` hangs on the dev database. Figure out what it's waiting on.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && timeout 20 uv run alembic upgrade head; echo exit=$?"}, r_terminal("INFO  [alembic.runtime.migration] Running upgrade 3f1a -> 4b02, add index on events(ts)\nexit=124")),
            ("terminal", {"command": "psql $DATABASE_URL -c \"select pid, state, wait_event_type, left(query,60) from pg_stat_activity where datname='gateway_dev'\""}, r_terminal(" 8812 | idle in transaction | Client | BEGIN; select * from events where ...\n 9107 | active | Lock | CREATE INDEX events_ts_idx ON events (ts)")),
            ("terminal", {"command": "psql $DATABASE_URL -c 'select pg_terminate_backend(8812)'"}, r_terminal(" t")),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run alembic upgrade head"}, r_terminal("INFO  [alembic.runtime.migration] Running upgrade 3f1a -> 4b02, add index on events(ts)\nDone.")),
        ],
        reply="A forgotten `psql` shell had an open transaction holding a share lock on `events`, so `CREATE INDEX` waited forever. Killed pid 8812, migration went through. Consider `CREATE INDEX CONCURRENTLY` in that migration.",
        size="m",
    ),
    dict(
        title="Rotate the API keys for the staging tenants",
        prompt="Rotate API keys for the three staging tenants, update the secrets in the cluster, and confirm the old keys stop working.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && uv run python -m tools.keys rotate --tenant acme-stg --tenant beta-stg --tenant gamma-stg"}, r_terminal("acme-stg: new key ak_live_9f...c2\nbeta-stg: new key ak_live_1a...77\ngamma-stg: new key ak_live_e0...b9")),
            ("terminal", {"command": "kubectl -n api create secret generic tenant-keys --from-file=keys.json --dry-run=client -o yaml | kubectl apply -f -"}, r_terminal("secret/tenant-keys configured")),
            ("terminal", {"command": "kubectl -n api rollout restart deploy/api && kubectl -n api rollout status deploy/api"}, r_terminal("deployment \"api\" successfully rolled out")),
            ("terminal", {"command": "curl -s -o /dev/null -w '%{http_code}' -H 'x-api-key: ak_live_OLD' https://staging.api.internal/v1/health"}, r_terminal("401")),
        ],
        reply="Rotated all three, secret updated, deployment restarted, old key returns 401. New keys are in the vault under `staging/tenants`.",
        size="s",
    ),
    dict(
        title="Write a smoke test for the release pipeline",
        prompt="Add a smoke test job that runs after deploy: hit /health, /v1/search with a known query, and one authenticated ingest. Fail the pipeline if any of them fail.",
        steps=[
            ("read_file", {"path": f"{REPO}/.github/workflows/deploy.yml"}, r_read("jobs:\n  deploy:\n    steps:\n      - run: ./scripts/deploy.sh")),
            ("write_file", {"path": f"{REPO}/scripts/smoke.sh", "content": "..."}, r_write(f"{REPO}/scripts/smoke.sh", 944)),
            ("patch", {"path": f"{REPO}/.github/workflows/deploy.yml", "patch": "..."}, r_patch_ok(f"{REPO}/.github/workflows/deploy.yml")),
            ("terminal", {"command": "cd ~/code/api-gateway && SMOKE_BASE=https://staging.api.internal ./scripts/smoke.sh"}, r_terminal("health ok\nsearch ok (12 hits)\ningest ok (202)")),
        ],
        reply="`scripts/smoke.sh` runs the three checks with a 10 s timeout each and exits non-zero on the first failure. Wired into `deploy.yml` as a `smoke` job that needs `deploy`.",
        size="s",
    ),
    dict(
        title="Reduce log noise from the scheduler",
        prompt="The scheduler logs about 4k lines a minute at INFO. Cut it to what matters and keep debug behind a flag.",
        steps=[
            ("search_files", {"workdir": REPO, "pattern": "logger.info"}, r_search([f"src/scheduler/loop.py:44", f"src/scheduler/loop.py:61", f"src/scheduler/loop.py:78", f"src/scheduler/claims.py:19"])),
            ("patch", {"path": f"{REPO}/src/scheduler/loop.py", "patch": "..."}, r_patch_ok(f"{REPO}/src/scheduler/loop.py")),
            ("patch", {"path": f"{REPO}/src/scheduler/claims.py", "patch": "..."}, r_patch_ok(f"{REPO}/src/scheduler/claims.py")),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run python -m src.scheduler --once 2>&1 | wc -l"}, r_terminal("37")),
        ],
        reply="Per-tick and per-claim lines moved to DEBUG, one INFO summary per tick (claimed, ran, failed). One dry run: 37 lines instead of about 4,000.",
        size="s",
    ),
    dict(
        title="Set up the new mini PC as a k3s worker",
        prompt="Join the new mini PC (10.0.0.24) to the k3s cluster as a worker, label it for batch jobs, and move the ingest cronjobs there.",
        steps=[
            ("terminal", {"command": "ssh admin@10.0.0.24 'curl -sfL https://get.k3s.io | K3S_URL=https://10.0.0.10:6443 K3S_TOKEN=$(cat ~/.k3s-token) sh -'"}, r_terminal("[INFO]  systemd: Starting k3s-agent")),
            ("terminal", {"command": "kubectl get nodes"}, r_terminal("NAME     STATUS   ROLES                  AGE\nnas      Ready    control-plane,master   212d\nmini-01  Ready    <none>                 41s")),
            ("terminal", {"command": "kubectl label node mini-01 workload=batch"}, r_terminal("node/mini-01 labeled")),
            ("patch", {"path": f"{INFRA}/k8s/cronjobs/ingest.yaml", "patch": "+      nodeSelector:\n+        workload: batch"}, r_patch_ok(f"{INFRA}/k8s/cronjobs/ingest.yaml")),
            ("terminal", {"command": "kubectl apply -f ~/infra/homelab/k8s/cronjobs/ingest.yaml"}, r_terminal("cronjob.batch/ingest configured")),
        ],
        reply="mini-01 joined and is Ready, labelled `workload=batch`, and the ingest cronjobs now pin to it. The control plane on the NAS is back to running just the API pods.",
        size="m",
    ),
    dict(
        title="Answer the question about our retention policy",
        prompt="Someone asked how long we keep ingest payloads. Check the code and the docs and give me a one-paragraph answer I can paste.",
        steps=[
            ("search_files", {"workdir": REPO, "pattern": "retention"}, r_search([f"src/settings.py:31: RETENTION_DAYS = 30", f"docs/data.md:14: Payloads are kept for 30 days"])),
            ("read_file", {"path": f"{REPO}/src/jobs/prune.py"}, r_read("def prune():\n    cutoff = now() - timedelta(days=settings.RETENTION_DAYS)\n    ...")),
        ],
        reply="Ingest payloads are kept for 30 days (`RETENTION_DAYS`), pruned nightly by the `prune` job; metadata rows stay for a year. Both are documented in `docs/data.md`.",
        size="s",
    ),
    dict(
        title="Profile the slow test suite",
        prompt="The test suite takes 6 minutes. Find the slowest tests and speed up the worst offenders.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest --durations=10 -q 2>&1 | tail -n 14"}, r_terminal("41.2s tests/test_search_api.py::test_large_page\n38.9s tests/test_ingest.py::test_bulk\n12.1s tests/test_ratelimit.py::test_refill\n... 6m01s")),
            ("read_file", {"path": f"{REPO}/tests/test_search_api.py"}, r_read("def test_large_page(client):\n    for i in range(5000):\n        client.post('/v1/ingest', json=row(i))\n    ...")),
            ("patch", {"path": f"{REPO}/tests/test_search_api.py", "patch": "..."}, r_patch_ok(f"{REPO}/tests/test_search_api.py")),
            ("patch", {"path": f"{REPO}/tests/test_ingest.py", "patch": "..."}, r_patch_ok(f"{REPO}/tests/test_ingest.py")),
            ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest -q 2>&1 | tail -n 1"}, r_terminal("58 passed in 1m48s")),
        ],
        reply="Two tests were inserting 5,000 rows through the HTTP client. They now seed through the session fixture directly. Suite: 6m01s to 1m48s.",
        size="l",
    ),
    dict(
        title="Check the SSL renewals across the homelab",
        prompt="List every cert we serve and how many days each has left. Flag anything under 14 days.",
        steps=[
            ("terminal", {"command": "for h in api.internal grafana.internal nas.internal git.internal; do echo -n \"$h \"; echo | openssl s_client -connect $h:443 -servername $h 2>/dev/null | openssl x509 -noout -enddate; done"}, r_terminal("api.internal notAfter=Oct 21 09:12:00 2026 GMT\ngrafana.internal notAfter=Aug 27 03:00:00 2026 GMT\nnas.internal notAfter=Nov 02 11:40:00 2026 GMT\ngit.internal notAfter=Aug 25 15:12:00 2026 GMT")),
        ],
        reply="grafana.internal (8 days) and git.internal (6 days) are under 14 days. Both are on the caddy host; its renew timer is disabled since the Aug 2 reboot. Re-enable with `systemctl enable --now caddy-renew.timer`.",
        size="s",
    ),
    dict(
        title="Nightly repo health check",
        prompt="Check api-gateway and ledger-web: are there failing CI runs on main, open Dependabot PRs older than 7 days, or branches merged but not deleted? Reply with a short list, or [SILENT] if all clear.",
        steps=[
            ("terminal", {"command": "cd ~/code/api-gateway && gh run list --branch main --limit 3 --json conclusion,name"}, r_terminal('[{"conclusion":"success","name":"ci"},{"conclusion":"success","name":"ci"}]')),
            ("terminal", {"command": "cd ~/code/api-gateway && gh pr list --author app/dependabot --json number,createdAt"}, r_terminal('[{"number":419,"createdAt":"2026-08-05T06:11:00Z"}]')),
        ],
        reply="api-gateway: CI green. Dependabot #419 (httpx 0.28) is 11 days old. ledger-web: all clear.",
        size="s",
        source="cron",
    ),
]

BOT_TEMPLATES = [
    dict(
        title="What's on my calendar tomorrow",
        prompt="what do I have tomorrow",
        steps=[("terminal", {"command": "gcalcli agenda tomorrow --nocolor"}, r_terminal("Wed Aug 13\n  09:30  Standup\n  14:00  Dentist\n  17:00  Call with Sam"))],
        reply="Tomorrow: standup 09:30, dentist 14:00, call with Sam 17:00.",
        size="s",
        source="telegram",
    ),
    dict(
        title="Remind me about the car service",
        prompt="remind me friday 9am to book the car service",
        steps=[("terminal", {"command": "hermes cron create '2026-08-15 09:00' 'Remind: book the car service' --deliver telegram"}, r_terminal("Created job car-service (id 88120031)"))],
        reply="Set for Friday 09:00. I will ping you here.",
        size="s",
        source="telegram",
    ),
    dict(
        title="Weekly digest for #ops",
        prompt="Write the weekly ops digest: uptime, alerts fired, backups. Keep it under 150 words.",
        steps=[
            ("terminal", {"command": "curl -s http://uptime.local/api/summary?days=7"}, r_terminal('{"uptime":"99.96%","incidents":1,"alerts":4}')),
            ("terminal", {"command": "journalctl -u restic-backup --since '7 days ago' | grep -c 'snapshot saved'"}, r_terminal("7")),
        ],
        reply="Uptime 99.96% (one 12-minute blip on Tuesday, ingress restart). 4 alerts fired, 3 auto-resolved, 1 was the disk alert on nas which is now excluded. Backups: 7 of 7 snapshots saved.",
        size="s",
        source="cron",
    ),
    dict(
        title="Translate this message to Hebrew",
        prompt="translate to hebrew: the package will arrive between 10 and 12, please leave it with the neighbour",
        steps=[],
        reply="החבילה תגיע בין 10 ל-12, בבקשה להשאיר אצל השכן.",
        size="s",
        source="telegram",
    ),
    dict(
        title="Quick unit conversion",
        prompt="how many liters is 3.5 gallons",
        steps=[],
        reply="3.5 US gallons is about 13.2 liters.",
        size="s",
        source="telegram",
    ),
    dict(
        title="Summarise the thread about the office move",
        prompt="summarise the last 30 messages in #general about the office move",
        steps=[("terminal", {"command": "hermes send --list --json"}, r_terminal('{"platforms":{"telegram":[{"id":"-1001","name":"ops"}]}}'))],
        reply="Move is set for Sept 8. Two open questions: parking passes (Dana owns it) and whether the standing desks come along (no decision yet).",
        size="s",
        source="telegram",
    ),
]

# Token volumes by size class: first-turn context on top of the system
# prompt, growth per API call (tool results and replies), output per call,
# and how many API calls the session runs. Calibrated on real Hermes sessions
# on this machine: the system prompt plus tool schemas is about 27k tokens,
# a small tool result adds 2-3k, a medium task runs 5-15 calls and a long
# investigation 20-40. Total prompt volume per session is calls x context,
# which is what the bill is made of.
SIZES = {
    "s": dict(first=(300, 2_500), grow=(1_500, 4_500), output=(150, 600), calls=(2, 6)),
    "m": dict(first=(800, 4_000), grow=(2_500, 8_000), output=(300, 1_200), calls=(8, 22)),
    "l": dict(first=(1_500, 6_000), grow=(3_000, 10_000), output=(500, 2_000), calls=(20, 55)),
    "xl": dict(first=(2_000, 8_000), grow=(3_500, 12_000), output=(500, 1_800), calls=(40, 90)),
}
# System prompt plus tool schemas, the part every call shares (measured:
# 27,2xx tokens on the first call of a fresh session here).
SYSTEM_CTX = (25_500, 29_000)

# Extra tool steps to pad a session out to its call count. Real agents read,
# search and run things far more often than the handful of steps a template
# spells out. Picked per working directory so the paths stay coherent.
FILLERS = {
    REPO: [
        ("read_file", {"path": f"{REPO}/src/main.py"}, "from fastapi import FastAPI\nfrom .settings import settings\napp = FastAPI()\n"),
        ("read_file", {"path": f"{REPO}/pyproject.toml"}, "[project]\nname = \"api-gateway\"\nversion = \"0.9.3\"\n"),
        ("search_files", {"workdir": REPO, "pattern": "def test_"}, "tests/test_ingest.py:12\ntests/test_search.py:9\ntests/test_auth.py:15"),
        ("terminal", {"command": "cd ~/code/api-gateway && git status --short"}, " M src/routes/ingest.py\n?? tests/test_ratelimit.py"),
        ("terminal", {"command": "cd ~/code/api-gateway && uv run pytest -q tests/test_auth.py"}, "........ 8 passed in 1.02s"),
        ("terminal", {"command": "cd ~/code/api-gateway && git log --oneline -5"}, "a41c9d2 ingest: token bucket\n9f0e1b7 settings module\n77ac2e0 ci: uv\n2b1d0f4 auth cache ttl\n0c9a8e1 initial"),
        ("read_file", {"path": f"{REPO}/src/routes/search.py"}, "@router.get('/v1/search')\nasync def search(q: str, limit: int = 20):\n    ...\n"),
        ("search_files", {"workdir": REPO, "pattern": "TODO"}, "src/db.py:40: # TODO pool size\nsrc/routes/ingest.py:88: # TODO batch"),
        ("terminal", {"command": "cd ~/code/api-gateway && uv run ruff check src"}, "All checks passed!"),
        ("read_file", {"path": f"{REPO}/tests/conftest.py"}, "import pytest\n@pytest.fixture\ndef client():\n    ...\n"),
    ],
    REPO2: [
        ("read_file", {"path": f"{REPO2}/package.json"}, '{"name": "ledger-web", "scripts": {"dev": "vite", "test": "vitest run"}}'),
        ("terminal", {"command": "cd ~/code/ledger-web && npm test -- --run"}, "Test Files  6 passed (6)\nTests  41 passed (41)"),
        ("search_files", {"workdir": REPO2, "pattern": "useTheme"}, "src/theme.ts:4\nsrc/App.tsx:11\nsrc/components/Nav.tsx:7"),
        ("read_file", {"path": f"{REPO2}/src/App.tsx"}, "export function App() {\n  return <Router />\n}\n"),
        ("terminal", {"command": "cd ~/code/ledger-web && git status --short"}, " M src/theme.ts"),
        ("terminal", {"command": "cd ~/code/ledger-web && npx tsc --noEmit"}, ""),
        ("read_file", {"path": f"{REPO2}/vite.config.ts"}, "export default defineConfig({ plugins: [react()] })\n"),
        ("search_files", {"workdir": REPO2, "pattern": "localStorage"}, "src/theme.ts:18\nsrc/store.ts:5"),
    ],
    INFRA: [
        ("terminal", {"command": "ssh nas 'df -h /srv'"}, "/dev/md0  7.3T  5.9T  1.4T  81% /srv"),
        ("read_file", {"path": f"{INFRA}/docker-compose.yml"}, "services:\n  grafana:\n    image: grafana/grafana:11\n  postgres:\n    image: postgres:16\n"),
        ("terminal", {"command": "ssh nas 'docker ps --format \"{{.Names}} {{.Status}}\"'"}, "grafana Up 9 days\npostgres Up 9 days\nrestic-cron Up 9 days"),
        ("terminal", {"command": "ssh nas 'journalctl -u restic-backup -n 20 --no-pager'"}, "Aug 18 03:00:02 nas restic[411]: Files: 1204 new, 88 changed\nAug 18 03:41:10 nas restic[411]: snapshot 3f9a1c saved"),
        ("search_files", {"workdir": INFRA, "pattern": "alert"}, "grafana/alerts/disk.yml:3\ngrafana/alerts/certs.yml:2"),
        ("read_file", {"path": f"{INFRA}/README.md"}, "# homelab\nnas, pi-hole, grafana, restic to b2\n"),
        ("terminal", {"command": "ssh nas 'uptime'"}, " 10:22:41 up 41 days,  3 users,  load average: 0.31, 0.28, 0.24"),
        ("terminal", {"command": "cd ~/infra/homelab && git status --short"}, " M grafana/alerts/disk.yml"),
    ],
}

IMPLICIT_CACHE_PROVIDERS = {"google", "gemini", "openrouter", "deepseek", "openai", "custom"}


def call_tokens(rng, provider, k, prev_ctx, ctx, sys_ctx):
    """Split one API call's prompt into (input, cache_read, cache_write).

    Anthropic: Hermes marks the system prompt and the last two messages, so
    everything before this call's new content is a cache read and the new
    content is a cache write. Only a few tokens after the last marker bill as
    plain input. The first call writes the whole context unless another
    session warmed the system prefix in the last few minutes.
    Implicit-cache providers (Gemini, OpenRouter routes, local servers that
    report it): reads on the shared prefix, no write side, and a miss now and
    then. Everything else: plain input.
    """
    if provider == "anthropic":
        if k == 1:
            if rng.random() < 0.3:
                read = int(sys_ctx * rng.uniform(0.9, 1.0))
                return rng.randint(20, 300), read, ctx - read
            return rng.randint(20, 300), 0, ctx
        if rng.random() < 0.03:  # cache expired mid-session
            read = int(sys_ctx * rng.uniform(0.9, 1.0))
            return rng.randint(20, 300), read, ctx - read
        read = int(prev_ctx * rng.uniform(0.97, 1.0))
        inp = rng.randint(20, 400)
        return inp, read, max(0, ctx - read - inp)
    if provider in IMPLICIT_CACHE_PROVIDERS:
        if k == 1 or rng.random() < 0.15:
            return ctx, 0, 0
        read = int(prev_ctx * rng.uniform(0.6, 0.97))
        return ctx - read, read, 0
    return ctx, 0, 0

PRESETS = {
    "homelab": dict(
        templates=TEMPLATES,
        main_model=("claude-sonnet-5", "anthropic", ""),
        heavy_model=("claude-opus-4-8", "anthropic", ""),
        local_model=("qwen3-coder-30b", "custom", "http://127.0.0.1:8080/v1"),
        aux_model=("gemini-3.5-flash", "google", ""),
        sessions_per_day=(1, 4),
        sources=("desktop", "desktop", "desktop", "cli"),
        cron_titles=["Nightly repo health check"],
    ),
    "bots": dict(
        templates=BOT_TEMPLATES,
        main_model=("gemini-3.5-flash", "google", ""),
        heavy_model=("gemini-3.1-pro", "google", ""),
        local_model=None,
        aux_model=("gemini-3.5-flash", "google", ""),
        sessions_per_day=(0, 4),
        sources=("telegram", "telegram", "telegram", "desktop"),
        cron_titles=["Weekly digest for #ops"],
    ),
}


def price(model: str, provider: str, base_url: str, usage: CanonicalUsage):
    result = estimate_usage_cost(model, usage, provider=provider or None, base_url=base_url or None)
    amount = float(result.amount_usd) if result.amount_usd is not None else 0.0
    return amount, result.status, result.source, result.pricing_version


def session_id_for(dt: datetime, rng: random.Random) -> str:
    return dt.strftime("%Y%m%d_%H%M%S_") + "".join(rng.choice("0123456789abcdef") for _ in range(6))


def seed(profile_dir: Path, preset: dict, days: int, rng: random.Random, profile_name: str, now: datetime) -> None:
    db_path = profile_dir / "state.db"
    db = SessionDB(db_path=db_path)
    made = 0
    start = now - timedelta(days=days)
    for day in range(days + 1):
        date = start + timedelta(days=day)
        weekday = date.weekday() < 5
        lo, hi = preset["sessions_per_day"]
        count = rng.randint(lo, hi) if weekday else rng.randint(0, max(1, hi - 2))
        if date.date() == now.date():
            count = min(count, 1)
        # cron jobs run daily/weekly regardless
        cron_today = [t for t in preset["templates"] if t.get("source") == "cron" and (t["title"].startswith("Nightly") or date.weekday() == 0)]
        picks = [rng.choice([t for t in preset["templates"] if t.get("source") != "cron"]) for _ in range(count)] + cron_today
        for template in picks:
            hour = 3 if template.get("source") == "cron" else rng.choice([9, 10, 10, 11, 13, 14, 15, 16, 17, 20, 21, 22])
            started = date.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
            if started > now:
                continue
            write_session(db, template, started, preset, rng, profile_name)
            made += 1
    db.close()
    print(f"{profile_name}: wrote {made} sessions into {db_path}")


def write_session(db: SessionDB, template: dict, started: datetime, preset: dict, rng: random.Random, profile_name: str, parent_id: str | None = None) -> str:
    size = SIZES[template.get("size", "m")]
    source = template.get("source") or rng.choice(preset["sources"])
    heavy = (size is SIZES["xl"] and rng.random() < 0.5) or (template.get("size") == "l" and rng.random() < 0.1)
    model, provider, base_url = preset["heavy_model"] if heavy else preset["main_model"]
    if preset.get("local_model") and rng.random() < 0.06:
        model, provider, base_url = preset["local_model"]
    sid = session_id_for(started, rng)
    cwd = REPO if "api-gateway" in json.dumps(template["steps"]) else REPO2 if "ledger-web" in json.dumps(template["steps"]) else INFRA
    # Delegate children carry _delegate_from, which is how Hermes tells them
    # apart from compression continuations when it walks a lineage.
    model_config = {"_delegate_from": parent_id} if parent_id else None
    db.create_session(sid, source, model=model, model_config=model_config, cwd=os.path.expanduser(cwd) if source != "telegram" else None, parent_session_id=parent_id, profile_name=profile_name)

    t = started
    ts = lambda: t.timestamp()  # noqa: E731
    db.append_message(sid, "user", template["prompt"], timestamp=ts())
    steps = list(template["steps"])
    calls_target = rng.randint(*size["calls"])
    if steps:
        # Pad to about 1.3 tool steps per call, keeping the template's own
        # last step last so the story still ends where the template says.
        pool = list(FILLERS.get(cwd, FILLERS[INFRA]))
        want = max(len(steps), int(calls_target * 1.3) - 1)
        last = steps.pop()
        while len(steps) < want - 1:
            tool, args, result = rng.choice(pool)
            steps.insert(rng.randint(0, len(steps)), (tool, args, r_read(result) if tool == "read_file" else r_terminal(result) if tool == "terminal" else r_search(result.split("\\n"))))
        steps.append(last)
    api_calls = 0
    total_in = total_out = total_cache = total_cache_w = total_reason = 0
    sys_ctx = rng.randint(*SYSTEM_CTX)
    ctx = sys_ctx + rng.randint(*size["first"])
    idx = 0
    while idx < len(steps) or api_calls == 0:
        per_turn = 1 if rng.random() < 0.7 else 2
        chunk = steps[idx: idx + per_turn] if steps else []
        idx += per_turn if steps else 1
        t += timedelta(seconds=rng.randint(4, 40))
        api_calls += 1
        if chunk:
            calls = []
            for n, (tool, args, _result) in enumerate(chunk):
                calls.append({"id": f"call_{sid[-6:]}_{api_calls}_{n}", "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}})
            db.append_message(sid, "assistant", "", tool_calls=calls, timestamp=ts())
            for n, (tool, args, result) in enumerate(chunk):
                t += timedelta(seconds=rng.randint(1, 25))
                db.append_message(sid, "tool", result, tool_name=tool, tool_call_id=calls[n]["id"], timestamp=ts())
        else:
            db.append_message(sid, "assistant", template["reply"], timestamp=ts())
        prev_ctx = ctx if api_calls > 1 else 0
        if api_calls > 1:
            ctx += rng.randint(*size["grow"])
        inp, cache_read, cache_write = call_tokens(rng, provider, api_calls, prev_ctx, ctx, sys_ctx)
        out = rng.randint(*size["output"])
        reason = int(out * rng.uniform(0.0, 0.6)) if provider in ("anthropic", "openai") else 0
        ctx += out
        total_in += inp
        total_out += out
        total_cache += cache_read
        total_cache_w += cache_write
        total_reason += reason
        if idx >= len(steps) and chunk:
            t += timedelta(seconds=rng.randint(3, 20))
            db.append_message(sid, "assistant", template["reply"], timestamp=ts())
            api_calls += 1
            prev_ctx = ctx
            ctx += rng.randint(*size["grow"]) // 2
            inp, cache_read, cache_write = call_tokens(rng, provider, api_calls, prev_ctx, ctx, sys_ctx)
            out = rng.randint(*size["output"]) // 2
            total_in += inp
            total_cache += cache_read
            total_cache_w += cache_write
            total_out += out
            ctx += out
            break
        if not steps:
            break

    usage = CanonicalUsage(input_tokens=total_in, output_tokens=total_out, cache_read_tokens=total_cache, cache_write_tokens=total_cache_w, reasoning_tokens=total_reason, request_count=api_calls)
    usd, status, cost_source, version = price(model, provider, base_url, usage)
    db.update_token_counts(
        sid,
        input_tokens=total_in,
        output_tokens=total_out,
        model=model,
        cache_read_tokens=total_cache,
        cache_write_tokens=total_cache_w,
        reasoning_tokens=total_reason,
        estimated_cost_usd=usd,
        cost_status=status,
        cost_source=cost_source,
        pricing_version=version,
        billing_provider=provider,
        billing_base_url=base_url or None,
        api_call_count=api_calls,
        absolute=True,
    )

    # Auxiliary usage the way the agent records it: a title, a review fork
    # on the main model, and compression on the long ones.
    aux_model, aux_provider, aux_base = preset["aux_model"]
    tu = CanonicalUsage(input_tokens=900, output_tokens=18)
    tusd, *_ = price(aux_model, aux_provider, aux_base, tu)
    db.record_auxiliary_usage(sid, "title_generation", model=aux_model, billing_provider=aux_provider, input_tokens=900, output_tokens=18, estimated_cost_usd=tusd, api_call_count=1)
    if source != "cron":
        # The review fork re-reads the conversation after each turn. On the
        # same model the prefix is warm, so it is mostly cache reads.
        rin = int(ctx * 0.9)
        rcache = int(rin * 0.9)
        rw = rin - rcache if provider == "anthropic" else 0
        ru = CanonicalUsage(input_tokens=rin - rcache - rw, output_tokens=380, cache_read_tokens=rcache, cache_write_tokens=rw)
        rusd, *_ = price(model, provider, base_url, ru)
        db.record_auxiliary_usage(sid, "background_review", model=model, billing_provider=provider, input_tokens=rin - rcache - rw, output_tokens=380, cache_read_tokens=rcache, cache_write_tokens=rw, estimated_cost_usd=rusd, api_call_count=1)
    if template.get("size") in ("l", "xl") and rng.random() < 0.6:
        # Compression sends the whole context once; the prefix is cached.
        cread = int(ctx * 0.85) if provider == "anthropic" or provider in IMPLICIT_CACHE_PROVIDERS else 0
        cu = CanonicalUsage(input_tokens=ctx - cread, output_tokens=1_100, cache_read_tokens=cread)
        cusd, *_ = price(model, provider, base_url, cu)
        db.record_auxiliary_usage(sid, "compression", model=model, billing_provider=provider, input_tokens=ctx - cread, output_tokens=1_100, cache_read_tokens=cread, estimated_cost_usd=cusd, api_call_count=1)

    # Children for delegated work.
    for i in range(template.get("children", 0)):
        child = dict(
            title=f"Subagent: {template['title']}",
            prompt=template["steps"][0][1]["tasks"][i]["goal"],
            steps=[("terminal", {"command": "cd ~/code/api-gateway && uv run pytest -q"}, r_terminal("...... 6 passed in 2.31s"))],
            reply="Done.",
            size="m",
            source="subagent",
        )
        write_session(db, child, started + timedelta(seconds=30 + i * 5), preset, rng, profile_name, parent_id=sid)

    # Titles are unique per store, like the real auto-titler's output. Try
    # the base title, then its variants, then a dated form (what cron runs
    # get anyway).
    candidates = [template["title"], *TITLE_VARIANTS.get(template["title"], [])]
    if source == "cron":
        candidates = [f"{template['title']} · {started.strftime('%b %d %H:%M')}"]
    rng.shuffle(candidates)
    candidates += [f"{template['title']} · {started.strftime('%b %d')}", f"{template['title']} · {started.strftime('%b %d %H:%M')}"]
    for title in candidates:
        try:
            db.set_session_title(sid, title)
            break
        except ValueError:
            continue
    ended = t + timedelta(seconds=rng.randint(2, 15))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE sessions SET started_at=?, ended_at=?, last_activity_at=?, end_reason=?, title_source=? WHERE id=?",
            (started.timestamp(), ended.timestamp(), ended.timestamp(), "cron_complete" if source == "cron" else rng.choice(["done", "tui_close", "new_session", "cli_close"]), "generated", sid),
        )
    return sid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="profile name under <hermes home>/profiles/")
    ap.add_argument("--preset", choices=sorted(PRESETS), required=True)
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--home", default=os.environ.get("HERMES_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "hermes"))
    ap.add_argument("--reset", action="store_true", help="delete the profile's state.db first")
    args = ap.parse_args()
    profile_dir = Path(args.home) / "profiles" / args.profile
    if not profile_dir.exists():
        raise SystemExit(f"profile dir not found: {profile_dir}")
    db_file = profile_dir / "state.db"
    if db_file.exists():
        if not args.reset:
            raise SystemExit(f"{db_file} exists; pass --reset to replace it (this is demo data only)")
        for suffix in ("", "-wal", "-shm"):
            try:
                (profile_dir / f"state.db{suffix}").unlink()
            except FileNotFoundError:
                pass
    now = datetime.now().replace(microsecond=0)
    seed(profile_dir, PRESETS[args.preset], args.days, random.Random(args.seed), args.profile, now)


if __name__ == "__main__":
    main()
