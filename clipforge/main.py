from __future__ import annotations
import argparse
import logging
from dotenv import load_dotenv
from clipforge.config import load_config
from clipforge.scheduler import run_forever, run_once


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="clipforge")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", metavar="URL",
                        help="process a single URL then exit (implies dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="run scheduler but never upload to YouTube")
    args = parser.parse_args()
    config = load_config(args.config)
    from clipforge.config import setup_file_logging
    setup_file_logging(config.storage_root)
    if args.once:
        run_once(config, args.once)
    else:
        run_forever(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
