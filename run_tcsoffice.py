"""Entry point for packaged builds (PyInstaller); `python -m office` does the same."""
import sys

from office.app import main

if __name__ == "__main__":
    sys.exit(main())
