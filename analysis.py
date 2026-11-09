"""Numerical translation of the supplied gelation workbook, not a curve fit."""

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd


VERSION = "0.4.1"
TEMPERATURE_COLUMN = "Gelation temperature (\u00b0C)"
REPORTING_BLOCK_SIZE = 3
REPORTING_THRESHOLD = 0.02
RAMP_JITTER_TOLERANCE = 0.1
METRICS = {
    "linear_peak": "First derivative: G* local maximum",
    "log_peak": "First derivative: log10(G*) local maximum",
    "linear_inflection": "Second derivative: G* positive-to-negative",
    "log_inflection": "Second derivative: log10(G*) positive-to-negative",
}


@dataclass(frozen=True)
class Settings:
    block_size: int = REPORTING_BLOCK_SIZE
    threshold: float = REPORTING_THRESHOLD


def essential_warnings(result):
    hidden = {f"{label}: no qualifying result." for key, label in METRICS.items() if key != "log_inflection"}
    return [warning for warning in result["warnings"] if warning not in hidden]


def log_inflection_candidates(result):
    boundary = result["log_threshold_temperature"]
    if boundary is None:
        return []
    blocks = result["blocks"]
    temperature = blocks.temperature.to_numpy()
    derivative = blocks.log_second_derivative.to_numpy()
    return [float(temperature[index + 1]) for index in range(len(blocks) - 1)
            if temperature[index] >= boundary
            and np.isfinite(derivative[index:index + 2]).all()
            and derivative[index] > 0 and derivative[index + 1] < 0]


