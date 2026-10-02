"""Inspect local performance and resource measurements without CUDA."""
import argparse
import json
from pathlib import Path
import sys

from .resource_history import ResourceHistory, ResourceHistoryError


def _emit(value, stream):
    output = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    encoding = getattr(stream, 'encoding', None)
    if encoding:
        try:
            output.encode(encoding)
        except UnicodeEncodeError:
            # A redirected Windows terminal may still use a legacy codepage.
            # Keep valid JSON and a visible acknowledgment token in that case.
            output = json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False)
    print(output, file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='freevideo resource-history',
        description='Inspect local performance measurements; no GPU work is started.')
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='Show performance measurements and discard stopped incomplete runs')
    for command in (listing,):
        command.add_argument('--history', type=Path,
            help='Local history database; defaults to this installation')
    args = parser.parse_args(argv)
    try:
        if args.history is None:
            from .adaptive import history_path
            path = history_path()
        else:
            path = args.history.expanduser()
        exists = path.exists()
        if args.command == 'list':
            recovered, rows = [], []
            if exists:
                ledger = ResourceHistory(path)
                recovered = ledger.recover_pending()
                rows = ledger.attempts()
            _emit({'history': str(path), 'history_exists': exists,
                   'attempts': rows, 'total': len(rows),
                   'discarded_incomplete_count': len(recovered),
                   'note': 'Complete measurements guide predictions and optimization; '
                           'history does not block configurations.'}, sys.stdout)
        return 0
    except (ResourceHistoryError, OSError, ValueError) as error:
        _emit({'error': str(error), 'gpu_work_started': False,
               'note': 'No inference was started.'}, sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
