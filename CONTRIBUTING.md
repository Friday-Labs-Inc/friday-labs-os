# Contributing to Friday Labs OS

> The rules for contributing to the Mark 1 dossier and (once it exists) the implementation. Read once before your first PR.

## The Dossier-First Rule

The single most important rule. **The dossier is the spec.** If your contribution disagrees with the dossier, the dossier wins. Update the docs first; the code follows.

Concretely:

- **Behavior change?** First propose an addendum (or update an existing one) and get it merged. *Then* open the code PR that implements it.
- **Refactor or cleanup?** No addendum needed, but every line of the diff must trace to an existing decision in the dossier.
- **New hardware in the BOM?** New addendum first.
- **Changing a locked addendum?** Revise the addendum in the same PR as the implementation. Both reviewed together.

If you find yourself writing code that "needs" the dossier to change — pause. Open the dossier PR first.

## Before Your First Contribution

1. **Read the dossier end-to-end.** Start at [`docs/Mark 1 Index.md`](docs/Mark%201%20Index.md). About 3-4 hours.
2. **Set up your workstation** per [`docs/onboarding/Phase 1 Implementation Kickoff.md`](docs/onboarding/Phase%201%20Implementation%20Kickoff.md) — Ubuntu 24.04 LTS, ROS 2 Jazzy, Gazebo Harmonic, ros_gz bridge, Foxglove.
3. **Know what the skills enforce.** The 8 skills under `.claude/skills/` refuse specific anti-patterns by design. Use them — they exist so you can't forget the discipline.

## Pull Request Workflow

1. **Branch off `main`** with a descriptive name:
   - `addendum/<short-topic>` — new or revised addendum
   - `module/<module-name>` — module spec change
   - `code/<area>` — implementation work (once code exists)
   - `fix/<what>` — bug fix
   - `docs/<what>` — typo / wording / cross-link fix
2. **One concern per PR.** Typo fix is one PR. Addendum revision is another. Don't bundle.
3. **Self-review your diff** before opening. Every line should trace to the PR title.
4. **Open the PR** with a description covering:
   - What changed and why (link to the dossier section or issue)
   - How a reviewer can verify it
   - What you considered and rejected (the "why not" matters)
5. **Pass CI.** Once CI exists (Phase 1 ships it), it must be green. Stage 5 fault-injection scenarios are mandatory; never merge with a Stage 5 regression.
6. **Get review from a code owner** — see [`CODEOWNERS`](.github/CODEOWNERS).

## Commit Message Format

Conventional commits:

```
<type>: <description>

<optional body explaining why>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

Scoping examples:

- `docs(addendum): revise authority lease quiet window from 500ms to 300ms`
- `docs(module): add IR break-beam debounce filter spec to aerial bay`
- `feat(locomotion): implement corner-steer PID loop`
- `fix(authority): reject commands with epoch < current holder`
- `test(stage5): add S7 partition-during-handoff scenario`

The body should explain **why**, not what. The diff shows what.

## The Eight Discipline Rules

These come straight from [`docs/onboarding/Phase 1 Implementation Kickoff.md`](docs/onboarding/Phase%201%20Implementation%20Kickoff.md). Internalize them; they exist because past mistakes paid for them.

1. **The dossier is the spec.** Code that contradicts the dossier is wrong; fix the doc first.
2. **Every line of code traces to a decision.** No drive-by changes. No "while I'm here."
3. **Every Mark 1-specific message has the mandatory header.** No exceptions.
4. **Every command source is validated against the authority lease.** Unsigned commands are dropped with `FaultReport`, never silently ignored.
5. **Every ESP32 with motion authority uses the hardware Task WDT.** Never a FreeRTOS soft timer for safety.
6. **Tests that claim "pass" report a p99 number.** Vibes don't pass CI.
7. **Never merge to main with a failing Stage 5.** No exceptions, including "just for the demo."
8. **Read the dossier on Monday, write code Tuesday-Friday.** Drift between docs and code is cheap to catch weekly, expensive to catch later.

## Using the Skills

The skills under `.claude/skills/` are not optional decoration. Each enforces specific rules that exist because past mistakes paid for them:

| Skill | Use when |
|---|---|
| `friday-msgs-author` | Adding or changing any `friday_msgs` interface |
| `lifecycle-node-scaffold` | Creating a new module agent (Pi rclpy/rclcpp or ESP32 rclc) |
| `sim-bringup` | Bringing Gazebo up; onboarding a developer |
| `fault-injection` | Running Stage 5; verifying safety regressions are caught |
| `safe-stop-audit` | Before any field test; after any Locomotion firmware change |
| `module-spec` | Drafting a new module spec (house style) |
| `qos-audit` | After any new node ships; before integration test |
| `command-center-protocol` | Working on the external link or the Telemetry Node Agent |

If a skill refuses your change, the skill is right and your change is wrong. The fix is to change the change, not the skill.

## Reporting Issues

Open a GitHub Issue with:

- What you observed (specific dossier section or code path)
- What you expected (link to the relevant addendum)
- What you tried

If you found a **contradiction in the dossier**, that's especially valuable — open the issue with both conflicting sections quoted.

## Code Review

Every PR needs at least one code-owner approval before merge — see [`CODEOWNERS`](.github/CODEOWNERS).

Reviewers check:

- Does the change trace to a dossier decision?
- Does it follow the relevant skill's rules?
- Are tests included with measured p99 numbers where applicable?
- Is the commit message accurate and explains the *why*?
- Are wiki-link conventions maintained? (We use standard markdown links, not `[[wiki-links]]`, so the dossier renders on GitHub.)

## Diff Discipline

Adapted from project conventions:

- **Every changed line should trace to the PR title.** If you can't justify a line by pointing at the title, remove it.
- No drive-by formatting changes.
- No refactors of adjacent code that wasn't broken.
- No comments explaining what well-named code already says.
- No speculative error handling for cases that can't happen.

## License

TBD — to be added before any external collaboration.