def analyze(raw, settings=Settings()):
    if not isinstance(settings.block_size, int) or settings.block_size < 0:
        raise ValueError("Block size must be a non-negative integer; zero disables averaging.")
    if not math.isfinite(settings.threshold) or settings.threshold < 0:
        raise ValueError("Noise threshold must be finite and non-negative.")
    data = raw.loc[:, ["temperature", "storage", "loss"]].copy()
    for column in data:
        original = data[column]
        data[column] = pd.to_numeric(original, errors="coerce")
        if (original.notna() & data[column].isna()).any():
            raise ValueError(f"Non-numeric entries in {column}.")
    if data.empty or data.temperature.isna().any():
        raise ValueError("Every data row must have a numeric temperature.")
    if not np.isfinite(data.temperature).all():
        raise ValueError("Temperatures must be finite.")
    temperatures = data.temperature.to_numpy()
    near_target = np.isclose(temperatures, temperatures.max(), rtol=0,
                             atol=RAMP_JITTER_TOLERANCE + 1e-9)
    outside_target = np.flatnonzero(~near_target)
    hold_start = int(outside_target[-1] + 1) if len(outside_target) else 0
    ramp_end = len(data)
    # A reversal or repeat distinguishes a terminal hold from a slow heating ramp.
    if near_target[-1] and (np.diff(temperatures[hold_start:]) <= 0).any():
        if hold_start == 0:
            raise ValueError("Select a heating ramp before the final temperature hold; "
                             "the entire dataset is within the hold tolerance.")
        ramp_end = hold_start + 1
    temperature_steps = np.diff(temperatures[:ramp_end])
    if (temperature_steps < -RAMP_JITTER_TOLERANCE).any():
        raise ValueError("Select a single non-decreasing temperature ramp; rows are not sorted automatically.")
    warnings = []
    hold_rows = len(data) - ramp_end
    if hold_rows:
        warnings.append(f"Final temperature hold: excluded {hold_rows} rows after data row {ramp_end} "
                        f"from averaging and gelation calculations (within {RAMP_JITTER_TOLERANCE:g} "
                        "\u00b0C of the maximum temperature). The first target-temperature point is retained; "
                        "all rows remain in the raw-data plot and raw-data export.")
    if (temperature_steps < 0).any():
        warnings.append(f"Small instrument temperature reversals (up to {RAMP_JITTER_TOLERANCE:g} \u00b0C) were "
                        "retained in row order; averaged block temperatures must still be strictly increasing.")
    if (temperature_steps == 0).any():
        warnings.append("Repeated raw temperatures retained; averaged block temperatures must be strictly increasing.")
    input_raw = data.reset_index(drop=True).copy()
    if data[["storage", "loss"]].isna().any().any():
        warnings.append("Missing moduli were treated as zero, matching Excel's blank-cell arithmetic.")
    data[["storage", "loss"]] = data[["storage", "loss"]].fillna(0.0)
    if not np.isfinite(data[["storage", "loss"]].to_numpy()).all():
        raise ValueError("Moduli must be finite.")
    data = data.reset_index(drop=True)
    excluded = np.flatnonzero((data.storage.iloc[:ramp_end] < 0) | (data.loss.iloc[:ramp_end] < 0))
    modulus = np.sqrt(data.storage.to_numpy() ** 2 + data.loss.to_numpy() ** 2)
    if len(excluded):
        modulus[:excluded[-1] + 1] = np.nan
        warnings.append(f"Complex modulus excluded through data row {excluded[-1] + 1}, matching the last-negative-value rule.")
    data["complex"] = modulus
    size = max(1, settings.block_size)
    blocks = []
    for start in range(0, ramp_end, size):
        group = data.iloc[start:min(start + size, ramp_end)]
        valid = group.complex.dropna()
        count = len(valid) + size - len(group)
        blocks.append({"temperature": float(group.temperature.mean()),
                   "complex": float(valid.sum() / count) if count else np.nan,
                       "first_data_row": start + 1,
                       "points": len(group)})
    table = pd.DataFrame(blocks)
    if not (np.diff(table.temperature) > 0).all():
        raise ValueError("Averaged block temperatures must be strictly increasing. Repeated temperatures remain "
                         "at the selected Moving Average; increase averaging or select a ramp without repeats.")
    if table.complex.notna().sum() == 0:
        raise ValueError("No complex moduli remain after the last negative input.")
    if ramp_end % size:
        warnings.append("The final modulus averaging block includes trailing zeros, matching Excel's blank-input complex-modulus formulas.")
    if len(table) < 5:
        warnings.append("Fewer than five averaging blocks: second derivatives cannot be evaluated.")
    temperature = table.temperature.to_numpy()
    averaged = table.complex.to_numpy()
    peak_index = int(np.nanargmax(averaged))
    log_modulus = np.full(len(table), np.nan)
    np.log10(averaged, out=log_modulus, where=averaged > 0)
    delta_temperature = np.full(len(table), np.nan)
    forward_span = np.full(len(table), np.nan)
    delta_modulus = np.full(len(table), np.nan)
    delta_log = np.full(len(table), np.nan)
    linear = np.full(len(table), np.nan)
    logarithmic = np.full(len(table), np.nan)
    curvature = np.full(len(table), np.nan)
    log_curvature = np.full(len(table), np.nan)
    forward_span[:-2] = temperature[2:] - temperature[:-2]
    for index in range(1, peak_index + 1):
        span = temperature[index] - temperature[index - 1]
        delta_temperature[index] = span
        difference = averaged[index] - averaged[index - 1]
        log_difference = log_modulus[index] - log_modulus[index - 1]
        if difference != 0:
            delta_modulus[index] = difference
            linear[index] = difference / span
        if log_difference != 0:
            delta_log[index] = log_difference
            logarithmic[index] = log_difference / forward_span[index]
    for index in range(2, len(table) - 2):
        denominator = 12 * forward_span[index] ** 2
        for signal, output in [(averaged, curvature), (log_modulus, log_curvature)]:
            output[index] = (-signal[index - 2] + 16 * signal[index - 1]
                             - 30 * signal[index] + 16 * signal[index + 1]
                             - signal[index + 2]) / denominator
    if len(table) > 2 and not np.allclose(np.diff(temperature), np.diff(temperature)[0]):
        warnings.append("Uneven block temperatures: the workbook's five-point coefficients are retained, not replaced by a nonuniform-grid method.")
    table["delta_temperature"] = delta_temperature
    table["delta_complex"] = delta_modulus
    table["linear_derivative"] = linear
    table["forward_temperature_span"] = forward_span
    table["half_span"] = forward_span / 2
    table["log_complex"] = log_modulus
    table["delta_log_complex"] = delta_log
    table["log_derivative"] = logarithmic
    table["linear_second_derivative"] = curvature
    table["log_second_derivative"] = log_curvature

    def first_threshold(signal):
        found = np.flatnonzero(np.isfinite(signal) & (signal >= settings.threshold))
        return int(found[0]) if len(found) else None

    def first_peak(signal):
        for index in range(1, len(signal) - 2):
            neighbors = signal[[index - 1, index, index + 1, index + 2]]
            if (np.isfinite(neighbors).all() and signal[index] >= settings.threshold
                    and signal[index] >= neighbors.max()):
                return float(temperature[index])
        return None

    def first_crossing(signal, start):
        if start is not None:
            for index in range(start, len(signal) - 1):
                # Inside the computed range Excel's blank ("") cell compares as greater than zero;
                # edge blocks are errors there, not blanks.
                blank = 2 <= index < len(signal) - 2 and np.isnan(signal[index])
                if (blank or signal[index] > 0) and signal[index + 1] < 0:
                    return float(temperature[index + 1])
        return None

    linear_start = first_threshold(linear)
    log_start = first_threshold(logarithmic)
    results = {
        "linear_peak": first_peak(linear),
        "log_peak": first_peak(logarithmic),
        "linear_inflection": first_crossing(curvature, linear_start),
        "log_inflection": first_crossing(log_curvature, log_start),
    }
    for key, value in results.items():
        if value is None:
            warnings.append(f"{METRICS[key]}: no qualifying result.")
    return {"results": results, "blocks": table, "raw": data, "input_raw": input_raw, "warnings": warnings,
            "hold_rows_excluded": hold_rows,
            "settings": asdict(settings), "version": VERSION,
            "maximum_modulus": float(averaged[peak_index]),
            "maximum_temperature": float(temperature[peak_index]),
            "linear_threshold_temperature": None if linear_start is None else float(temperature[linear_start]),
            "log_threshold_temperature": None if log_start is None else float(temperature[log_start])}