# Email Triage Agent

Runs on your Mac every 15 minutes, classifies new Gmail inbox mail with OpenAI, and applies one
`Triage/<Category>` label per email. It **only reads and labels**: it never sends, archives,
trashes or deletes.

Categories (edit them in `config.toml`): Urgent, Needs-Reply, FYI, Jobs, Newsletter, Promotions,
Receipts-Notifications.

Results from a real run (redacted): [docs/sample-output.md](docs/sample-output.md).

## One-time setup

### 1. Google OAuth client (`credentials.json`)
1. Go to <https://console.cloud.google.com/> and create a project (e.g. "email-triage").
2. **APIs & Services → Library**: search for **Gmail API** and click **Enable**.
3. **Google Auth Platform / OAuth consent screen**: choose User type **External** and fill in the app name and your email.
   Under **Audience → Test users**, add your Gmail address.
4. **Clients → Create client**: set Application type to **Desktop app** and create it. **Download JSON**.
5. Save the downloaded file as `credentials.json` in this directory. It is git-ignored.

> While the app is in "Testing" status, Google expires refresh tokens after 7 days. If runs start
> failing with an auth error (you'll get a macOS notification), run `uv run triage auth` again.
> Publishing the app ("In production") removes the 7-day limit. For personal use you can do this
> without verification; you'll just click through an "unverified app" warning.

### 2. OpenAI key
```sh
cp .env.example .env    # then put your key in .env
```

### 3. Authorize and try it
```sh
uv sync
uv run triage auth                      # opens a browser; token saved to ~/Library/Application Support/email-triage/
uv run triage run --dry-run --limit 10  # prints categories, changes nothing
uv run triage run --limit 10            # applies labels
```

### 4. Schedule it
```sh
uv run triage install-schedule          # launchd job, every 15 min (--interval to change)
launchctl list | grep email-triage      # confirm it's loaded
uv run triage uninstall-schedule        # to remove
```

## How it works
- Each run searches `in:inbox newer_than:<lookback_days>d` and excludes anything that already has a
  `Triage/*` label, so there is no state file. An email that fails to classify stays unlabeled and
  is retried on the next run.
- At most `max_per_run` (default 50) emails are processed per run.
- The model's answer is restricted to the configured category names (structured output).
- Email content is treated as untrusted. The agent has no tools beyond labeling, so the worst a
  malicious email can do is get itself mislabeled.

## Logs and troubleshooting
- Run log: `~/Library/Logs/email-triage/triage.log` (one line per email, plus a summary per run)
- launchd stdout/stderr: `~/Library/Logs/email-triage/launchd.*.log`
- A run that fails outright (auth, missing key, network), or one where every email failed, shows a
  macOS notification and exits non-zero.

## Tuning
Edit category descriptions in `config.toml`. They go straight into the prompt. Check the effect
with `--dry-run`. Changing category *names* creates new labels; old labels are left in place.

## Development
```sh
uv run pytest
```
