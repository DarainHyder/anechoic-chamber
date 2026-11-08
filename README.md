# Anechoic Chamber

*Hear everything except what hurts.*

Anechoic Chamber is a privacy-first AI filter for misophonia. It removes specific trigger sounds, such as chewing, sniffing, clicks and typing, from what you listen to, while keeping voices intact. All audio processing happens on your device.

**Status: early development. Nothing is usable yet.**

## Layout

| Folder | Contents |
| --- | --- |
| `extension/` | Chrome extension |
| `web/` | Web app |
| `packages/engine/` | Shared audio engine |
| `api/` | Agent API |
| `ml/` | Model and training code |
| `synth/` | Dataset scripts and mixture generator |
| `eval/` | Metrics and baselines |
| `kaggle/notebooks/` | Training notebooks and run guides |
| `models/` | Model manifests (model files live on Hugging Face) |
| `scripts/` | Repo checks and tools |
| `docs/` | Guides |

## Development

Requires Node 24 and Python 3.11.

```sh
npm install                  # also turns on the pre-push privacy hook
npm run lint
npm run typecheck
npm test

py -3.11 -m venv .venv       # on macOS or Linux: python3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m mypy
.venv/Scripts/python -m pytest
```

## Privacy

This repo is public. Recordings, consent notes and tester details stay in the git-ignored `private/` folder. A pre-push hook blocks them, and CI checks again.
