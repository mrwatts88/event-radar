# Event Radar

Event Radar is a small Python CLI that fetches configured sources, extracts visible text, asks OpenAI to return structured events happening today, optionally discovers additional events with web search, deduplicates the results, and emails a daily summary.

## Requirements

- Python 3.11+
- `OPENAI_API_KEY`
- `EVENT_RADAR_SMTP_PASSWORD`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Configure

1. Copy [event_radar.example.yaml](/Users/mattwatts/code/events/event_radar.example.yaml) to your own config path.
2. Copy [.env.example](/Users/mattwatts/code/events/.env.example) to `.env`.
3. Fill in your OpenAI and SMTP credentials.

The CLI automatically loads `.env` from the current working directory and the config directory if present.

Config files may also reference environment variables with `${ENV_VAR}` placeholders if you need them, but the default setup just uses a single config file locally and in GitHub Actions.

## Commands

Validate configuration and required secrets:

```bash
event-radar validate-config --config event_radar.example.yaml
```

Run the pipeline without sending email:

```bash
event-radar run --config event_radar.example.yaml --dry-run
```

Run for a specific date:

```bash
event-radar run --config event_radar.example.yaml --date 2026-04-01
```

## Cron

Run every morning at 7:00 AM local time:

```cron
0 7 * * * cd /Users/mattwatts/code/events && /Users/mattwatts/code/events/.venv/bin/event-radar run --config /Users/mattwatts/code/events/event_radar.example.yaml >> /Users/mattwatts/code/events/event-radar.log 2>&1
```

## GitHub Actions

The repository includes a scheduled workflow at [.github/workflows/daily-event-radar.yml](/Users/mattwatts/code/events/.github/workflows/daily-event-radar.yml). It runs daily at `13:00 UTC`, which is `8:00 AM` during daylight time in Chicago and `7:00 AM` during standard time.

Set these repository secrets before enabling the workflow:

- `OPENAI_API_KEY`
- `EVENT_RADAR_SMTP_PASSWORD`

The workflow uses [event_radar.yaml](/Users/mattwatts/code/events/event_radar.yaml), so the same config works both locally and in GitHub Actions.

## Notes

- Source failures are logged and skipped.
- Discovery still runs if all configured sources fail.
- Email is the only delivery method in v1.
