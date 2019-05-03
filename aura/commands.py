import sys
import json
import time
import pprint
import copy
from pathlib import Path

import click

from .package_analyzer import Analyzer
from .analyzers.python import execution_flow
from .scan_results import ScanResults
from .uri_handlers.base import URIHandler, ScanLocation

from . import config
from . import exceptions
from . import utils

logger = config.get_logger(__name__)


def check_requirement(pkg):
    click.secho("Received payload from package manager, running security audit...")

    handler = URIHandler.from_uri(f"{pkg['path']}")
    try:
        metadata = {
            'uri_input': 'pkg_path',
            'source': 'package_manager',
            'pm_data': pkg
        }

        for location in handler.get_paths():
            # print(f"Enumerating: {location}")
            scan = scan_worker(location, metadata)

            scan.pprint()

    finally:
        handler.cleanup()
    sys.exit(1)


def scan_worker(item, metadata, analyzer=None):
    item_metadata = metadata.copy()
    if 'path' not in item_metadata:
        item_metadata['path'] = item.location

    if not item.location.exists():
        logger.warn(f"Location '{item.location}' does not exists. Skipping")
        return

    scan = ScanResults(
        item.location.name,
        metadata=item_metadata
    )

    sandbox = Analyzer(location=item.location)

    if analyzer:
        sandbox.analyzers = utils.import_hook(analyzer)

    hits = sandbox.run(strip_path=item.location.parent, metadata=item_metadata)

    for x in hits:
        scan.add_hit(x)

    return scan


def scan_uri(uri, metadata=None, analyzer=None):
    start = time.time()
    handler = None
    metadata = metadata or {}

    try:
        handler = URIHandler.from_uri(uri)

        if handler is None:
            raise ValueError(f"Could not find a handler for provided URI: '{uri}'")

        metadata.update({
            'uri_scheme': handler.scheme,
            'uri_input': handler.metadata,
            'source': 'cli',  # TODO: migrate to passed metadata
        })

        for x in handler.get_paths(): #type: ScanLocation
            scan = scan_worker(x, metadata, analyzer)

            if scan is not None:
                if scan.score < metadata.get('min_score', 0):
                    continue

                if metadata.get('format') == 'json':
                    click.echo(json.dumps(scan.json, default=utils.json_encoder))
                else:
                    scan.pprint(verbose=metadata.get('verbosity', 0))
    except exceptions.NoSuchPackage:
        logger.warn(f"No such package: {uri}")
    except Exception:
        logger.exception(f"An error was thrown while processing URI: '{uri}'")
        raise
    finally:
        if handler:
            handler.cleanup()

    logger.info(f"Scan finished in {time.time() - start} s")


def parse_ast(path):
    meta = {
        'path': path,
        'source': 'cli'
    }

    traversal = execution_flow.ExecutionFlow.from_cache(source=path, metadata=meta)
    if not traversal.traversed:
        traversal.traverse()

    pprint.pprint(traversal.tree)
    if traversal.hits:
        print("\n---[ Hits ]---\n")
        for x in traversal.hits:
            print(" * " + repr(x._asdict()))