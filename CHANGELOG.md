# Changelog

## 0.1.0 (2026-08-19)

First release. One plugin file for Hermes Desktop with:

- Sessions list and detail (tokens, cache hit rate, spend, tools, failures,
  files, subagents, timeline) over core REST with an RPC fallback. Content
  search, worst-first scan, archived toggle.
- Overview with spend windows, month projection, spend per day, by model
  (input, cached, written and output tokens, what-if repricing at list
  price), by helper task, recommendations you can dismiss and restore,
  monthly and per-session budgets.
- Profile scope: active profile, any single profile, or all profiles merged
  with a per-profile table. Budgets, dismissed tips, scans and saved answers
  kept per profile. The all-profiles view sums the profile budgets unless it
  has one of its own.
- Live ledger pane, statusbar chip and a running cost estimate at list
  price, from the gateway event stream.
- Analysis inside Hermes: quick explain, full audit, background audit.
- Alert channel and daily, weekly or monthly spend reports through the
  gateway's cron.
- Seed tool (`tools/seed/seed_history.py`) that fills a profile with a
  month of realistic history for screenshots and testing, priced with the
  agent's own cost function.

Checked by hand on a local gateway (Hermes 0.20.4) and on a remote gateway
in Docker behind username and password auth.

plugin.js SHA-256: `e5185febfc348064c22e87d42ae9d775e2a6b785abb140f552ac65eb5e7649f8`
