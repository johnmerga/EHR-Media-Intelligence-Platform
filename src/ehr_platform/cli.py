"""Command-line entry point: ``ehr <stage>``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from functools import partial

from ehr_platform import pipeline
from ehr_platform.config import Settings, get_settings
from ehr_platform.storage import Store

Stage = Callable[[Settings, Store], object]

# Stages in the order they depend on each other.
STAGE_HELP = {
    "ingest": "Read and clean the raw files",
    "fhir": "Map clean records to FHIR R4 Bundles and validate them",
    "summarize": "Generate (or reuse cached) clinical summaries and evaluate them",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ehr", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    refreshable = [commands.add_parser(name, help=text) for name, text in STAGE_HELP.items()][-1:]
    refreshable.append(commands.add_parser("run", help="Run every stage in order"))
    for command in refreshable:
        command.add_argument(
            "--refresh-summaries",
            action="store_true",
            help="Ignore the summary cache and call the LLM again for every patient",
        )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    store = Store(settings.database_path)

    stages: dict[str, Stage] = {
        "ingest": pipeline.run_ingest,
        "fhir": pipeline.run_fhir,
        "summarize": partial(
            pipeline.run_summarize, refresh=getattr(arguments, "refresh_summaries", False)
        ),
    }
    selected = list(stages) if arguments.command == "run" else [arguments.command]
    for name in selected:
        stages[name](settings, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
