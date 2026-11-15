"""Tiny helper shared by services: strip the canonical '[date] @author:' prefix from an evidence line."""
from .ingest.parsers import parse_line


def body_of(line: str) -> str:
    return parse_line(line)["body"]
