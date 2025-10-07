"""Utilities for organizing outpatient chemotherapy clinic patient data.

This module provides a small command line program that can read a CSV file
containing information about patients who attend an outpatient chemotherapy
clinic and produce a sorted version of that data.  The default ordering sorts
patients by the urgency of their treatment, followed by the appointment date
and, finally, by their numeric patient identifier.  The behaviour can be
customised through command line flags, making it simple to adapt the tool for
different clinics without editing the source code.

Example
-------
Assuming you have a file called ``patients.csv`` with columns
``patient_id,name,appointment_date,urgency_level,regimen`` you can run:

```
python chemotherapy_patient_sorter.py patients.csv --output sorted.csv
```

This will create ``sorted.csv`` with the rows ordered based on the default
sorting policy.  To change the order you can provide the ``--sort-by`` flag and
list the column names in the desired priority, for example:

```
python chemotherapy_patient_sorter.py patients.csv --sort-by urgency_level \
    appointment_date regimen
```

The script validates that all requested sort keys are present in the CSV file
and will provide human friendly error messages if the input data is malformed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class PatientRecord:
    """Container that stores the essential data for a clinic visit."""

    patient_id: str
    name: str
    appointment_date: dt.date
    urgency_level: int
    regimen: str
    cycle_number: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "PatientRecord":
        """Create a :class:`PatientRecord` from a CSV row.

        Parameters
        ----------
        row:
            Mapping of column names to values obtained from ``csv.DictReader``.

        Returns
        -------
        PatientRecord
            The normalised patient record.

        Raises
        ------
        ValueError
            If any of the required fields are missing or cannot be converted
            to the expected type.
        """

        try:
            patient_id = row["patient_id"].strip()
            name = row["name"].strip()
            appointment = _parse_date(row["appointment_date"].strip())
            urgency = int(row["urgency_level"].strip())
            regimen = row["regimen"].strip()
        except KeyError as exc:  # pragma: no cover - defensive programming
            missing = exc.args[0]
            raise ValueError(f"Missing required column: {missing}") from exc
        except ValueError as exc:
            raise ValueError(
                "Failed to parse one of the required fields: "
                f"{exc}. Check the input data."
            ) from exc

        cycle_number: int | None
        raw_cycle = row.get("cycle_number", "").strip()
        if raw_cycle:
            try:
                cycle_number = int(raw_cycle)
            except ValueError as exc:  # pragma: no cover - defensive programming
                raise ValueError(
                    "Cycle number must be an integer when provided."
                ) from exc
        else:
            cycle_number = None

        return cls(
            patient_id=patient_id,
            name=name,
            appointment_date=appointment,
            urgency_level=urgency,
            regimen=regimen,
            cycle_number=cycle_number,
        )

    def as_dict(self) -> dict[str, str]:
        """Return a serialisable representation suitable for CSV writing."""

        base = {
            "patient_id": self.patient_id,
            "name": self.name,
            "appointment_date": self.appointment_date.isoformat(),
            "urgency_level": str(self.urgency_level),
            "regimen": self.regimen,
        }
        if self.cycle_number is not None:
            base["cycle_number"] = str(self.cycle_number)
        return base


def _parse_date(value: str) -> dt.date:
    """Parse an ISO formatted date string into a :class:`datetime.date`."""

    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - defensive programming
        raise ValueError(
            "Dates must be provided in ISO format (YYYY-MM-DD)."
        ) from exc


def load_patients(path: Path) -> List[PatientRecord]:
    """Read patient data from a CSV file.

    Parameters
    ----------
    path:
        Path to the CSV file containing the raw patient data.

    Returns
    -------
    list[PatientRecord]
        A list of normalised patient records.
    """

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required_columns = {
            "patient_id",
            "name",
            "appointment_date",
            "urgency_level",
            "regimen",
        }

        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "Input file is missing the following columns: "
                + ", ".join(sorted(missing_columns))
            )

        records = []
        for row in reader:
            if not any(value.strip() for value in row.values() if value):
                # Skip blank lines
                continue
            records.append(PatientRecord.from_row(row))
    return records


def sort_patients(
    patients: Iterable[PatientRecord],
    sort_keys: Sequence[str],
) -> List[PatientRecord]:
    """Return a new list of patient records sorted by ``sort_keys``.

    Supported sort keys are ``urgency_level``, ``appointment_date``,
    ``patient_id``, ``name``, ``regimen``, and ``cycle_number``.  Missing
    ``cycle_number`` values are treated as larger than all integers, meaning
    records without a cycle number are placed at the end when sorting ascending
    on that key.
    """

    valid_keys = {
        "urgency_level",
        "appointment_date",
        "patient_id",
        "name",
        "regimen",
        "cycle_number",
    }
    unknown_keys = [key for key in sort_keys if key not in valid_keys]
    if unknown_keys:
        readable = ", ".join(unknown_keys)
        raise ValueError(f"Unknown sort keys provided: {readable}")

    def sort_tuple(record: PatientRecord):  # type: ignore[override]
        tuple_values = []
        for key in sort_keys:
            value = getattr(record, key)
            if key == "cycle_number" and value is None:
                # ``None`` values are moved to the end for readability.
                tuple_values.append(float("inf"))
            else:
                tuple_values.append(value)
        return tuple(tuple_values)

    return sorted(patients, key=sort_tuple)


def _write_patients(path: Path, patients: Iterable[PatientRecord]) -> None:
    """Write the sorted patient data back to ``path`` as CSV."""

    patients = list(patients)
    if not patients:
        raise ValueError("No patient records available to write.")

    fieldnames = list(patients[0].as_dict().keys())

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for patient in patients:
            writer.writerow(patient.as_dict())


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the argument parser used by :func:`main`."""

    parser = argparse.ArgumentParser(
        description=(
            "Sort outpatient chemotherapy patient data by the selected fields "
            "and either print the resulting table or write it to a new CSV "
            "file."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input CSV file containing patient data.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="If provided, the sorted data will be written to this CSV file.",
    )
    parser.add_argument(
        "--sort-by",
        nargs="+",
        default=["urgency_level", "appointment_date", "patient_id"],
        help=(
            "Space separated list of column names that determine the sort "
            "order.  Default: urgency_level appointment_date patient_id"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by ``python -m chemotherapy_patient_sorter``."""

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        patients = load_patients(args.input)
        sorted_patients = sort_patients(patients, args.sort_by)
    except ValueError as exc:
        parser.error(str(exc))

    if args.output:
        _write_patients(args.output, sorted_patients)
    else:
        _print_patients(sorted_patients)

    return 0


def _print_patients(patients: Iterable[PatientRecord]) -> None:
    """Pretty print the patient table to standard output."""

    patients = list(patients)
    if not patients:
        print("هیچ بیماری برای نمایش وجود ندارد.")
        return

    headers = [
        ("patient_id", "شناسه بیمار"),
        ("name", "نام"),
        ("appointment_date", "تاریخ نوبت"),
        ("urgency_level", "اولویت"),
        ("regimen", "رژیم"),
        ("cycle_number", "شماره سیکل"),
    ]

    rows: list[list[str]] = []
    for patient in patients:
        row = [
            patient.patient_id,
            patient.name,
            patient.appointment_date.isoformat(),
            str(patient.urgency_level),
            patient.regimen,
            "-" if patient.cycle_number is None else str(patient.cycle_number),
        ]
        rows.append(row)

    column_widths = [
        max(len(header), max((len(row[idx]) for row in rows), default=0))
        for idx, (_, header) in enumerate(headers)
    ]

    header_row = " | ".join(
        header.ljust(column_widths[idx]) for idx, (_, header) in enumerate(headers)
    )
    separator = "-+-".join("-" * width for width in column_widths)

    print(header_row)
    print(separator)
    for row in rows:
        print(
            " | ".join(
                value.ljust(column_widths[idx])
                for idx, value in enumerate(row)
            )
        )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
