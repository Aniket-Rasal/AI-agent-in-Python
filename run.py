from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from app.agent.runner import AgentRunner
from app.config import Config
from app.database.repository import Repository
from app.logging_config import configure_logging
from app.scheduler import run_forever
from app.sources.local import LocalDocumentSource
from app.sources.mca import MCADocumentSource


def _make_source(name: str, config: Config):
    return LocalDocumentSource(config) if name == "local" else MCADocumentSource(config)


def _print_demo(config: Config) -> int:
    sample = Path(__file__).resolve().parent / "samples" / "Companies Act, 2013.pdf"
    if not sample.is_file():
        print(f"Demo sample PDF is missing: {sample}")
        return 1

    # The demo has isolated SQLite state so it is repeatable and doesn't change
    # the normal MCA collection count. Artifacts still go to data/documents/Acts.
    demo_run_id = uuid.uuid4().hex[:12]
    repository = Repository(config.data_dir / "demo_state" / f"companies-act-demo-{demo_run_id}.sqlite3")
    source = LocalDocumentSource(config, files=[sample])
    source.name = "LOCAL DEMO"
    runner = AgentRunner(config, repository=repository, source=source)
    outcome = runner.run_once(owner="local-demo")
    status = repository.status()
    categories = repository.category_counts()

    print("=" * 42)
    print("MCA AI DOCUMENT AGENT")
    print("=" * 42)
    print("Source: LOCAL DEMO")
    print(f"Discovered: {runner.last_discovered}")
    print(f"Downloaded: {status['downloaded']}")
    print(f"OCR Processed: {status['ocr_processed']}")
    print(f"Classified: {status['classified']}")
    print(f"Errors: {status['errors']}")
    print("Classification:")
    for category, amount in sorted(categories.items()):
        print(f"  {category}: {amount}")
    print(f"Document limit: {status['downloaded']} / {config.max_documents}")
    success = outcome in ("complete", "limit") and status["errors"] == 0 and status["classified"] == 1
    print(f"Status: {'SUCCESS' if success else 'PARTIAL'}")
    print("=" * 42)
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and process Companies Act documents from MCA or a local PDF folder")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one discovery and processing cycle")
    mode.add_argument("--demo", action="store_true", help="Run the isolated local Companies Act PDF demonstration")
    mode.add_argument("--status", action="store_true", help="Show persisted processing status")
    mode.add_argument("--process-existing", action="store_true", help="Resume downloaded files without discovering more")
    mode.add_argument("--import-pdf", metavar="PATH", help="Import and process one local PDF")
    mode.add_argument("--import-dir", metavar="PATH", help="Import and process PDFs from a folder")
    parser.add_argument("--source", choices=("mca", "local"), default="mca", help="Use the MCA website or LOCAL_PDF_DIR as the source")
    parser.add_argument("--title", help="Title to record for --import-pdf (defaults to the filename)")
    args = parser.parse_args()
    if args.title and not args.import_pdf:
        parser.error("--title can only be used with --import-pdf")
    config = Config.from_env()
    config.create_directories()
    configure_logging(config.log_path)
    repository = Repository(config.database_path)
    if args.status:
        status = repository.status()
        status["remaining"] = max(0, config.max_documents - status["downloaded"])
        for key, value in status.items():
            print(f"{key}: {value}")
        return 0

    if args.demo:
        return _print_demo(config)

    if args.import_pdf:
        outcome = AgentRunner(config, repository=repository).import_local_pdf(args.import_pdf, args.title)
        return 0 if outcome in ("complete", "duplicate", "limit", "locked") else 1
    if args.import_dir:
        outcome = AgentRunner(config, repository=repository).import_local_directory(args.import_dir)
        return 0 if outcome in ("complete", "limit", "locked") else 1
    source = _make_source(args.source, config)
    runner = AgentRunner(config, repository=repository, source=source)
    if args.once or args.process_existing:
        outcome = runner.run_once(process_existing_only=args.process_existing, source=source)
        if args.source == "local":
            print(f"Source: LOCAL\nDiscovered: {runner.last_discovered}\nStatus: {outcome.upper()}")
        return 0 if outcome in ("complete", "limit", "locked") else 1
    run_forever(config, runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
