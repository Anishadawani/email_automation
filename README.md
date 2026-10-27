# Candidate Email Automation (Gemini or Claude + Python)

Reads a CSV of screened candidates and uses the Gemini or Claude API to draft personalised recruitment emails
(shortlist invite, on-hold update, or polite rejection). **Nothing is sent without an explicit, reviewed approval.**

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in GEMINI_API_KEY (or ANTHROPIC_API_KEY) and SMTP_* if you will send
```
Settings are read from environment variables or the `.env` file.

For Gmail use an **App Password** (needs 2-Step Verification), `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`.

## Workflow
```bash
# 1. Generate drafts (nothing is sent)
python email_drafter.py draft --input candidates.csv --job-title "AI Intern" --company Virtuous

# 2. Open drafts.csv: edit any subject/body, and put "yes" in the `approved` column for rows to send.

# 3. Send only approved rows that are not already sent
python email_drafter.py send --drafts drafts.csv
```
Re-running `send` is safe: rows already marked `sent` are skipped, and the file is saved after every email.

Input CSV columns: `name, email, recommendation (shortlist|maybe|reject), summary`.
Output `drafts.csv` columns: `name, email, recommendation, subject, body, status, approved`.

Legacy one-shot mode: `draft ... --send` (asks for confirmation; add `--yes` to skip).

## Tests
```bash
pytest -q
```
Tests use a fake Claude client and fake sender, so no API key or SMTP server is needed.

## Design notes
- Per-recommendation rules in the prompt; the model is told not to invent dates, times or links.
- Candidate fields are passed as JSON data, not instructions (prompt-injection hardening); summaries are length-capped.
- Model output is validated (valid JSON, non-empty, length limit); a failure on one candidate is recorded in `status` and the batch continues.
- Email addresses are validated and header values stripped of newlines (header-injection protection).
- Duplicate addresses in the input are flagged; results are saved incrementally and atomically.
- Send has rate limiting (`--delay`), SMTP timeouts, STARTTLS (587) or SSL (465), and up-front config checks.
- Human review before sending is built into the workflow.
