"""Deprecated office-demo file-helper compatibility exports."""
from domains.office_demo.office_files import (
    create_presentation,
    create_spreadsheet,
    read_spreadsheet,
)

__all__ = ["create_presentation", "create_spreadsheet", "read_spreadsheet"]
