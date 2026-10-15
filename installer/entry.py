"""PyInstaller entry point for the standalone camcommand.exe.

Kept deliberately tiny: it just delegates to the package's CLI main so the
frozen executable behaves exactly like the pip-installed `camcommand` console
script.
"""
import sys

from camcommand.cli import main

if __name__ == "__main__":
    sys.exit(main())
