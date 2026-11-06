# Recording guide: your first 100 clips

These clips teach the model what real trigger sounds are like in local homes and hostels, such as chewing roti, crisps and pen clicks. Public datasets don't cover these sounds well.

## Before you start

1. Create these folders inside the project. Git ignores them, so they never reach GitHub.

   ```text
   private/recordings/clips/      the audio files
   private/recordings/consent/    signed consent notes
   ```

2. Copy `docs/recording/clip_log_template.csv` to `private/recordings/clip_log.csv`.
3. Get consent from everyone who will be heard, using [consent_note.md](consent_note.md). Never record anyone secretly. Anyone under 18 also needs a parent or guardian's consent.
4. Give each person a code, such as P01 or P02. Use `self` for yourself. Keep names out of the log.

If these sounds upset you too, record in short sessions and take breaks. There's no deadline that justifies distress.

## What to record

| Trigger | `trigger` value | Suggested clips | Examples |
| --- | --- | --- | --- |
| Chewing and eating | `chewing_eating` | 40 | Roti, rice, crisps, apples, gum, lip smacking, slurping tea |
| Sniffing and breathing | `sniffing_breathing` | 20 | Sniffing, nose breathing, throat clearing |
| Clicks | `clicks` | 20 | Pen clicks, mouse clicks |
| Typing | `typing` | 20 | Laptop keyboard, desktop keyboard, phone tapping |

The mix is a suggestion. The gate only counts the 100 total, but the checker shows your count for each trigger so you can see any gaps.

## How to record

- **Length:** 10 to 30 seconds per clip.
- **One trigger per clip:** don't mix chewing and typing in the same clip.
- **Talking:** avoid it for now. If someone talks, keep the clip and mark `contains_speech` as `yes`.
- **Distance:** vary it. Most clips at 30 cm to 1 metre, some further away.
- **Rooms:** use at least 3 different places, such as a kitchen, a bedroom and a classroom or hostel room.
- **Background:** normal room sound is fine. Turn off music and TV.
- **Phone settings:** use the highest quality setting, and turn off any noise reduction if your recorder app has that option.
- **Moving files:** use a cable or your own cloud storage. Don't send clips through WhatsApp, because it compresses audio.

## Filling in the log

Add one row per clip. Dates must stay as `YYYY-MM-DD`; Excel may change them, so format that column as Text, or edit the file in VS Code. If you use Excel, save with **CSV UTF-8**.

| Column | What to write | Example |
| --- | --- | --- |
| `clip_id` | C plus 4 digits, never reused | `C0001` |
| `file` | File name inside `clips/` | `chew_roti_01.m4a` |
| `trigger` | A value from the table above | `chewing_eating` |
| `session_id` | S plus digits. One session is one sitting in one place | `S01` |
| `recorded_on` | Date of recording | `2026-11-07` |
| `room` | Short description | `kitchen` |
| `device` | Short description | `phone_a` |
| `people` | Everyone heard, separated by `;` | `self;P01` |
| `consent_given` | `yes`. If consent is missing, delete the clip | `yes` |
| `consent_note` | How and when consent was given | `signed form 2026-11-07` |
| `contains_speech` | `yes` or `no` | `no` |
| `notes` | Anything useful, without names | `crisps, loud` |

Session IDs matter. Clips from one session sound alike, so Phase 1 uses them to stop one sitting appearing in both the training data and the test data.

## Check your work

Run this from the project folder at any time:

```sh
python -m scripts.check_clips
```

It lists any problems and counts your valid clips. `--gate` also requires 100 valid clips.

## Withdrawals

If someone withdraws consent, delete their clips, remove their rows from the log and tell Claude Code, so the clips are left out of any future training data.
