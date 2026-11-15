# How to run K1: data bank

K1 downloads the training corpora, collects Creative Commons trigger clips from Freesound and filters them with CLAP, locks the real-world test set, computes CLAP embeddings, and checks 200 generated mixtures with an independent judge. Kaggle's menus change from time to time, so the exact labels below may differ slightly.

## Before you start

- **Code pushed:** the notebook clones the repo at the commit written in its first code cell, so that commit must already be on GitHub.
- **Phone-verified Kaggle account:** needed for GPU and internet.
- **No leftover runs:** if an older K1 version is still queued or running, cancel it first, to save GPU quota.

## 1. Create the notebook

1. On [kaggle.com](https://www.kaggle.com), choose **Create > New Notebook**. If you're reusing the old K1 notebook, choose **File > Import Notebook** and replace it instead.
2. Upload `kaggle/notebooks/K1_data_bank.ipynb` from this repo.

## 2. Settings (right-hand panel)

| Setting | Value |
| --- | --- |
| Accelerator | **GPU T4 x2** (or P100) |
| Internet | **On** |
| Persistence | Files only, if offered |

## 3. Secret

1. Choose **Add-ons > Secrets**.
2. Make sure `FREESOUND_API_KEY` exists and is attached to this notebook. Its value is the Freesound key from your local `.env`.

## 4. Datasets to attach

None. Everything downloads with internet on:

- [ESC-50](https://github.com/karolpiczak/ESC-50)
- [FSD50K labels](https://zenodo.org/records/4060432)
- [LibriSpeech](https://www.openslr.org/12/)
- [MUSAN](https://www.openslr.org/17/)
- [Room impulse responses](https://www.openslr.org/28/)
- [Freesound](https://freesound.org)

## 5. Smoke test (about 10 to 20 minutes)

1. Leave `SMOKE_TEST = True` in the first code cell.
2. Choose **Run All**.
3. The last cell should print `SMOKE OK`. If any cell fails, copy the error and the last 30 lines of output, and send them to me.

## 6. Full run (about 2 hours)

1. Set `SMOKE_TEST = False`.
2. Choose **Save Version > Save & Run All (Commit)**. It starts a fresh background session, so you can close the tab and stop the interactive session.
3. When the version shows as complete, open it.

**If the run stops early:** open the stopped version, choose **Add Input**, and add that version's output with the name `k1-resume`. Then run again; it continues where it stopped.

## 7. What to download

1. In the finished version, open the **Output** tab and download **`K1_data_bank_outputs.zip`** (about 10 to 60 MB). You don't need anything else.
2. Put the zip in the project's `kaggle_outputs/` folder (note the underscore: **not** `kaggle/outputs/`). Either unzip it so the files sit directly in `kaggle_outputs/K1_data_bank/`, or leave it zipped and I'll unzip it.
3. Keep this Kaggle notebook version. Its output (the trigger bank audio) becomes K2's input in Phase 2.

Then reply **DONE**.
