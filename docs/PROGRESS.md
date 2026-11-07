# Anechoic Chamber: progress log

Updated at every stop point. Plan: `docs/PLAN.md`. Process: `docs/BUILD_PROTOCOL.md`.

## Current status

- **Phase:** 0, Foundations: complete
- **Step:** 6, Report given; waiting for NEXT
- **Next:** on NEXT, give the Phase 1 briefing (modified as recommended below) and stop for APPROVE
- **Last updated:** 2026-11-07

## Phase overview

| Phase | Name | Status | Gate |
| --- | --- | --- | --- |
| 0 | Foundations | Complete | PASS |
| 1 | Data pipeline | Not started | Not run |
| 2 | Baseline model | Not started | Not run |
| 3 | Browser engine | Not started | Not run |
| 4 | Chrome extension MVP | Not started | Not run |
| 5 | Embedding-conditioned model and teach-your-trigger | Not started | Not run |
| 6 | Automated perceptual evaluation, round 1 | Not started | Not run |
| 7 | Agent layer | Not started | Not run |
| 8 | Polish, accessibility, Urdu, privacy | Not started | Not run |
| 9 | Live mode v2 | Not started | Not run |
| 10 | Launch | Not started | Not run |

## Phase 0: Foundations

### What was built

| # | Task | Status |
| --- | --- | --- |
| 1 | Repo skeleton and `CLAUDE.md` | Done |
| 2 | TypeScript workspace: `packages/engine`, `extension`, `web`; ESLint, strict TypeScript, Vitest | Done |
| 3 | Python workspace: `ml`, `synth`, `eval`, `api`; Ruff, strict mypy, pytest with Hypothesis | Done |
| 4 | Privacy guard: `scripts/check_private.py` and `.githooks/pre-push`, turned on by `npm install` | Done |
| 5 | CI: privacy, TypeScript and Python jobs on every push | Done |
| 6 | Recording kit and clip-log checker | Done; optional since 2026-11-07 |
| 7 | Tester kit and tester-log checker | Built, then removed on 2026-11-07 (no human testers) |
| 8 | Account guide and `.env.example`; all 6 accounts created and keys tested | Done |
| 9 | Push file by file, CI file last; Claude attribution removed from history | Done |
| 10 | No-tester plan change: automated perceptual evaluation replaces testers | Done |
| 11 | Gate check, review and report | Done |

Tests: 3 TypeScript tests and 68 Python tests. The Python tests include 8 that push to a real local remote and confirm the hook blocks private files.

### Gate table

The gate was revised on 2026-11-07, when human testers and own recordings were dropped (see Decisions).

| Check | Target | Actual | Result |
| --- | --- | --- | --- |
| CI | Lint, type-check and unit tests green | All 3 jobs green, run 42378400898 on `ef014e3` | PASS |
| Accounts | Vercel, Freesound, Kaggle (phone verified), Hugging Face, Google AI Studio, Groq | 6 of 6; each key accepted by its provider on 2026-11-06 | PASS |
| Privacy guard | Blocks private files in a real push | 8 of 8 real-push tests pass; the hook ran on every push to GitHub and found nothing private | PASS |

### Phase review

**What worked**
- CI passed on its first run on GitHub, and stayed green across both history versions.
- The privacy guard works in real pushes: it blocks private folders, audio, `.env` files, filled-in `.env.example` values and files added then deleted.
- One file per commit held across 71 commits, checked by a script before each push.

**What was harder than expected**
- Removing Claude attribution needed a history rewrite and a force push. GitHub's contributors sidebar is cached separately and may lag.
- One commit briefly held two files. It was split before any push.
- A shell quoting error and one lost command output cost time, but no work. The checks were rerun rather than assumed.

**Surprises and what they tell us**
- GitHub's sidebar counts co-authors from commit messages, while the contributors API does not. Attribution lines must never be written.
- Kaggle's dataset-list endpoint accepted a fake token. Key checks must use endpoints that need login, or they prove nothing.
- The first Groq key was cut short when copied. Every key is now tested, not assumed.

**Risks from PLAN.md**
- *Bigger:* removal artefacts. With no human listeners, only automated judges stand between a bad model and users. A new risk, "automated judges miss what sufferers hear", was added to PLAN.md.
- *Bigger:* local sounds are missing without own recordings. This was added to the risk table and will go in the data card.
- *Smaller:* privacy leaks. A hook, a CI history check and the public-repo rules are in place.
- *Smaller:* Kaggle quota and access. The account is phone-verified and the token works.

**What changes later phases**
- Phase 1 gains a Freesound collector and the 80-clip frozen real-world test set, and automated realism checks replace the human listening check.
- Phase 2's harness must include the perceptual judges, check their licences, and **validate them before trusting them**: on synthetic mixtures with known ground truth, each judge's score must track the true leftover trigger energy.
- Phase 6 becomes Kaggle notebook K7, and the Phase 8 and 9 gates are now automated.

