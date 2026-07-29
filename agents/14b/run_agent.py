"""Thin entry point for the shared agent runner."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from agents._shared.run_agent import main  # noqa: E402


if __name__ == "__main__":
    main(HERE)
