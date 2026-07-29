# Crash postmortem: 11 months of silent restart looping

**Date of investigation:** 2026-07-29
**Window of failure:** 2025-08-25 to 2026-07-29 (approximately 11 months)
**Impact:** service never available; 7.9 GB of logs written; no data loss

## Summary

TinyIntent's bridge service died on startup and was restarted by launchd roughly
every ten seconds for eleven months. It never served a request in that entire
period. The failure was silent because the launchd job stayed registered, so
nothing surfaced as broken.

## Root cause

Commit `d27fb09` (2025-08-25), the last commit of the August 2025 sprint, deleted
`bridge/gen_client.py` (388 lines) while leaving importers pointing at it.

The import chain that fails on every boot:

```
bridge/tinyrpc.py:28
  -> bridge/api_main.py:16
    -> bridge/routes/__init__.py:10
      -> bridge/routes/shortcut.py:22
         from ..gen_client import async_ollama_client
         ModuleNotFoundError: No module named 'bridge.gen_client'
```

`com.tinyintent.tinyrpc.plist` sets `KeepAlive=true`, so launchd restarted the
process after every crash, indefinitely.

Three further references point at `tinyintent.bridge.gen_client`, a module path
that never existed at all. Those were already broken before `d27fb09`:

- `tests/conftest.py:201`
- `tests/integration/gen_reliability_test.py:26`
- `tests/router/router_async_test.py:25`

The two genuinely broken by `d27fb09` are `bridge/routes/shortcut.py:22` and
`tinyintent/interactive.py:211,297`.

## Secondary failure

`com.tinyintent.autopilot` runs hourly (`ThrottleInterval 3600`). Every run
validated the helper registry, and every helper failed validation:

| Helper | Failure |
|---|---|
| `bot_guard` | Missing `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, `EXCHANGE_BASE_URL`, `EXCHANGE_MODE`; provenance file missing |
| `ssh_ops` | Missing `SSH_HOST`, `SSH_USER`; provenance file missing |
| `network_monitor` | File integrity check failed; `Manifest loading failed: 'list' object has no attribute 'get'` |

The first two are unprovisioned credentials, which is expected for a dormant
system. The `network_monitor` manifest error is a genuine code defect and is
still unfixed.

Each run then terminated with `retrain_router` failing and
`make: *** [autopilot-dry] Error 1`.

## Evidence

Log volume at time of investigation:

| File | Size | Lines |
|---|---|---|
| `audit.log` | 5.2 GB | 5,180,818 |
| `stderr.log` | 2.0 GB | 33,846,575 |
| `stdout.log` | 688 MB | 7,303,000 |
| `autopilot.err.log` | 5.3 MB | 112,310 |

`audit.log` span: `2025-08-17T01:49:17Z` to `2026-07-29T09:24:40Z`.

A 50 MB sample of `stderr.log` contained 66,226 tracebacks, of which 100 percent
were the `bridge.gen_client` error. Extrapolated across 33.8M lines at roughly
twelve lines per traceback, that is approximately 2.8 million restarts, which is
consistent with one restart per ten seconds over eleven months.

A 20 MB sample of `audit.log` contained 18,403 `helper_validation_failure`
records against exactly three helpers, and 4 `autopilot_step` records.

Earlier entries at the head of `stderr.log` show a different, older failure
(`No module named 'fastapi'`) from before the virtualenv existed. That was
already resolved and is unrelated.

## Remediation applied 2026-07-29

1. `com.tinyintent.tinyrpc` and `com.tinyintent.autopilot` booted out and
   disabled via `launchctl disable`, so they do not return on login. The plists
   remain in `~/Library/LaunchAgents/` so the service can be re-enabled with
   `launchctl enable` and `launchctl bootstrap`.
2. Outstanding work from the August and December 2025 sessions committed.
3. Three source modules that `.gitignore` had silently excluded were recovered
   and committed. See below.
4. Secrets removed from history and the repository pushed to GitHub.
5. Bulk log files deleted after this postmortem was written.

## Not fixed

- `bridge/gen_client.py` is still missing and the importers still reference it.
  The file is recoverable from the pre-rewrite history if needed.
- The `network_monitor` manifest defect.
- There is still no log rotation. **Do not re-enable either launchd job until
  rotation exists**, or this recurs.

## Related finding: gitignore was hiding source code

`.gitignore` excluded `bridge/logs/` as a whole directory. Three source modules
live in that directory and were therefore never tracked:

- `bridge/logs/audit.py` (164 lines) - writes the audit log described above
- `bridge/logs/sanitize.py` (288 lines) - redacts secrets from log output
- `bridge/logs/util.py` (3 lines)

They existed only in the working tree, in no commit and on no remote. Git cannot
re-include a file whose parent directory is excluded, so the rule was narrowed to
`bridge/logs/*` with a negation for `*.py`.
