"""Command-line entry point: ``ehr <stage>``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from ehr_platform import pipeline
from ehr_platform.config import Settings, get_settings
from ehr_platform.storage import Store

Stage = Callable[[Settings, Store], object]

# Stages in the order they depend on each other.
STAGES: dict[str, tuple[Stage, str]] = {
    "ingest": (pipeline.run_ingest, "Read and clean the raw files"),
    "fhir": (pipeline.run_fhir, "Map clean records to FHIR R4 Bundles and validate them"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ehr", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_, description) in STAGES.items():
        commands.add_parser(name, help=description)
    commands.add_parser("run", help="Run every stage in order")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    store = Store(settings.database_path)

    selected = list(STAGES) if arguments.command == "run" else [arguments.command]
    for name in selected:
        stage, _ = STAGES[name]
        stage(settings, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
