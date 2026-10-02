# Email Triage Agent — Design & Plan

## Context
You want an agent on your Mac that triages your Gmail inbox automatically. `~/MyLearnings/email_triage_agent` is empty (new project).

**What you chose:**
- Triage = **classify + apply Gmail labels only**. It never sends, archives, trashes or deletes.
- **Gmail**, single account.
- Runs as a **scheduled background job** (launchd, every 15 min).
- **OpenAI API** for classification.
- **Python** (managed with uv; no LangChain).
- Default **6 categories**: Urgent, Needs-Reply, FYI, Newsletter, Promotions, Receipts-Notifications.

**Assumptions (correct me):**
- Only mail in the Inbox from the last 2 days is considered. Older backlog is ignored on the first run.
- At most 50 emails per run, to cap OpenAI cost and runtime.
- Exactly one category per email.

**Success:** new inbox mail gets a `Triage/<Category>` label within about 15 minutes, with no manual steps after setup. Failures show up in a log and a macOS notification instead of failing silently.

## Architecture

```
launchd (every 15 min) ──► `triage run`
                              │
         ┌────────────────────┼─────────────────────┐
   gmail_client          classifier             pipeline
   (fetch unlabeled,     (OpenAI structured     (fetch → classify → label,
    ensure labels,        output → category)      per-message error isolation)
    apply label)
```

**No state file. The run is idempotent through labels.** Each run searches
`in:inbox newer_than:2d -label:Triage/Urgent -label:Triage/Needs-Reply …`
(the query is built from config). A labeled email is never picked up again. An email whose classification failed stays unlabeled and is retried on the next run.

## Project layout
```
email_triage_agent/
  pyproject.toml            # uv; deps: openai, google-api-python-client, google-auth-oauthlib, pydantic, python-dotenv; dev: pytest
  config.toml               # categories (name + description for the prompt), model, lookback_days, max_per_run, label_prefix
  .env.example              # OPENAI_API_KEY=
  .gitignore                # .env, credentials.json, token.json
  README.md                 # Google Cloud OAuth setup steps, usage
  src/email_triage/
    cli.py                  # `triage auth | run [--dry-run] [--limit N] | install-schedule | uninstall-schedule`
    config.py               # load config.toml → pydantic models; build Literal of category names
    gmail_client.py         # OAuth (scope gmail.modify), search query builder, fetch message (headers + plain-text body), ensure_labels(), apply_label()
    classifier.py           # OpenAI structured output → Classification{category, confidence, reason}; body truncated to ~4k chars
    pipeline.py             # orchestrates one run; returns summary counts; per-message try/except
    notify.py               # macOS notification via osascript on run-level failure (e.g. auth expired)
    launchd.py              # renders ~/Library/LaunchAgents/local.email-triage.plist (StartInterval 900), launchctl load/unload
  tests/
    test_config.py  test_query.py  test_classifier.py  test_pipeline.py
```

## Key decisions
- **Auth:** you create a Google Cloud project and a Desktop OAuth client, then download `credentials.json` (steps in the README). `triage auth` runs the browser consent flow once and saves a refresh token to `~/Library/Application Support/email-triage/token.json` (chmod 600). The scope is `gmail.modify`: it can read and label but cannot permanently delete. The code only ever calls `labels.create`, `messages.list/get` and `messages.modify` (addLabelIds).
- **OpenAI:** uses `client.chat.completions.parse(response_format=Classification)` with Pydantic. The model name lives in config, defaulting to a small, cheap model (`gpt-5.4-mini`). The prompt includes sender, subject, date, the List-Unsubscribe header if present, and the truncated body.
- **Prompt injection:** email content is untrusted. The model's output is limited to the category enum, and the agent has no other tools, so the worst case is a wrong label.
- **Secrets:** `OPENAI_API_KEY` is read from `.env` in the project dir, because launchd does not inherit your shell env.
- **Logging:** a rotating log at `~/Library/Logs/email-triage/triage.log`. Each run logs one line per email (id, category, confidence) and a summary.
- **Errors:** a per-message failure (OpenAI error or malformed email) is logged and skipped, then retried next run. A run-level failure (auth refresh failed, no network, missing key) is logged, triggers a macOS notification, and exits non-zero.
- **`--dry-run`** prints the classifications without touching Gmail. Use it to tune category descriptions before going live.

## Implementation order (TDD where logic exists)
1. `git init`, uv project scaffold, `.gitignore`, `config.toml`, and save this spec to `docs/superpowers/specs/2026-10-02-email-triage-design.md`.
2. `config.py` + tests (load, validate unique categories).
3. Query builder in `gmail_client.py` + tests.
4. `classifier.py` + tests with a mocked OpenAI client.
5. `pipeline.py` + tests with fake Gmail and fake classifier: labels applied, failures isolated, dry-run makes no changes, max_per_run respected.
6. Real Gmail calls (auth, fetch, MIME body extraction, ensure_labels, apply_label).
7. `cli.py`, `notify.py`, `launchd.py`.
8. README with the Google Cloud setup walkthrough.

## Verification
- `uv run pytest`: all tests pass.
- `uv run triage auth`: browser consent works and the token is saved.
- `uv run triage run --dry-run --limit 10`: sensible categories printed, nothing changed in Gmail.
- `uv run triage run --limit 10`: `Triage/*` labels appear in Gmail. A second run processes 0 messages (idempotency).
- `uv run triage install-schedule`: `launchctl list | grep email-triage` shows the job, and `tail -f ~/Library/Logs/email-triage/triage.log` shows a run within 15 min.
- Failure path: temporarily set an invalid `OPENAI_API_KEY`; messages are skipped and logged, and nothing is labeled wrongly.

## Manual steps you'll need to do
1. Create a Google Cloud project, enable the Gmail API, configure the OAuth consent screen (External, add yourself as a test user), create a **Desktop app** OAuth client, and download `credentials.json` into the project dir.
2. Put `OPENAI_API_KEY` in `.env`.
