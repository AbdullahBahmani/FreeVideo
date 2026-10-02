"""Resolve the installed test environment without shell activation."""
import sys
from .managed import main as managed


def main():
    return managed(['test', *sys.argv[1:]])


if __name__ == '__main__':
    raise SystemExit(main())
