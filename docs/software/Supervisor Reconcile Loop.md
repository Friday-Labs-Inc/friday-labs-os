# Supervisor Reconcile Loop — auto-wake for real boards

**What changed (plain English).** The Core Hub has always had a *supervisor* whose job
is to bring managed modules up (`configure` → `activate`). Until now it was a
**one-shot**: it fired 3 seconds after the Core Hub started, waited up to 5 seconds
per node, and permanently skipped anything that wasn't there yet. That worked in sim,
where every node launches together — but real ESP32 boards arrive on their own clock
(the serial agent has to come up, a board may be mid watchdog-restart with boot
backoff, someone may plug a board in late). On a cold boot the one-shot fired long
before any board existed, skipped all four, and the fleet stayed dark until a human
ran the wake-up by hand.

**Now it's a reconcile loop.** Every `reconcile_period_s` (default 10 s) the
supervisor asks each managed node for its lifecycle state (`get_state`) and walks
anything sitting `unconfigured` or `inactive` toward `active`:

```
every 10 s, per managed node:
  not on the graph yet?      → try again next tick (no error, no skip)
  unconfigured?              → configure  (board registers here)  → then activate
  inactive?                  → activate   (5 Hz heartbeat starts here)
  active / mid-transition?   → leave it alone
```

It is idempotent — an active node is never touched — and self-healing: a board that
power-cycles or watchdog-restarts mid-mission comes back `unconfigured` and is
re-woken on the next tick, no human involved.

**What did NOT change.**
- The rejoin rule: after a split-brain failover the supervisor stays hands-off,
  exactly as before.
- Authority: the loop only automates *bring-up*. The command chain
  (E-stop > operator > CC > AI > plan) sits above it, untouched.
- The boards: no firmware change. The loop speaks the same 3-service contract
  (`get_state` / `change_state`).

**Configuration** (`managed_nodes` empty by default — deployments opt in):

```yaml
# /etc/friday/core_hub.params.yaml on the Core Hub Pi
core_hub:
  ros__parameters:
    managed_nodes:
      - mark1/mark1_mob_drive_001
      - mark1/mark1_mob_steer_001
      - mark1/mark1_sparkbay_001
      - mark1/mark1_sensor_001
    reconcile_period_s: 10.0
```

**If this breaks, look here.**
- Board never wakes: is its `change_state`/`get_state` on the graph?
  (`ros2 daemon start; ros2 service list | grep <node>`). If not, it's a link
  problem (agent journal is ground truth), not a supervisor problem.
- `configure` FAILED in the log: the board refused the transition — check the
  board's serial log; the supervisor will retry next tick.
- Supervisor idle: `managed_nodes` is empty — parameters not loaded
  (check the service's `--params-file`).

**Glossary.** *Reconcile loop* — a controller that repeatedly compares desired state
("all managed boards active") with actual state and fixes the difference, instead of
assuming one attempt at startup succeeds forever. Same idea Kubernetes uses.
