from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path

from event_radar.ai import EventAIService, build_openai_client
from event_radar.config import ConfigError, load_config, resolve_secrets
from event_radar.delivery import DeliveryError, send_email
from event_radar.env import load_dotenv_files
from event_radar.fetch import create_session
from event_radar.formatting import build_email_subject, format_daily_summary
from event_radar.pipeline import EventRadarPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the daily pipeline.")
    run_parser.add_argument("--config", required=True, help="Path to YAML or JSON config.")
    run_parser.add_argument("--date", help="Override target date in YYYY-MM-DD format.")
    run_parser.add_argument("--dry-run", action="store_true", help="Print output instead of sending email.")
    run_parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    validate_parser = subparsers.add_parser("validate-config", help="Validate config and required secrets.")
    validate_parser.add_argument("--config", required=True, help="Path to YAML or JSON config.")
    validate_parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(getattr(args, "verbose", False))

    try:
        if args.command == "validate-config":
            validate_config(args.config)
            print("Config is valid.")
            return 0

        if args.command == "run":
            run_pipeline(args.config, args.date, args.dry_run)
            return 0
    except (ConfigError, DeliveryError, ValueError) as exc:
        logging.error("%s", exc)
        return 1

    parser.print_help()
    return 2


def validate_config(config_path: str) -> None:
    config_path_obj = Path(config_path).expanduser().resolve()
    load_dotenv_files(Path.cwd() / ".env", config_path_obj.parent / ".env")
    load_config(config_path_obj)
    resolve_secrets()


def run_pipeline(config_path: str, raw_date: str | None, dry_run: bool) -> None:
    config_path_obj = Path(config_path).expanduser().resolve()
    load_dotenv_files(Path.cwd() / ".env", config_path_obj.parent / ".env")

    config = load_config(config_path_obj)
    secrets = resolve_secrets(require_smtp_password=not dry_run)

    if raw_date:
        target_date = date.fromisoformat(raw_date)
    else:
        target_date = datetime.now(config.zoneinfo).date()

    ai_client = build_openai_client(secrets.openai_api_key)
    ai_service = EventAIService(ai_client)
    session = create_session()

    pipeline = EventRadarPipeline(config, ai_service, session)
    events = pipeline.run(target_date)
    body = format_daily_summary(events, config, target_date)
    subject = build_email_subject(target_date)

    if dry_run:
        print(body)
        return

    if secrets.smtp_password is None:
        raise ConfigError("SMTP password is required for email delivery")
    send_email(config, subject, body, secrets.smtp_password)
