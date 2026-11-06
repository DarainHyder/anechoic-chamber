# Anechoic Chamber: progress log

Updated at every stop point. Plan: `docs/PLAN.md`. Process: `docs/BUILD_PROTOCOL.md`.

## Current status

- **Phase:** 0, Foundations
- **Step:** 3, Build; tasks 1 to 8 done, first push next
- **Next:** push file by file, confirm CI, then run the gate check
- **Last updated:** 2026-11-06

## Phase overview

| Phase | Name | Status | Gate |
| --- | --- | --- | --- |
| 0 | Foundations | Build | Not run |
| 1 | Data pipeline | Not started | Not run |
| 2 | Baseline model | Not started | Not run |
| 3 | Browser engine | Not started | Not run |
| 4 | Chrome extension MVP | Not started | Not run |
| 5 | Embedding-conditioned model and teach-your-trigger | Not started | Not run |
| 6 | Listening test, round 1 | Not started | Not run |
| 7 | Agent layer | Not started | Not run |
| 8 | Polish, accessibility, Urdu, privacy | Not started | Not run |
| 9 | Live mode v2 | Not started | Not run |
| 10 | Launch | Not started | Not run |

## Phase 0: Foundations

### Tasks

| # | Task | Status |
| --- | --- | --- |
| 1 | Repo skeleton and `CLAUDE.md` | Done |
| 2 | TypeScript workspace | Done |
| 3 | Python workspace | Done |
| 4 | Privacy guard (pre-push hook and check script) | Done |
| 5 | CI workflow | Done |
| 6 | Recording kit and clip-log checker | Done |
| 7 | Tester kit and tester-log checker | Done |
| 8 | Account guide and `.env.example` | Done |
| 9 | First push, file by file, CI file last | Not started |
| 10 | Gate check, review and report | Not started |

### Gate table

| Check | Target | Actual | Result |
| --- | --- | --- | --- |
| CI | Lint, type-check and unit tests green | Not run | Pending |
| Testers | 5 to 10 booked, main triggers recorded | Not run | Pending |
| Clips | 100 local trigger clips logged with consent notes | Not run | Pending |

## Decisions

| Date | Decision | Reason | Source |
| --- | --- | --- | --- |
| 2026-11-06 | Remote is `https://github.com/DarainHyder/anechoic-chamber` (public) | Project repo | User |
| 2026-11-06 | Commit one file at a time as each task passes (`phase-N: <task>: <file>`), then push those commits one by one at the end of the phase | Meets the user's per-file push rule and the protocol's per-task commits | User, reconciled with protocol Step 3 |
| 2026-11-06 | Added Freesound to the Phase 0 accounts | Phase 1 needs its API key | User approved; PLAN.md edited |
| 2026-11-06 | Added a git-ignored `private/` folder, pre-push hook and CI re-check | Repo is public; CI alone only reacts after a leak | User approved; PLAN.md edited |
| 2026-11-06 | ESC-50 source changed to `karolpiczak/ESC-50` | Original repo, not `xufuou/ESC-50` | User approved; PLAN.md edited |
| 2026-11-06 | GPU check skipped only when `SMOKE_TEST = True` | Plan and protocol conflicted on CPU smoke tests | User approved; PLAN.md and BUILD_PROTOCOL.md edited |

## Proposed plan changes (not applied; need approval)

None.

## Open issues

- `gh` is not installed, so CI results are read from GitHub's public API.
- Local machine: Python 3.14 is the default and 3.11 is also installed; Node 24; `ffmpeg`, `pnpm` and `make` are not installed.
- Check that the git commit email (`darainhyder2004@gmail.com`) is on the GitHub account, or commits will not link to the profile.
- `npm audit` reports 10 moderate warnings, all from one advisory in `minimatch` (GHSA-g3hv-75wg-m249), used by ESLint. Dev-only, and its input is our own config; the only fix is a forced breaking change. Recheck when ESLint updates.
- `check_testers.py` catches name columns, emails, phone numbers and handles, but cannot recognise a name typed into free text.
- The repo has no LICENSE, so nobody else may legally reuse the code yet. Decide before the Phase 10 launch.
