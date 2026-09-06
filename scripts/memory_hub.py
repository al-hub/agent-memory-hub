#!/usr/bin/env python3
"""Legacy script entry point; new integrations should use memcarry_store.py."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("memcarry_store.py")), run_name="__main__")
