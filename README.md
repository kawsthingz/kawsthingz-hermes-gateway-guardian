# Hermes Gateway Guardian

A small, read-only reliability guard for Hermes gateway and Telegram operation.

## Why

Hermes users hit the same painful class of failure: Telegram goes quiet, a 409 polling conflict appears (two pollers, one token), the gateway freezes, or a stale lock blocks restart. The agent often reports "gateway running" while no reply can reach the user. Gateway Guardian makes that state visible in one place.

## What it does

- `gateway_guardian_status` — scans recent gateway logs and process list for:
  - 409 / polling conflicts
  - duplicate pollers
  - freeze / unresponsive signals
  - stale locks
  - missed / failed deliveries
  - returns one state: `OK`, `DEGRADED`, or `BLOCKED`, with the exact cause and pattern counts.
- `gateway_guardian_recover` — records the recovery intent and returns the exact operator plan. It never restarts, kills or rebinds anything by itself.
- `/gateway-guardian` — slash command that prints the status.

## Safety

- Read-only status by default.
- Recovery is approval-gated: the tool prints commands, the operator approves and runs them.
- No message bodies are stored. Only pattern counts and recovery intents are kept.

## Demo

1. Healthy gateway: status is `OK`.
2. Start a duplicate poller or freeze a lane: status becomes `BLOCKED` with the exact cause.
3. Run the approved recovery plan from `gateway_guardian_recover`.
4. Status returns to `OK` and the intent log shows the action.

## Validate

```bash
hermes plugins validate /root/.hermes/plugins/gateway-guardian --install-deps
hermes plugins doctor gateway-guardian --ci
```
