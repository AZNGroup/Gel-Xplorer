"""Plain Excel output (one summary sheet, one table per dataset) and figure downloads."""

from io import BytesIO
import re

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font


DATA_COLUMNS = [
    ("temperature", "Mean temperature (\u00b0C)"),
    ("complex", "Moving-average G* (Pa)"),
    ("log_complex", "log10(G*)"),
    ("log_second_derivative", "Second derivative d2 log10(G*)/dT2 (1/\u00b0C2)"),
]
RESULT_HEADER = "Apparent gelation temperature (\u00b0C)"
SUMMARY_HEADERS = ["Dataset", RESULT_HEADER, "Moving average (points; 0 = off)", "Noise threshold", "Warnings"]


def finite_value(value):
    return float(value) if value is not None and np.isfinite(value) else None


def sheet_title(label, used):
    title = re.sub(r"[\[\]:*?/\\]", "_", label.rsplit(" / ", 1)[-1]).strip(" '") or "Dataset"
    title = title[:31]
    base, suffix = title, 2
    while title.casefold() in used or title.casefold() == "summary":
        ending = f" ({suffix})"
        title = base[:31 - len(ending)] + ending
        suffix += 1
    used.add(title.casefold())
    return title


def style_header(sheet, width):
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = width
    sheet.freeze_panes = "A2"


def export_workbook(records, markers=None, configuration=None, failures=None):
    """Summary sheet first, then one sheet per dataset with its moving-averaged data,
    second-derivative calculation and apparent gelation temperature, with no blank rows or columns."""
    if not records:
        raise ValueError("No analyzed datasets to export.")
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    summary.append(SUMMARY_HEADERS)
    used = set()
    for label, result in records.items():
        blocks = result["blocks"]
        if len(blocks) + 1 > 1048576:
            raise ValueError(f"{label}: too many rows for an Excel worksheet.")
        reported = (markers or {}).get(label, result["results"]["log_inflection"])
        summary.append([label, reported, result["settings"]["block_size"], result["settings"]["threshold"],
                        " | ".join(result["warnings"])])
        summary.cell(summary.max_row, 2).number_format = "0.0"
        summary.cell(summary.max_row, 5).data_type = "s"
        sheet = book.create_sheet(sheet_title(label, used))
        sheet.append([header for _, header in DATA_COLUMNS] + [RESULT_HEADER])
        for index in range(len(blocks)):
            row = [finite_value(blocks[field].iloc[index]) for field, _ in DATA_COLUMNS]
            row.append(reported if index == 0 else None)
            sheet.append(row)
        sheet.cell(2, len(DATA_COLUMNS) + 1).number_format = "0.0"
        style_header(sheet, 24)
        if result.get("hold_rows_excluded", 0):
            raw = result["input_raw"]
            if len(raw) + 1 > 1048576:
                raise ValueError(f"{label}: too many raw rows for an Excel worksheet.")
            sheet = book.create_sheet(sheet_title("Raw " + label.rsplit(" / ", 1)[-1], used))
            sheet.append(["Temperature (\u00b0C)", "Storage modulus G' (Pa)",
                          'Loss modulus G" (Pa)', "Used in gelation calculation"])
            ramp_end = len(raw) - result["hold_rows_excluded"]
            for index, row in enumerate(raw.itertuples(index=False, name=None)):
                sheet.append([finite_value(value) for value in row] + [index < ramp_end])
            style_header(sheet, 24)
    style_header(summary, 30)
    summary.column_dimensions["A"].width = 40
    summary.column_dimensions["E"].width = 60
    if failures:
        sheet = book.create_sheet("Failed datasets")
        sheet.append(["Dataset", "Error"])
        for label, error in failures.items():
            sheet.append([str(label), str(error)])
            for cell in sheet[sheet.max_row]:
                cell.data_type = "s"
    payload = BytesIO()
    book.save(payload)
    book.close()
    return payload.getvalue()


def figure_image(figure, image_format):
    if image_format not in {"png", "svg", "pdf"}:
        raise ValueError("Choose PNG, SVG or PDF.")
    return figure.to_image(format=image_format, width=1200, height=1000,
                           scale=3 if image_format == "png" else 1)
