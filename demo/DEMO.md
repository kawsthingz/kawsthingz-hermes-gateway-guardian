# Demo script (90 seconds)

Open with the story: “Your Hermes Telegram bot goes quiet at 2 a.m. Customers are messaging. The gateway says it is running. Nobody gets a reply. The worst part is the silence.”

1. Show the blocked screenshot: Gateway Guardian returns `BLOCKED` with the exact cause (repeated 409/polling conflict).
2. Run `gateway_guardian_status` on a healthy gateway: state `OK`.
3. Start a duplicate poller or freeze a lane.
4. Run `gateway_guardian_status` again: state `BLOCKED`, cause named, pattern counts shown.
5. Run `gateway_guardian_recover` with `restart-gateway`: it prints the approved operator plan and records the intent. It never restarts anything by itself.
6. Operator approves and runs the plan. Status returns to `OK`.

Close with: “Silent failures erode trust. Gateway Guardian makes the silent failure loud, in one line.”

## Local checks already run

- Unit tests: 3 pass.
- `hermes plugins validate . --install-deps`: pass.
- `hermes plugins doctor . --ci`: pass.
- Live status on the build box returned `BLOCKED` from real 409/polling log patterns.
