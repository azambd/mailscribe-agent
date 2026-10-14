"""
Mail-to-Sheet AI Agent — CLI entry point.

Usage:
    python main.py --mode dry-run       # no credentials needed, see README
    python main.py --mode once          # one real fetch -> extract -> sync cycle
    python main.py --mode schedule      # runs continuously on the configured interval
"""

import argparse
import logging

from src.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Mail-to-Sheet AI Agent")
    parser.add_argument(
        "--mode",
        choices=["dry-run", "once", "schedule"],
        default="dry-run",
        help="dry-run: sample emails, no credentials needed. once: single real run. schedule: run continuously.",
    )
    parser.add_argument("--config", default="config/schema.example.yaml", help="Path to the YAML schema/config file")
    args = parser.parse_args()

    if args.mode == "dry-run":
        from src.dry_run import main as dry_run_main
        dry_run_main()
        return

    settings = load_settings(yaml_path=args.config)

    if args.mode == "once":
        from src.agent import MailToSheetAgent
        agent = MailToSheetAgent(settings)
        summary = agent.run_once()
        print(summary)

    elif args.mode == "schedule":
        from src.scheduler import run_scheduled
        run_scheduled(settings)


if __name__ == "__main__":
    main()
