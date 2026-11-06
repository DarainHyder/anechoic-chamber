# Tester intake form

Thank you for volunteering for Anechoic Chamber. This takes about 5 minutes. Answer only what you're comfortable with, except questions 1 and 2, which we need before you can take part.

1. **Are you 18 or over?** Yes / No
2. **Have you read the consent note and returned it?** Yes / No
3. **Which sounds affect you most?** Tick all that apply.
   - [ ] Chewing and eating
   - [ ] Sniffing and breathing
   - [ ] Pen or mouse clicks
   - [ ] Keyboard typing
   - [ ] Other: ______________
4. **Which one affects you most?** ______________
5. **Are there any sounds you never want to hear in a test?** We'll leave them out. ______________
6. **What do you usually listen on?** Earbuds / Over-ear headphones / Laptop speakers / Other
7. **Which languages do you mainly listen to?** ______________
8. **When are you usually free for a 30-minute session?** ______________
9. **Is there anything that would make the session easier for you?** ______________

This form is not a diagnosis, and you don't need a diagnosis to take part.

---

**For the organiser, not the tester:** copy the answers into `private/testers/tester_log.csv` under the tester's code, and keep the form in `private/testers/consent/`.

| Log column | What to write | Example |
| --- | --- | --- |
| `tester_id` | T plus 2 digits | `T01` |
| `status` | `invited`, `booked` or `withdrawn` | `booked` |
| `adult_confirmed` | `yes` from question 1 | `yes` |
| `consent_given` | `yes` once the consent note is back | `yes` |
| `consent_date` | Date on the consent note, as `YYYY-MM-DD` | `2026-11-10` |
| `main_triggers` | From question 3, separated by `;` | `chewing; sniffing` |
| `avoid_sounds` | From question 5, separated by `;` | `slurping` |
| `notes` | Anything useful, with no names or contact details | `prefers evenings` |
