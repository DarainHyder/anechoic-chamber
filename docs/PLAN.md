# Anechoic Chamber — Build Plan

Nov 6, 2026 · @sawab\_e\_darain

## What Anechoic Chamber is and why it matters

Anechoic Chamber is an AI filter that removes the specific sounds a person with misophonia cannot bear (chewing, sniffing, pen clicks, typing) from what they listen to, while keeping voices and everything else intact. It ships first as a Chrome extension and web app, and later as a live-listening mode on phones.

**Name and tagline.** An anechoic chamber is a room built to absorb sound so nothing unwanted reaches the ear; this product builds one around the user. Tagline: *Hear everything except what hurts.* Repo: `anechoic-chamber`.

**The hidden problem.**

- **Common.** A UK study representative of the general population [estimated misophonia prevalence at 18%](https://pmc.ncbi.nlm.nih.gov/articles/PMC10032546/).
- **Unnamed.** [Fewer than 14% of that sample](https://www.sciencealert.com/misophonia-turns-out-to-be-way-more-common-than-we-thought) had heard of misophonia, so most sufferers have no word for what happens to them.
- **Misjudged.** It looks like rudeness: leaving the dinner table, snapping at siblings, failing to focus in an exam hall next to a sniffing classmate.
- **Worse in Pakistan.** Shared family meals, crowded classrooms and hostels, and no private space leave nowhere to escape.

**Why software can help now.**

- Research shows real-time selective hearing works. University of Washington's [Waveformer](https://targetsound.cs.washington.edu) was the first real-time, streaming target sound extraction model, and their [semantic hearing](https://washington.edu/news/2023/11/09/ai-noise-canceling-headphones) system lets headphone wearers choose which sounds pass through.
- A 2026 research system, [Sona](https://arxiv.org/pdf/2604.00447), attenuates bothersome sounds in real time on-device and lets users extend it over time.
- There is also evidence that people can learn to cope: the first randomised trial of CBT for misophonia found [short- and long-term efficacy](https://pmc.ncbi.nlm.nih.gov/articles/PMC8359510).

**The gap Anechoic Chamber fills.**

- **What exists is weak or out of reach.** The only shipped tools are a [Chrome extension that targets lip smacks with fixed frequency bands](https://chromewebstore.google.com/detail/lhefampilclchjahbmcdffjhlbempjal) and sender-side noise suppression in meeting apps, which does nothing when someone else's microphone or a video carries the chewing. The research systems above are prototypes you cannot install.
- **Anechoic Chamber is the first installable, user-side, trainable filter** that works on any audio the user plays, plus the social support (explain cards, coping tools) that a filter alone cannot give.

## Users, scope and design principles

The primary user is a teenager or young adult with misophonia who studies, works or lives in shared spaces and listens to a lot of video, lectures and calls. Secondary users are family members, teachers and colleagues who need to understand the condition.

**In scope for v1:** a Chrome extension filtering tab audio (YouTube, lecture sites, Meet and Zoom web); a web app for uploaded files and voice notes; 4 built-in triggers (chewing and eating, sniffing and breathing, pen and mouse clicks, keyboard typing); teach-your-own-trigger; the agent layer. **Later:** live microphone mode on phones, more triggers, desktop app for native Zoom or Teams. **Out of scope:** diagnosis, therapy, filtering other apps' audio system-wide on Android or iOS (the operating systems do not allow it).

Six principles every phase must respect:

1. **Voices are sacred.** Removing a trigger must never make speech harder to understand; speech intelligibility is a release gate.
2. **Artefacts are triggers too.** Gurgling or warbling left behind after removal can upset users as much as the original sound, so listening tests with real sufferers decide releases, not metrics alone.
3. **On-device audio.** Audio never leaves the user's device. Only anonymous settings and opt-in usage counts reach the server.
4. **User in control.** Every trigger has a slider (off, soften, remove, replace with soft noise) and a panic button that mutes everything.
5. **Not a medical product.** Screening is labelled non-diagnostic; coping content is framed as support and points to professionals for severe distress.
6. **Free and private by default.** No accounts needed for the extension; no ads; no audio stored.

## Product features

The MVP is one Chrome extension, one web app and one small model; everything else builds on them.

| Feature | What the user does | Release |
| --- | --- | --- |
| Tab filter | Clicks the Anechoic Chamber icon on any tab; triggers fade out while voices keep playing | MVP |
| Per-trigger sliders | Sets each trigger to off, soften, remove, or replace with soft brown noise | MVP |
| Panic button | One key mutes the tab instantly and fades back in | MVP |
| File and voice-note cleaner | Drops in an mp3, mp4 or WhatsApp voice note; downloads a cleaned copy | MVP |
| Teach your trigger | Records 3 to 5 clips, or types a description like "pen clicking"; Anechoic Chamber builds a personal filter | MVP |
| Trigger profiler | A 3-minute guided conversation and listening check builds the starting profile | v1 |
| Modes | "Exam", "family dinner", "study", each with its own filter settings | v1 |
| Weekly insights | On-device log summary: which triggers, when, how often | v1 |
| Coping coach | Short CBT-informed exercises, framed as support, never therapy | v1 |
| Explain-it card | Urdu and English message for family or teachers explaining misophonia | v1 |
| Self-check | Non-diagnostic questionnaire written for Anechoic Chamber (not a copied clinical scale) | v1 |
| Live mode | Phone microphone in, earbuds out; detect-and-mask first, true removal later | v2 |

**Two hard platform limits, stated up front:**

- The extension works in desktop Chrome, Edge and Brave. Chrome on Android has no extensions, and phones do not let one app filter another app's sound, so mobile users get the web app and live mode instead.
- Streaming sites that use DRM, such as Netflix, may block tab audio capture.

## Architecture and free stack

All audio processing runs inside the user's browser; the cloud only trains models (Kaggle), hosts model files (Hugging Face model repo) and runs the agent layer (Vercel). That split keeps audio private, latency low and hosting free.

&#91;embedded content: system architecture · on-device audio, cloud for training and agents\]

Only settings cross the browser boundary; models arrive once from the Hugging Face repo, which Kaggle training feeds.

| Layer | Choice | Notes (verify limits before relying on them) |
| --- | --- | --- |
| Extension | Chrome Manifest V3, TypeScript, Vite | Service worker gets a tab stream ID; an [offscreen document](https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture) captures and plays the processed audio |
| Audio engine | Shared `@anechoic-chamber/engine` package: AudioWorklet plus a Web Worker running ONNX Runtime Web (WASM SIMD, WebGPU when available) | Worklet and worker share a ring buffer via SharedArrayBuffer, which needs cross-origin isolation; fall back to message passing if unavailable |
| Web app | Next.js on Vercel Hobby | Same engine for file and voice-note cleaning |
| Model hosting | Hugging Face **model repo** (free) | Versioned ONNX files plus a `manifest.json`; Docker and Gradio Spaces are paid now, model repos are not |
| Agent API | FastAPI as a Vercel Python function, LangGraph | Gemini Flash free tier primary, Groq fallback, through one provider router |
| Accounts (optional) | Supabase free | Only to sync profiles across devices; the extension works without an account |
| Tracing | Langfuse free tier | Agent runs only, never audio |
| Training | Kaggle notebooks (you run them) | About 30 GPU hours a week and up to 12-hour sessions are commonly reported; Kaggle's docs say the quota floats, so check your account |

**Key design decision: triggers are embeddings.** The separation model is conditioned on a 512-number vector in CLAP's shared audio-text space, not on a fixed class list. Built-in triggers, typed descriptions and the user's own recordings all become vectors in that same space, so "teach your trigger" needs no retraining.

## Audio ML approach

Anechoic Chamber estimates the trigger sound and subtracts it, rather than rebuilding the whole soundtrack. When no trigger is present the model outputs near-silence and the user hears the original audio untouched, which is the safest way to protect voices.

**Task.** Given a mixture x and a trigger embedding e, predict the trigger signal t̂. The output is y = x − g·t̂, where the slider sets g (0 off, 0.5 soften, 1 remove). "Replace" mode subtracts t̂ and adds soft brown noise shaped by t̂'s loudness envelope.

**Model (student, runs in the browser).**

- **Base:** [Waveformer](https://github.com/vb000/Waveformer), the open-source causal model built for real-time streaming target sound extraction.
- **Change 1:** replace its fixed class conditioning with a FiLM layer fed by the 512-number CLAP embedding, so any trigger vector works.
- **Change 2:** add a small detection head that outputs "trigger active" probability per 10 ms; it drives insights, live-mode masking and high-band gating.
- **Sample rate:** the model runs at 16 kHz to stay cheap. Crunch and click energy above 8 kHz is handled by a band split: the high band is attenuated by a gain driven by the detection head. Phase 2 measures whether this is good enough or 24 kHz is needed.
- **Size target:** under 5 million parameters and under 10 MB after int8 quantisation; real-time factor under 0.3 on a mid-range laptop in WASM.

**Teacher (runs only on Kaggle).**

- [AudioSep](https://github.com/Audio-AGI/AudioSep), an MIT-licensed foundation model that separates sounds from a text description, generates pseudo-targets on real, unlabelled Creative Commons recordings where no ground truth exists.
- The student is trained on synthetic mixtures with exact targets first, then fine-tuned with knowledge distillation from the teacher on real-world audio, which closes the gap between clean training data and messy YouTube audio.

**Trigger embeddings.**

- **Built-in triggers:** CLAP audio embeddings averaged over many clips, computed on Kaggle with [`laion/clap-htsat-fused`](https://huggingface.co/docs/transformers/v4.50.0/model_doc/clap) and shipped as a small JSON file.
- **Typed descriptions:** a vocabulary of about 300 trigger phrases is embedded with CLAP's text encoder on Kaggle. At runtime, Gemini maps the user's free text to the closest phrases, and their stored embeddings are averaged, so no text encoder ever runs in the browser.
- **Recorded clips:** a small enrolment encoder in the browser maps the user's 3 to 5 clips into CLAP space. If CLAP's own audio encoder exports to ONNX at under 60 MB it is used directly; otherwise a compact encoder is distilled on Kaggle to imitate it.

**Losses.** Negative SI-SDR on the trigger estimate, plus a speech-preservation penalty (the error on speech-only regions of the output), plus binary cross-entropy for the detection head.

## Datasets and the mixture pipeline

Training data is built by mixing clean trigger clips into clean speech and music, so the exact trigger signal is always known. Public datasets supply most clips; your own recordings supply the local sounds (chewing roti, crisps, hostel pen clicks) that public sets miss.

| Role | Source | What it gives | Licence notes |
| --- | --- | --- | --- |
| Triggers | [ESC-50](https://github.com/karolpiczak/ESC-50) | 2,000 five-second clips in 50 classes, including keyboard typing, mouse click, breathing, coughing, sneezing, snoring, clock tick and drinking or sipping | CC BY-NC (fine for a free product; revisit if you ever charge) |
| Triggers and backgrounds | [FSD50K](https://zenodo.org/record/4060432) | 51,197 Freesound clips in 200 AudioSet classes | Dataset CC BY; each clip has its own CC licence, some non-commercial; check `vocabulary.csv` for chewing-related classes |
| Extra triggers | Freesound API | Targeted search for chewing, crunching, sniffing, pen clicks, lip smacks | Keep only CC0 and CC BY clips; log each clip's licence and author |
| Your recordings | Phone recordings with consent | 300+ clips of local triggers in real rooms, plus 50 "talking while eating" evaluation clips | Yours; get consent from everyone recorded |
| Speech | LibriSpeech; Mozilla Common Voice (Urdu and English) | Clean read speech in two languages | Verify each licence before download |
| Music and noise | MUSAN | Music, speech and noise beds | Verify licence |
| Rooms | OpenSLR room impulse responses | Real and simulated room echo | Verify licence |

**Mixture generator (`synth/mix.py`).**

1. Pick a 4-second bed: 1 to 2 speakers, optional music, optional background noise.
2. Add 0 to 2 trigger events at a trigger-to-bed ratio between −5 and +15 dB; 20% of samples have no trigger, which teaches the model to stay silent.
3. Apply a random room impulse response and gain.
4. Pass through a lossy codec (Opus or AAC via ffmpeg) at random bitrates, because YouTube and Meet audio is compressed.
5. Save mixture, exact trigger signal, per-10 ms activity labels and the trigger's CLAP embedding.

**Rules that prevent fake results.**

- Split train, validation and test by original source recording, never by clip, so no recording leaks across splits (ESC-50's folds already do this).
- Mix on the fly during training (dynamic mixing) to get effectively unlimited variety without storing terabytes.
- Keep a frozen real-world test set: your 50 recorded clips plus 30 Creative Commons videos. It is never used for tuning.
- Write a data card listing every source, count, licence and known gap.

## Real-time engine: extension and web app

The engine is one TypeScript package used by both the extension and the web app, so the model is tested once and shipped twice.

**Extension flow (Chrome Manifest V3).**

1. User clicks the Anechoic Chamber icon. The service worker calls `chrome.tabCapture.getMediaStreamId` for that tab and creates an offscreen document with the `USER_MEDIA` reason, the pattern in [Chrome's capture guide](https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture).
2. The offscreen document opens the tab stream. Capturing a tab silences its normal output, so the document must play audio itself; Anechoic Chamber plays the processed audio instead of the original, which is exactly the replacement we want.
3. An AudioWorklet writes 128-sample blocks into a ring buffer; an inference Web Worker reads 10 ms chunks, runs the ONNX model, writes the trigger estimate back; the worklet outputs x − g·t̂.
4. The popup shows sliders, the panic button and live trigger activity; settings sync through `chrome.storage`.

**Latency and safety rules.**

- **Budget:** under 80 ms end-to-end for tab audio, so speech stays in sync with video. Measure it with a click-track test, not by estimate.
- **Never block the audio thread.** If inference falls behind, the worklet passes the original audio through and reports a dropout; it never stalls or crackles.
- **Bypass on failure.** Any error returns the user to original audio within one block.
- **Fallbacks:** WebGPU if available, else WASM SIMD; SharedArrayBuffer if the page is cross-origin isolated, else message passing with a larger buffer.

**Web app.** Next.js page where the user drops a file or WhatsApp voice note. The same engine processes it faster than real time in a worker, previews before and after, and offers a download. Nothing is uploaded.

**Live mode (v2).** Phone microphone in, earbuds out through the web app. Bluetooth earbuds add far more delay than the 20 ms budget the [semantic hearing team](https://euronews.com/next/2023/12/20/prefer-birdsong-to-sirens-this-ai-powered-headphone-could-let-you-choose-which-noise-to-fi) worked within, so v2 starts with detect-and-mask (fade in soft noise when a trigger starts) and tests true removal with wired earbuds.

## Agent layer

The agents never touch audio; they read and write the user's settings and anonymous counts through typed tools. That keeps them useful, cheap on free LLM tiers and incapable of leaking sound.

| Agent | Job | Tools it can call |
| --- | --- | --- |
| Profiler | Short guided chat plus a listening check (plays sample sounds, asks for a 0 to 10 reaction) to build the starting trigger profile | `play_sample`, `set_trigger(level)`, `map_description_to_vocab` |
| Trigger mapper | Turns free text like "my brother eating chips" into the closest vocabulary phrases and their embeddings | `search_vocab`, `average_embeddings` |
| Context | Creates and switches modes (exam, family dinner, study) and suggests one when a known site or time matches | `create_mode`, `activate_mode` |
| Insight | Summarises the week from on-device counts: which triggers, when, how often | `get_weekly_counts` (sent only if the user opts in) |
| Coach | Short coping exercises drawn from a curated, cited library; detects distress keywords and points to professional help | `get_exercise`, `get_help_resources` |
| Explainer | Writes the Urdu or English "explain-it" card for family or teachers | `get_condition_facts` |

**Guardrails.**

- Coping content comes only from a curated library written from published sources (for example, the [CBT trial](https://pmc.ncbi.nlm.nih.gov/articles/PMC8359510)); the LLM may select and phrase, never invent techniques.
- The coach never diagnoses and never claims to treat; a fixed safety message triggers on crisis language.
- Every tool call is schema-validated; settings changes are shown to the user and undoable.
- Agent evals: 40 scripted conversations per agent with expected tool calls and forbidden outputs, run in CI with recorded model responses.

## Evaluation

A release must remove triggers, leave voices untouched and run in real time; the targets below are starting points that Phase 2's baseline will recalibrate.

| Metric | What it measures | Initial target |
| --- | --- | --- |
| Trigger SI-SDR improvement | How well the estimated trigger matches the true one (dB) | 8 dB or more on the synthetic test set |
| Trigger energy reduction | How much quieter triggers are after processing, in trigger-active frames | 12 dB or more |
| Speech intelligibility change (ESTOI) | Whether voices became harder to understand | Drop of 0.02 or less |
| False removal | Energy removed when no trigger is present | Below −30 dB relative to the input |
| Detection F1 | Accuracy of the trigger-activity head | 0.85 or more |
| Real-time factor | Processing time divided by audio duration, WASM on a mid-range laptop | 0.3 or less |
| End-to-end latency | Tab audio delay, measured with a click track | 80 ms or less |
| Model size | ONNX file after int8 quantisation | 10 MB or less |
| Listener annoyance | 0 to 10 rating by misophonia testers, original against processed | 50% lower on average |
| Artefact complaints | Share of test clips where testers report new unpleasant sounds | 10% or fewer |

**Baselines to beat, reported side by side:** the fixed band-stop filter approach used by the existing extension; the original Waveformer with one-hot classes; AudioSep offline as the quality ceiling.

**Listening protocol.** Ten testers recruited from online misophonia communities rate 20 paired clips each, blind to which is processed, with a stop button available at all times. Results are reported with medians and ranges, not just averages.

## Phase-by-phase plan

Eleven phases over about 18 weeks. Each ends with a gate and a review that may reorder or change later phases based on what was learned. Steps marked **\[Kaggle Kn\]** produce a notebook you run on Kaggle; work that depends on its outputs waits until you return them.

&#91;embedded content: roadmap · 11 phases over about 18 weeks\]

Phases 3 and 4 ship a working extension on the baseline model, so the hardest engineering risk is retired before the expensive training in Phase 5.

### Phase 0: Foundations (week 1)

- [ ] Monorepo: `extension`, `web`, `packages/engine`, `api`, `ml` (training code), `synth`, `eval`, `kaggle`, `docs`
- [ ] Accounts: GitHub, Vercel, Hugging Face, Google AI Studio, Groq, Kaggle (phone-verify now so GPU is enabled when needed), Freesound (API key needed in Phase 1)
- [ ] CI: lint, type-check, unit tests
- [ ] Privacy guard: recordings, consent notes and tester details stay in a git-ignored `private/` folder; a pre-push hook blocks them and CI re-checks, because the repo is public
- [ ] Recruit 5 to 10 misophonia testers; record their main triggers
- [ ] Record the first 100 local trigger clips with consent

**Gate:** CI green; testers booked; clips logged with consent notes.

### Phase 1: Data pipeline (weeks 2 to 3)

- [ ] Download scripts for ESC-50, FSD50K subsets, Freesound (CC0 and CC BY only), speech, music, room responses, each logging licences
- [ ] Mixture generator with dynamic mixing and codec simulation; data card
- [ ] **\[Kaggle K1\]** Build the trigger bank, compute CLAP embeddings for built-in triggers and the 300-phrase vocabulary, package everything as a private Kaggle dataset

**Gate:** unit tests confirm mixture loudness maths; a leakage test proves no source recording spans two splits; you listen to 20 random mixtures and confirm they sound realistic.

### Phase 2: Baseline model (weeks 4 to 5)

- [ ] Evaluation harness computing every metric in the Evaluation section
- [ ] Band-stop filter baseline
- [ ] **\[Kaggle K2\]** Train Waveformer with fixed classes on the 4 MVP triggers at 16 kHz
- [ ] Measure leftover trigger energy above 8 kHz; decide band-split versus 24 kHz and record the decision

**Gate:** baseline beats the band-stop filter on every removal metric with no speech-intelligibility loss; targets for later phases recalibrated from these numbers.

### Phase 3: Browser engine (weeks 6 to 7)

- [ ] Export the Phase 2 model to ONNX, quantise to int8, compare quality before and after
- [ ] `@anechoic-chamber/engine`: AudioWorklet, ring buffer, inference worker, bypass-on-failure
- [ ] Web app file and voice-note cleaner with before-and-after preview
- [ ] Benchmarks: real-time factor, latency, memory, across 3 machines

**Gate:** real-time factor 0.3 or less; quantised model within 0.5 dB of the full model; offline processing works with the network disabled.

### Phase 4: Chrome extension MVP (week 8)

- [ ] Tab capture via offscreen document; popup with sliders, panic button, activity meter
- [ ] Settings in `chrome.storage`; per-site memory

**Gate:** 30-minute soak tests on YouTube, Google Meet and a lecture site with zero audible dropouts; measured latency 80 ms or less.

### Phase 5: Embedding-conditioned model and teach-your-trigger (weeks 9 to 11)

- [ ] **\[Kaggle K3\]** Export or distil the enrolment encoder for recorded clips
- [ ] **\[Kaggle K4\]** Train the FiLM-conditioned student with the detection head
- [ ] **\[Kaggle K5\]** Generate AudioSep pseudo-targets on real Creative Commons audio; fine-tune the student by distillation
- [ ] Teach-your-trigger UI: record clips or type a description

**Gate:** all synthetic targets met; on 2 trigger classes held out from training, SI-SDR improvement of 4 dB or more (proves new triggers work without retraining).

### Phase 6: Listening test, round 1 (week 12)

- [ ] Blind paired test with testers using the protocol in the Evaluation section
- [ ] Analyse ratings and artefact complaints; write findings into PROGRESS.md

**Gate:** annoyance 50% lower and artefact complaints 10% or fewer. If missed, the review sends specific fixes back into Phase 5 before moving on.

### Phase 7: Agent layer (weeks 13 to 14)

- [ ] FastAPI plus LangGraph on Vercel; provider router; Langfuse
- [ ] Profiler, mapper, context, insight, coach and explainer agents with the curated coping library
- [ ] Agent eval suite

**Gate:** tool-call accuracy 95% or more; zero forbidden outputs (diagnosis, invented techniques, missing crisis message).

### Phase 8: Polish, accessibility, Urdu, privacy (week 15)

- [ ] Onboarding, Urdu interface, optional Supabase sync, privacy page
- [ ] Network audit proving no audio leaves the device

**Gate:** Lighthouse accessibility score 95 or more; network audit clean; testers complete onboarding unaided.

### Phase 9: Live mode v2 (weeks 16 to 17)

- [ ] Phone web app: microphone in, detect-and-mask out
- [ ] **\[Kaggle K6, optional\]** Train a tiny low-latency detector if the main model is too slow on phones
- [ ] Wired-earbud experiment with true removal

**Gate:** masking starts within 100 ms of trigger onset; tester feedback recorded.

### Phase 10: Launch (week 18 onward)

- [ ] Chrome Web Store listing (one-time $5 fee; until then, a GitHub sideload guide)
- [ ] Landing page, demo video, public evaluation report, model card on Hugging Face
- [ ] Beta with 30 to 50 users from misophonia communities

**Gate to call it v1:** 4-week retention of 40% or more and an average usefulness rating of 8/10 or more.

## Kaggle workflow

All training, distillation, embedding computation and large evaluations run on Kaggle in notebooks Claude Code writes and you run. Claude Code never simulates their results.

| Notebook | Phase | Purpose | Accelerator | Main outputs |
| --- | --- | --- | --- | --- |
| K1 | 1 | Build trigger bank; CLAP embeddings for triggers and vocabulary | GPU T4 | `trigger_bank/`, `embeddings.json`, data card |
| K2 | 2 | Train fixed-class Waveformer baseline | GPU T4 or P100 | `checkpoints/`, `metrics.json`, sample audio |
| K3 | 5 | Export or distil the enrolment encoder | GPU T4 | `enrol_encoder.onnx`, similarity report |
| K4 | 5 | Train the embedding-conditioned student with detection head | GPU T4 or P100 | `student.pt`, `student.onnx`, metrics |
| K5 | 5 | AudioSep pseudo-targets plus distillation fine-tune | GPU T4 or P100 | `student_kd.onnx`, before and after metrics |
| K6 | 9 (optional) | Tiny low-latency detector for phones | GPU T4 | `detector.onnx`, latency report |

**Every notebook follows the same contract.**

1. A first markdown cell stating purpose, inputs, accelerator, internet setting and expected runtime.
2. Pinned package versions, fixed seeds, and a GPU check that stops immediately if the GPU is missing (skipped only when `SMOKE_TEST = True`, so smoke tests can run on CPU).
3. All input paths as constants at the top, reading from `/kaggle/input/<dataset>/`.
4. Checkpoints saved every 20 to 30 minutes to `/kaggle/working/` and automatic resume, because sessions can end early and the weekly quota is limited.
5. Progress and estimated time remaining printed regularly.
6. Outputs written to `/kaggle/working/outputs/<task>/` with `manifest.json` (versions, hyperparameters, metrics, file list with checksums), `metrics.json` and a short `REPORT.md`, then zipped.
7. Secrets read through Kaggle's secrets feature, never typed into code.

**The hand-off loop.**

1. Claude Code writes `kaggle/notebooks/Kn_<task>.ipynb` and a `Kn_<task>_RUN.md` listing datasets to attach, accelerator, internet setting, expected runtime and what to download.
2. You run it on Kaggle, download the zip, unzip into `kaggle_outputs/Kn_<task>/`, and reply DONE.
3. Claude Code validates the manifest and checksums, writes an ingestion script with tests, and only then continues.

Budget the GPU quota: smoke-test each notebook on 1% of the data with the CPU first, and keep a full run under 8 hours.

## Testing strategy

Five layers, each at a different cadence, so slow GPU work and randomness never make everyday CI flaky.

| Layer | Covers | Tools | When |
| --- | --- | --- | --- |
| Unit and property tests | Mixture maths, loudness, splits, ring buffer, slider maths, settings | pytest with Hypothesis; Vitest | Every push |
| Model contract tests | ONNX input and output shapes, silence in gives near-silence out, deterministic output for a fixed input | onnxruntime (Python and Node) | Every push |
| Audio regression | 30 short reference clips processed by the current model; metrics compared with the stored baseline | `make eval-quick` | Every push touching `engine` or models |
| Browser and extension | Real Chrome running the extension on a local test page with known audio; checks capture, output, bypass on failure, latency | Playwright with Chromium | Every push touching `extension` or `engine` |
| Full evaluation and listening tests | Complete metrics on all test sets; blind tester sessions | Kaggle notebooks; tester protocol | End of model phases |

**Merge rule:** a pull request fails if any evaluation metric drops more than 0.5 dB or 0.01 ESTOI against the stored baseline, or if latency rises above budget.

**Agents:** recorded model responses replay in CI; live agent evals run before each phase gate.

## Repo layout and rules for Claude Code

Export this doc as Markdown to `docs/PLAN.md`; Claude Code works from it one phase at a time and records progress in `docs/PROGRESS.md`.

```text
anechoic-chamber/
  CLAUDE.md                 # rules below
  docs/PLAN.md              # this document
  docs/PROGRESS.md          # phase status, gate tables, decisions, open issues
  docs/BUILD_PROTOCOL.md    # the Claude Code prompt
  extension/                # Chrome MV3 extension (TypeScript, Vite)
  web/                      # Next.js web app (Vercel)
  packages/engine/          # AudioWorklet, ring buffer, ONNX worker, bypass logic
  api/                      # FastAPI + LangGraph agents (Vercel)
  ml/                       # PyTorch models, losses, training loops (imported by notebooks)
  synth/                    # dataset download scripts, mixture generator, data card
  eval/                     # metrics, reference clips, baselines, reports
  kaggle/notebooks/         # generated .ipynb files and RUN.md guides
  kaggle_outputs/           # you place unzipped Kaggle outputs here (git-ignored)
  private/                  # recordings, consent notes, tester details (git-ignored, never pushed)
  models/                   # versioned ONNX files and manifests (pushed to HF model repo)
```

**`CLAUDE.md` starter**

```markdown
# Anechoic Chamber: rules for every session
- Follow docs/BUILD_PROTOCOL.md. Read docs/PLAN.md and docs/PROGRESS.md first.
- Work only on the current phase. Never start the next phase without my approval.
- Heavy compute (GPU, training, >10 min CPU, >1 GB data, batch inference) goes to a Kaggle notebook I run. Never fake its results.
- Audio never leaves the user's device. No code may upload audio.
- The audio thread must never block; on any error, pass original audio through.
- Every change ships with tests. Run them before saying a task is done.
- Report metrics with numbers; never claim improvement without measuring.
- Free tiers only. No paid services, nothing needing a card.
- If unsure about an API or a limit, say "unverified" and check the docs.
```

## Risks, ethics and launch

The biggest technical risk is leftover artefacts that upset users; the biggest product risk is a large platform shipping a similar feature.

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Removal artefacts | Users hear new unpleasant sounds | Subtract-the-trigger design; listening tests gate releases; soften and replace modes |
| Speech damage | Voices become harder to understand | ESTOI gate; false-removal metric; the model is trained to output silence when unsure |
| Latency too high | Audio drifts from video | 80 ms budget measured in CI; smaller model or larger hop as fallback |
| Kaggle quota or session limits | Training stalls | Checkpoint and resume; CPU smoke tests first; runs under 8 hours |
| Dataset licences | Takedown or legal risk | Only CC0 and CC BY clips in released assets; non-commercial sets used for training a free product only; data card |
| Big platforms copy the feature | Fewer users | Personal trigger teaching, social tools (explain cards) and a focus on an underserved community |
| Store fees need a card | Cannot publish | GitHub sideload until the $5 Chrome Web Store fee can be paid |
| Mental-health harm | Distress unhandled | Curated coping content only, crisis message, no diagnosis or treatment claims |
| Privacy | Loss of trust | No audio leaves the device, proven by a network audit; minimal optional accounts |

**Launch plan.**

- Closed beta with testers from online misophonia communities.
- Open the GitHub repo with the evaluation report and a model card on Hugging Face.
- A demo video: a food vlogger talking while eating crisps, toggle on, crunch gone, voice clear.
- Publish the Chrome extension once the store fee is covered; share in misophonia communities and with university counselling services.

## Sources

Free-tier terms and licences change; recheck before relying on them.

- [Misophonia in the UK: prevalence study (PLOS ONE, 2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10032546/) and [ScienceAlert summary](https://www.sciencealert.com/misophonia-turns-out-to-be-way-more-common-than-we-thought)
- [CBT for misophonia: randomised clinical trial](https://pmc.ncbi.nlm.nih.gov/articles/PMC8359510)
- [Waveformer: real-time target sound extraction](https://targetsound.cs.washington.edu) and [code](https://github.com/vb000/Waveformer)
- [Semantic hearing (UW news)](https://washington.edu/news/2023/11/09/ai-noise-canceling-headphones) and [Euronews on the 20 ms budget](https://euronews.com/next/2023/12/20/prefer-birdsong-to-sirens-this-ai-powered-headphone-could-let-you-choose-which-noise-to-fi)
- [Sona: real-time multi-target sound attenuation](https://arxiv.org/pdf/2604.00447)
- [AudioSep: Separate Anything You Describe](https://github.com/Audio-AGI/AudioSep)
- [CLAP in Hugging Face Transformers](https://huggingface.co/docs/transformers/v4.50.0/model_doc/clap)
- [ESC-50](https://github.com/karolpiczak/ESC-50) and [FSD50K](https://zenodo.org/record/4060432)
- [Chrome extensions: audio recording and screen capture](https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture)
- [Existing Misophonia Mode extension](https://chromewebstore.google.com/detail/lhefampilclchjahbmcdffjhlbempjal)
- [Hugging Face Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview) (Docker and Gradio Spaces now need a paid plan)
- [Free cloud GPUs in 2026](https://gpuperhour.com/blog/free-cloud-gpus-and-credits) (Kaggle session limits; quota floats)
