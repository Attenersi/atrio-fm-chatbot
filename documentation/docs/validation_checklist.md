# Validation checklists

Use the right checklist for the situation:

| When | Document |
| --- | --- |
| **First baseline**, major schema/capture changes, or full doc/training audit | [`validation_initial_acceptance.md`](validation_initial_acceptance.md) |
| **Every deploy** or routine release | [`validation_release.md`](validation_release.md) |

## Why two lists

- **Initial acceptance** includes one-time or heavy items (full documentation audit, fresh-DB schema behavior, exhaustive training export contract, every review state).
- **Release checklist** stays short so it is realistic to run on every deploy without turning into a duplicate full acceptance test.

If you are unsure, run the release checklist first; escalate to initial acceptance when migrations, training capture, or export contracts change.
