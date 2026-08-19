# Ledgerline

Know what every Hermes session costs, why, and what to change. One plugin
file for Hermes Desktop. No backend, no restart, and it works the same on a
local gateway and on a remote one.

<img width="1002" height="958" alt="ledgerline" src="https://github.com/user-attachments/assets/6f0911eb-f684-4e25-82d5-9cc832f855fa" />


## What you get

**It shows the money.** Spend today, this week, this month, and where the
month is heading. Spend per day, per model and per helper task (compression,
memory review, title generation), so the quiet costs show up next to the
chat. Each model row splits its tokens into plain input, cache reads, cache
writes and output, because on a cached provider that split is the bill.

**It tells you what to do about it.** Low cache hit rates, sessions with
unknown pricing, helper tasks eating a big share, and a cheaper model that
lists the same tokens for less, each with the dollar figure attached. Monthly
and per-session budgets warn you at 80% and 100%.

**It watches the session you're in.** A ledger pane and a statusbar chip
follow the live turn: tokens, calls, context fill, tools as they run,
subagents as they finish, and a running cost at list price that turns into
the recorded cost the moment the turn ends.

**It explains a session, inside Hermes.** Pick a session and ask. A quick
explain is one small model call. A full audit opens a session with the
digest as context and streams the answer back into the pane. A background
audit runs headless and saves the result. You see the digest before anything
is sent.

**It reaches you where you already are.** Budget alerts go out through any
messaging platform your gateway already has. Daily, weekly or monthly spend
reports run as cron jobs on the gateway and land in the channel you pick.

**It works on remote gateways.** No Python half to install on the other
machine, no `config.yaml` edit, no restart. Copy one file into the desktop
and it works, local or remote, one profile or all of them.

## Install

Copy `plugin.js` to `$HERMES_HOME/desktop-plugins/ledgerline/plugin.js`
(`%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` elsewhere). The desktop
picks it up within seconds and hot-reloads on every save. Open it from the
sidebar, the palette ("Ledgerline: Open"), or Ctrl/Cmd+Alt+L.

## What's inside

- Overview: spend windows and a month projection, budgets, spend per day,
  by model with what-if repricing, by helper task, recommendations you can
  dismiss and restore.
- Sessions: tokens, cache hit rate, spend, tools, failures, files and
  subagents. Title and full-text search. Sort by recent, cost, tokens, tools
  or worst (a bounded scan for failed tool calls that keeps its results).
- Profiles: the active profile, any single profile, or all of them merged
  with a per-profile table. Budgets, dismissed tips, scans and saved answers
  are kept per profile. The all-profiles view sums the profile budgets unless
  you give it one of its own.
- Live ledger pane, timeline tab and statusbar chip.
- Analysis in three flavours: quick explain, full audit, background audit.
- Alert channel and scheduled reports with pause, resume and remove.

## Where the numbers come from

Every dollar is what the gateway recorded for that session, at the prices it
recorded it with. Ledgerline does not reprice history, on purpose: the figures
stay the same ones `hermes insights` and your provider invoice show. The flip
side is that a session Hermes priced wrong, or could not price (a local model,
a provider it has no snapshot for), shows up that way here too. Unknown
pricing is flagged in the recommendations, not fixed.

List prices for what-ifs and the live estimate come from the gateway's model
catalog, fetched on load, again on every reconnect, and hourly. Cache hit
rate is cache reads over input plus reads plus writes, the same ratio the
agent logs. Cache writes per model come from the session list and are shown
as a floor when child sessions are missing from it.

## How it reaches the gateway

Live data and actions go through the desktop plugin SDK (`host.request`
JSON-RPC and `host.onEvent`). History and analytics use the gateway's own
REST routes through the desktop's bridge, the same door the app uses for its
own session list, so it works on local, token and OAuth remotes. Reports and
alert pushes run `hermes cron` and `hermes send` on the gateway host through
`cli.exec`. If the REST door is ever missing, the plugin drops to an RPC-only
mode and says so on the About tab.

Nothing leaves your machine unless you ask for it: an explain or audit goes
to the model you picked, an alert or report goes to the channel you picked.

## Known upstream gaps

Ledgerline works around these today. If they get fixed in Hermes Agent the
plugin will feature-detect the new fields and use them.

- `session.usage` over JSON-RPC returns tokens but no cache tokens and no
  cost, although the agent tracks both.
- The gateway relay drops `cost_usd` from `subagent.complete` events.
- `cron.manage` `add` cannot set a delivery target over RPC.
- `/api/analytics/usage` has no cache write column and no per-model cache
  reads. Ledgerline reads cache writes from the session rows (marked with a
  floor sign when child sessions are missing from the list) and per-model
  cache reads from `/api/analytics/models`.

## Contributing

Contributions are welcome. Open an issue first for anything bigger than a
small fix so we can agree on the shape before you spend time on it.

## License

MIT
