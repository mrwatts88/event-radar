# Personal Event Radar – Spec

## Overview
Build a minimal system that sends a daily summary of relevant events based on user-defined interests. The system combines deterministic sources with optional AI-based discovery.

---

## Goals
- Deliver a daily list of “today’s events”
- Avoid manual checking of apps/websites
- Keep system simple, deterministic, and debuggable
- No UI required

---

## Non-Goals
- No mobile app
- No real-time updates
- No complex scheduling engine
- No multi-user support

---

## Architecture

### 1. Configuration Layer
A single config file (YAML or JSON) defines:

- categories
- sources per category
- filters (teams, keywords)
- delivery method

Example structure:

```
categories:
  sports:
    sources:
      - url: "https://www.espn.com/nba/team/schedule/_/name/mil"
    filters:
      include_keywords: ["Bucks"]

  space:
    sources:
      - url: "https://www.nasa.gov/launchschedule/"
      - url: "https://www.spacex.com/launches/"

  motorsports:
    sources:
      - url: "https://www.formula1.com/en/racing-calendar.html"

discovery:
  enabled: true
  prompt_categories: ["sports", "space", "poker", "motorsports"]

delivery:
  method: "email"
  email:
    to: "your@email.com"
```

---

### 2. Fetch Layer

- Runs on a daily cron job
- Fetches raw HTML from each configured source
- Uses simple HTTP client (requests)

Requirements:
- Retry once on failure
- Timeout after reasonable duration (e.g., 10s)

---

### 3. Content Extraction

Before sending to AI:
- Strip scripts/styles
- Extract visible text only
- Truncate to reasonable size (e.g., 10–20k chars)

Goal:
- Reduce noise
- Reduce token usage
- Improve parsing quality

---

### 4. AI Parsing Layer

For each source:
- Send cleaned text to AI
- Request structured output

Required output format:

```
{
  "events": [
    {
      "title": "string",
      "datetime": "ISO8601",
      "category": "string",
      "source": "string",
      "confidence": 0.0-1.0
    }
  ]
}
```

Prompt requirements:
- ONLY include events happening today (local time)
- Ignore future or past events
- Ignore vague mentions without a clear date/time
- Prefer scheduled events

---

### 5. Discovery Layer (Optional)

If enabled:
- Run a separate AI query:

“What notable events are happening today in: [categories]?”

Same structured output format.

Purpose:
- Capture events not present in canonical sources

---

### 6. Merge & Deduplication

- Combine parsed events + discovered events
- Deduplicate based on:
  - title similarity
  - time proximity

- Tag events:
  - "core" (from sources)
  - "discovered" (from AI search)

---

### 7. Filtering

Apply config filters:
- Include only matching keywords (if specified)
- Drop low-confidence events (threshold configurable)

---

### 8. Sorting

- Sort events by datetime ascending
- Group optionally by category

---

### 9. Output Formatting

Plain text format:

```
TODAY – {date}

CORE
🏀 Bucks vs Heat – 7:00 PM
🚀 SpaceX Launch – 9:12 PM

DISCOVERED
♠️ WSOP Event #12 Day 2
```

Guidelines:
- Keep concise
- Include emoji per category (optional)
- Always include time if available

---

### 10. Delivery

#### Email (Primary)
- Use SMTP or provider (SendGrid, etc.)
- Subject: “Today’s Events – {date}”
- Body: formatted output

#### SMS (Optional Future)
- Send only top N events
- Shortened format

---

## Scheduling

- Run via cron once daily (morning)
- Optional second run (evening preview)

---

## Error Handling

- If a source fails → skip and continue
- If AI parsing fails → log and skip
- If all sources fail → still attempt discovery layer

---

## Logging

- Log fetched URLs
- Log AI responses (truncated)
- Log final event count

---

## Extensibility

Future additions:
- Add new categories via config only
- Add new sources without code changes
- Add Slack/Push notifications
- Add “tomorrow preview” mode

---

## Key Principles

- Keep system deterministic where possible
- Use AI only for parsing and discovery
- Avoid overengineering
- Prefer simplicity over completeness

---

## Minimal Tech Stack

- Python
- requests
- BeautifulSoup (or equivalent)
- OpenAI API (structured output)
- cron
- SMTP / email provider

---

## Success Criteria

- Runs daily without intervention
- Produces relevant, clean event list
- Misses are understandable and fixable
- No need to open external apps
