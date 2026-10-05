"""`ontle observations csv`: CSV records -> an ObservationSet (tooling; spec section 12.2 defines the document).

One CSV file holds one record type. Each row becomes one observation: `type` is given, `subject` and `observedAt` come
from named columns, and the remaining columns become `values`. Values stay strings unless a column is named as a number
or a list. Ids are `<type>-<row number>`, so sets of different types merge without clashes.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .core import OWPError
from .ews import _valid_timestamp


def csv_observations(path: str | Path, otype: str, subject: str, time: str, numbers: list[str] | None = None,
                     lists: list[str] | None = None, separator: str = ";", columns: list[str] | None = None) -> dict[str, Any]:
    numbers, lists = set(numbers or []), set(lists or [])
    observations: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        for name in [subject, time, *sorted(numbers | lists), *(columns or [])]:
            if name not in header:
                raise OWPError(f"{path}: no column {name!r} (columns: {', '.join(header)})")
        for line, row in enumerate(reader, start=2):
            observed = (row.get(time) or "").strip()
            if not _valid_timestamp(observed):
                raise OWPError(f"{path}:{line}: {time} {observed!r} must be UTC YYYY-MM-DDTHH:MM:SSZ")
            values: dict[str, Any] = {}
            for key, raw in row.items():
                if key in (subject, time) or key is None or (columns and key not in columns):
                    continue
                raw = raw if raw is not None else ""
                if key in lists:
                    values[key] = [x.strip() for x in raw.split(separator) if x.strip()]
                elif key in numbers:
                    if raw.strip() == "":
                        continue  # an empty cell is no value
                    try:
                        number = float(raw)
                    except ValueError as exc:
                        raise OWPError(f"{path}:{line}: {key} {raw!r} is not a number") from exc
                    values[key] = int(number) if number.is_integer() and "." not in raw and "e" not in raw.lower() else number
                else:
                    values[key] = raw
            observations.append({"id": f"{otype}-{len(observations) + 1}", "type": otype, "subject": row.get(subject) or "",
                                 "observedAt": observed, "values": values})
    return {"apiVersion": "openworld/v1alpha1", "kind": "ObservationSet", "spec": {"observations": observations}}
