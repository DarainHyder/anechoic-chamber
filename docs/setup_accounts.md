# Account setup

Create these accounts now, so nothing blocks later phases. All of them should be free. **If any site asks for a card, stop and tell Claude Code instead of entering one.** Free-tier terms change, so the limits in `docs/PLAN.md` need rechecking when each service is first used.

| Service | Sign up | Needed from | Key to create now |
| --- | --- | --- | --- |
| Freesound | [freesound.org](https://freesound.org/home/login/) | Phase 1 | Yes: [apply for an API key](https://freesound.org/apiv2/apply/), then save it as `FREESOUND_API_KEY` |
| Kaggle | [kaggle.com](https://www.kaggle.com/settings) | Phase 1 | No. Verify your phone number in Settings; GPUs and notebook internet access depend on it |
| Hugging Face | [huggingface.co](https://huggingface.co/join) | Phase 3 | No |
| Vercel | [vercel.com](https://vercel.com/signup) | Phase 3 | No. Sign in with GitHub and pick the Hobby plan |
| Google AI Studio | [aistudio.google.com](https://aistudio.google.com/apikey) | Phase 7 | No |
| Groq | [console.groq.com](https://console.groq.com/keys) | Phase 7 | No |

## Storing keys

1. Copy `.env.example` to a new file named `.env` in the project folder.
2. Put each key after its `=` sign in `.env`.
3. Leave `.env.example` empty.

`.env` is ignored by git, and the pre-push hook blocks it from being pushed. Keys for Kaggle notebooks go into Kaggle's own Secrets feature, never into the notebook.

**Never paste a key into a chat, an issue or a code file.** If a key is exposed, delete it on the provider's site and create a new one.

## When you're done

Tell Claude Code which accounts are ready. You don't need to share the keys.