**Technical debt and shortcuts**
- *Dangerous if skipped:* the automated judges are unvalidated. Releases now rest on them, so the Phase 2 validation above is a hard requirement, not a nice-to-have.
- *Low:* the `minimatch` audit warning (dev-only), and the unused optional recording kit.
- *Low:* no LICENSE yet.

### Recommendation: (b) a modified Phase 1

Run Phase 1 as planned, with these additions:
1. **Freesound collector:** CC0 and CC BY clips only, with each clip's licence, author and source logged, polite rate limits, and the key read from `.env`.
2. **Frozen real-world test set:** 80 Creative Commons clips of real scenes, locked before any model work and never used for tuning.
3. **Automated mixture realism checks:** clipping, loudness ranges and trigger-to-bed ratios, plus an independent tagger confirming speech and trigger presence on 200 mixtures. Claude Code reviews spectrograms of 20 mixtures. Together these replace the human listening check.
4. **Data card:** states the local-sound gap explicitly.

*Trade-offs:* Phase 1 grows from medium to medium-large. Moving the real-world test set to Phase 2 would shrink Phase 1, but the set should be frozen before any model sees data, so it belongs here. Options (a) and (c) don't fit: (a) ignores the no-tester decision, and nothing is broken that needs a corrective mini-phase (c).

## Decisions

| Date | Decision | Reason | Source |
| --- | --- | --- | --- |
| 2026-11-06 | Remote is `https://github.com/DarainHyder/anechoic-chamber` (public) | Project repo | User |
| 2026-11-06 | Commit one file at a time as each task passes (`phase-N: <task>: <file>`), then push those commits one by one at the end of the phase | Meets the user's per-file push rule and the protocol's per-task commits | User, reconciled with protocol Step 3 |
| 2026-11-06 | Added Freesound to the Phase 0 accounts | Phase 1 needs its API key | User approved; PLAN.md edited |
| 2026-11-06 | Added a git-ignored `private/` folder, pre-push hook and CI re-check | Repo is public; CI alone only reacts after a leak | User approved; PLAN.md edited |
| 2026-11-06 | ESC-50 source changed to `karolpiczak/ESC-50` | Original repo, not `xufuou/ESC-50` | User approved; PLAN.md edited |
| 2026-11-06 | GPU check skipped only when `SMOKE_TEST = True` | Plan and protocol conflicted on CPU smoke tests | User approved; PLAN.md and BUILD_PROTOCOL.md edited |
| 2026-11-06 | No Claude attribution on commits or pull requests; strip it from existing history | User asked to remove Claude from collaboration on GitHub | User |
| 2026-11-07 | No human testers. An automated perceptual battery replaces listening tests: independent taggers and quality models, Zwicker–Fastl annoyance, artefact checks and spectrogram review. Phase 6 becomes Kaggle K7; Phase 8 and 9 gates are automated | User cannot recruit testers and asked for the best automated method | User approved; PLAN.md edited |
| 2026-11-07 | No own recordings planned. Freesound CC0 and CC BY clips replace them, plus an 80-clip Creative Commons real-world test set; the recording kit stays as an option | User cannot record | User approved; PLAN.md edited |
| 2026-11-07 | Phase 0 gate revised to CI, accounts and the privacy guard; tester kit removed | Follows from the two decisions above | User approved |
| 2026-11-07 | Nothing is stored on C:. Temp files, caches and helper scripts go to `F:\V3XON\.cache\anechoic-chamber\` | User request | User |

## Proposed plan changes (not applied; need approval)

- The Phase 1 additions in the recommendation above. They take effect if the user replies NEXT.

## Open issues

- GitHub's contributors sidebar may still show Claude from its cache. No commit contains a Claude line (checked through the API). If it persists, contact GitHub Support.
- Judge models (for example PANNs, BEATs, DNSMOS, Squim) and the psychoacoustics library: licences and validity unverified until Phase 2.
- Accounts are done: Vercel, Freesound, Kaggle (phone verified, as confirmed by the user), Hugging Face, Google AI Studio and Groq. Each key was tested against its provider on 2026-11-06.
- `gh` is not installed, so CI results are read from GitHub's public API.
- Local machine: Python 3.14 is the default and 3.11 is used for the project; Node 24; `ffmpeg`, `pnpm` and `make` are not installed. Phase 1 needs `ffmpeg` for codec simulation.
- Check that the git commit email (`darainhyder2004@gmail.com`) is on the GitHub account, or commits will not link to the profile.
- `npm audit` reports 10 moderate warnings, all from one advisory in `minimatch` (GHSA-g3hv-75wg-m249), used by ESLint. Dev-only, and its input is our own config; the only fix is a forced breaking change. Recheck when ESLint updates.
- The repo has no LICENSE, so nobody else may legally reuse the code yet. Decide before the Phase 10 launch.
