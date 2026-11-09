"""Conservative import suggestions; users retain control of rows and columns."""

import re
import unicodedata

import pandas as pd


FIELDS = ("temperature", "storage", "loss")


def header_field(value):
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("\u2033", '"').replace("\u2032", "'").replace("\u2019", "'")
    compact = re.sub(r"\s+", "", text)
    if "temperature" in text or re.fullmatch(r"temp\.?([\s\[\](].*)?", text) or compact in {"t", "t(c)", "t[\u00b0c]"}:
        return "temperature"
    if "loss" in text or "g\"" in compact or "g''" in compact or "gdoubleprime" in compact:
        return "loss"
    if "storage" in text or "g'" in compact or "gprime" in compact:
        return "storage"
    return None


def numeric_or_blank(value):
    return pd.isna(value) or pd.notna(pd.to_numeric(value, errors="coerce"))


def detect_layout(frame):
    if frame.shape[1] < 3:
        raise ValueError("At least three columns are required.")
    best = {}
    header_row = None
    ambiguous = False
    for row_index, row in frame.head(30).iterrows():
        matches = {}
        duplicates = set()
        for column, value in enumerate(row):
            field = header_field(value)
            if field:
                if field in matches:
                    duplicates.add(field)
                else:
                    matches[field] = column
        if len(matches) > len(best):
            best, header_row, ambiguous = matches, int(row_index), bool(duplicates)
    columns = [best.get(field) for field in FIELDS]
    used = {column for column in columns if column is not None}
    for index, column in enumerate(columns):
        if column is None:
            columns[index] = next(candidate for candidate in range(frame.shape[1]) if candidate not in used)
            used.add(columns[index])
    first_row = None
    start = 0 if header_row is None else header_row + 1
    for row_index in range(start, len(frame)):
        values = frame.iloc[row_index, columns]
        if pd.notna(pd.to_numeric(values.iloc[0], errors="coerce")) and all(numeric_or_blank(value) for value in values.iloc[1:]):
            first_row = row_index + 1
            break
    notes = []
    confidence = "Detected" if len(best) == 3 and not ambiguous else "Needs confirmation"
    if confidence != "Detected":
        notes.append("Column labels are incomplete or ambiguous. Confirm the selected columns and first data row.")
    if first_row is None:
        first_row = min(start + 1, max(len(frame), 1))
        notes.append("No numeric measurement row was detected.")
    header_end = first_row - 1
    unit_text = " ".join(str(value) for value in frame.iloc[max(0, header_end - 3):header_end, columns].to_numpy().flat).casefold()
    unit_issue = None
    if re.search(r"\b(kpa|mpa)\b", unit_text):
        unit_issue = "Modulus headers indicate kPa or MPa. Convert the raw moduli to Pa before analysis."
    elif re.search(r"\bkelvin\b|\bfahrenheit\b|\u00b0f|\[k\]|\(k\)", unit_text):
        unit_issue = "Temperature headers indicate non-Celsius units. Convert temperatures to Celsius before analysis."
    return {"columns": columns, "first_data_row": first_row,
            "header_row": None if header_row is None else header_row + 1,
            "confidence": confidence, "notes": notes, "unit_issue": unit_issue}


def extract_raw(frame, first_row, last_row, columns):
    if len(set(columns)) != 3:
        raise ValueError("Temperature, storage and loss must use different columns.")
    selected = frame.iloc[first_row - 1:last_row, list(columns)].copy()
    selected.columns = list(FIELDS)
    occupied = selected.notna().any(axis=1).to_numpy().nonzero()[0]
    if not len(occupied):
        raise ValueError("No data in the selected row range and columns.")
    return selected.iloc[:occupied[-1] + 1]


def input_summary(frame, first_row, skipped, columns):
    raw = extract_raw(frame, first_row + skipped, None, columns)
    temperature = pd.to_numeric(raw.temperature, errors="coerce")
    finite = temperature.dropna()
    return {"Measurements": len(raw), "First included row": first_row + skipped,
            "Excluded measurements": skipped,
            "Minimum temperature": None if finite.empty else float(finite.min()),
            "Maximum temperature": None if finite.empty else float(finite.max()),
            "Units": "\u00b0C / Pa (assumed)"}