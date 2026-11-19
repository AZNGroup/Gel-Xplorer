"""Figures for the Excel-compatible log gelation metric."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analysis import Settings, analyze, log_inflection_candidates


CELSIUS = "\u00b0C"
COLORS = {"storage": "#c62828", "loss": "#245bc4", "complex": "#111111"}
AXIS_COLOR = "#111111"
TICK_WIDTH = 2
DERIVATIVE_LABEL = "d<sup>2</sup>log<sub>10</sub>(G*) / (dT<sub>avg</sub>)<sup>2</sup>"


def crossover_temperature(raw):
    temperature = raw.temperature.to_numpy()
    storage = raw.storage.to_numpy()
    loss = raw.loss.to_numpy()
    difference = storage - loss
    for index in range(len(raw)):
        if not (np.isfinite(storage[index]) and np.isfinite(loss[index])
                and storage[index] > 0 and loss[index] > 0):
            continue
        if difference[index] == 0:
            return float(temperature[index])
        if index + 1 < len(raw) and storage[index + 1] > 0 and loss[index + 1] > 0:
            if difference[index] * difference[index + 1] < 0:
                fraction = -difference[index] / (difference[index + 1] - difference[index])
                return float(temperature[index] + fraction * (temperature[index + 1] - temperature[index]))
    return None


def marker_value(blocks, temperature):
    if temperature is None:
        return None
    temperatures = blocks.temperature.to_numpy()
    values = blocks.log_second_derivative.to_numpy()
    for index, current in enumerate(temperatures):
        if current == temperature and np.isfinite(values[index]):
            return float(values[index])
        if index + 1 < len(blocks) and current < temperature < temperatures[index + 1]:
            if np.isfinite(values[index:index + 2]).all():
                return float(np.interp(temperature, temperatures[index:index + 2], values[index:index + 2]))
    return None


def axis_defaults(result, exclude_last=0):
    raw = result["raw"]
    positive = np.abs(raw[["storage", "loss"]].to_numpy())
    positive = np.concatenate([positive.ravel(), np.hypot(raw.storage, raw.loss).to_numpy()])
    positive = positive[np.isfinite(positive) & (positive > 0)]
    minimum = float(np.floor(raw.temperature.min() / 20) * 20)
    maximum = float(np.ceil(raw.temperature.max() / 20) * 20)
    if maximum <= minimum:
        maximum = minimum + 20
    low_power = float(np.floor(np.log10(positive.min()))) if len(positive) else -2.0
    high_power = float(np.ceil(np.log10(positive.max()))) if len(positive) else 2.0
    derivative = derivative_plot_data(result, exclude_last).iloc[:, 1].to_numpy()
    finite = derivative[np.isfinite(derivative)]
    low = min(float(finite.min()), 0.0) if len(finite) else -0.01
    high = max(float(finite.max()), 0.0) if len(finite) else 0.01
    span = high - low or 0.02
    return {"temperature_min": minimum, "temperature_max": maximum, "temperature_step": 20.0,
            "modulus_min_power": low_power, "modulus_max_power": max(high_power, low_power + 1),
            "derivative_min": low - 0.15 * span, "derivative_max": high + 0.25 * span,
            "derivative_exclude_last": exclude_last}


def derivative_plot_data(result, exclude_last=0):
    if not isinstance(exclude_last, int) or exclude_last < 0:
        raise ValueError("Excluded derivative point count must be a non-negative integer.")
    data = result["blocks"][["temperature", "log_second_derivative"]].copy()
    raw = result["raw"][["temperature", "storage", "loss"]].copy()
    if (raw[["storage", "loss"]] < 0).any().any():
        # Magnitudes preserve sqrt(G'^2 + G"^2), bypassing exclusions for display only.
        raw[["storage", "loss"]] = raw[["storage", "loss"]].abs()
        unfiltered = analyze(raw, Settings(**result["settings"]))["blocks"]
        data["log_second_derivative"] = data.log_second_derivative.combine_first(
            unfiltered.log_second_derivative)
    data = data.rename(columns={
        "temperature": "temperature_C",
        "log_second_derivative": "log10_complex_second_derivative_per_C2"})
    if exclude_last:
        valid = np.flatnonzero(np.isfinite(data.iloc[:, 1]))
        if exclude_last >= len(valid):
            raise ValueError("At least one valid derivative point must remain visible.")
        data = data.iloc[:valid[-exclude_last]]
    return data


def build_figure(result, marker_temperature=None, panel=None, axis_settings=None):
    figure = make_subplots(rows=2 if panel is None else 1, cols=1,
                           vertical_spacing=0.18, shared_xaxes=True)
    raw = result["raw"]
    blocks = result["blocks"]
    detected = result["results"]["log_inflection"]
    marker_temperature = detected if marker_temperature is None else marker_temperature
    candidates = log_inflection_candidates(result)
    if marker_temperature not in candidates:
        marker_temperature = detected if detected in candidates else None
    excluded = (axis_settings or {}).get("derivative_exclude_last", 0)
    plotted_derivative = derivative_plot_data(result, excluded)
    settings = {**axis_defaults(result, excluded), **(axis_settings or {})}
    minimum = settings["temperature_min"]
    maximum = settings["temperature_max"]
    low_power = settings["modulus_min_power"]
    high_power = settings["modulus_max_power"]
    if (not all(np.isfinite(value) for value in settings.values()) or minimum >= maximum
            or low_power >= high_power or settings["derivative_min"] >= settings["derivative_max"]
            or settings["temperature_step"] <= 0):
        raise ValueError("Axis maxima must exceed minima and the temperature tick interval must be positive.")
    if panel in (None, "A"):
        display = raw.assign(complex=np.hypot(raw.storage, raw.loss))
        for column, name in [("storage", "G'"), ("loss", 'G"'), ("complex", "G*")]:
            figure.add_trace(go.Scatter(x=display.temperature, y=display[column].where(display[column] > 0),
                                       name=name, mode="lines", connectgaps=False, showlegend=False,
                                       line={"color": COLORS[column], "width": 2}), row=1, col=1)
            negative = raw[column] < 0
            if negative.any():
                # A log axis cannot show negatives, so plot their magnitude as hollow markers.
                figure.add_trace(go.Scatter(x=raw.temperature[negative], y=raw[column][negative].abs(),
                                           name=f"{name} (negative, magnitude)", mode="markers", showlegend=False,
                                           marker={"color": "white", "size": 6, "symbol": "circle",
                                                   "line": {"color": COLORS[column], "width": 1.5}},
                                           customdata=raw[column][negative],
                                           hovertemplate=f"%{{x:.3f}} {CELSIUS}<br>%{{customdata:.4g}} Pa<extra>%{{fullData.name}}</extra>"),
                                 row=1, col=1)
        crossover = crossover_temperature(raw)
        for temperature, color, field in [(crossover, "#279443", "storage"), (marker_temperature, "#111111", "complex")]:
            if temperature is not None:
                modulus = float(np.interp(temperature, raw.temperature, raw[field]))
                if np.isfinite(modulus) and modulus > 0:
                    endpoint = float(np.clip((np.log10(modulus) - low_power) / (high_power - low_power), 0, 1))
                    figure.add_shape(type="line", x0=temperature, x1=temperature, y0=0, y1=endpoint,
                                     xref="x", yref="y domain",
                                     line={"color": color, "width": 3, "dash": "6px,4px"},
                                     name="Moduli crossover" if field == "storage" else "Apparent gelation<br>temperature",
                                     showlegend=True, legendrank=5 if field == "storage" else 4)
                    figure.add_trace(go.Scatter(x=[temperature], y=[modulus], mode="markers",
                                               marker={"color": color, "size": 9}, showlegend=False,
                                               name="Modulus crossover" if field == "storage" else "Reported gelation",
                                               hovertemplate=f"%{{x:.1f}} {CELSIUS}<extra>%{{fullData.name}}</extra>"), row=1, col=1)
        powers = range(int(np.ceil(low_power)), int(np.floor(high_power)) + 1)
        minor_values = [multiplier * 10.0 ** power
                        for power in range(int(np.floor(low_power)), int(np.ceil(high_power)))
                        for multiplier in range(2, 10)
                        if 10.0 ** low_power < multiplier * 10.0 ** power < 10.0 ** high_power]
        figure.update_yaxes(type="log", title_text="Modulus [Pa]", range=[low_power, high_power],
                            tickmode="array", tickvals=[10.0 ** power for power in powers],
                            ticktext=[f"10<sup>{power}</sup>" for power in powers],
                            minor={"tickmode": "array", "tickvals": minor_values, "ticks": "inside",
                                "ticklen": 4, "tickwidth": TICK_WIDTH, "tickcolor": AXIS_COLOR, "showgrid": False},
                             row=1, col=1)
    if panel in (None, "B"):
        row = 2 if panel is None else 1
        boundary = result["log_threshold_temperature"]
        noise_end = maximum if boundary is None else boundary
        noise_fraction = float(np.clip((noise_end - minimum) / (maximum - minimum), 0, 1))
        axis = "x2" if panel is None else "x"
        domain = "y2 domain" if panel is None else "y domain"
        figure.add_shape(type="rect", x0=0, x1=noise_fraction, y0=0, y1=1,
                 xref=f"{axis} domain", yref=domain, fillcolor="#bdbdbd", opacity=0.65,
                 line_width=0, layer="below", name="Noise threshold", showlegend=True, legend="legend2")
        figure.add_shape(type="line", x0=noise_fraction, x1=noise_fraction, y0=0, y1=1,
                 xref=f"{axis} domain", yref=domain,
                 line={"color": AXIS_COLOR, "dash": "dot", "width": 3})
        figure.add_shape(type="line", x0=0, x1=1, y0=0, y1=0,
                 xref=f"{axis} domain", yref="y2" if panel is None else "y",
                 line={"color": AXIS_COLOR, "dash": "dot", "width": 3})
        figure.add_trace(go.Scatter(x=plotted_derivative.iloc[:, 0], y=plotted_derivative.iloc[:, 1],
                                   name="Log second derivative", showlegend=False,
                                   mode="lines+markers", connectgaps=False,
                                   line={"color": "#111111", "width": 1.6},
                                   marker={"color": "#111111", "size": 5}), row=row, col=1)
        value = marker_value(blocks, marker_temperature)
        if value is not None and marker_temperature in plotted_derivative.temperature_C.to_numpy():
            figure.add_trace(go.Scatter(x=[marker_temperature], y=[value], mode="markers",
                                       name="Selected marker", showlegend=False,
                                       marker={"color": "#d62728", "size": 16, "symbol": "circle-open", "line": {"width": 3}},
                                       hovertemplate=f"%{{x:.1f}} {CELSIUS}<br>%{{y:.6g}}<extra>Selected marker</extra>"), row=row, col=1)
        figure.update_layout(legend2={"x": 1, "xanchor": "right",
                          "y": figure.layout["yaxis2" if panel is None else "yaxis"].domain[1] + 0.015,
                          "yanchor": "bottom", "orientation": "h", "font": {"size": 14},
                          "bgcolor": "white", "itemclick": False, "itemdoubleclick": False})
        figure.update_yaxes(title_text=DERIVATIVE_LABEL, title_standoff=18,
                            range=[settings["derivative_min"], settings["derivative_max"]],
                            zeroline=False, nticks=5,
                            minor={"ticks": "inside", "ticklen": 4, "tickwidth": TICK_WIDTH, "tickcolor": AXIS_COLOR, "showgrid": False, "nticks": 2},
                            row=row, col=1)
    step = settings["temperature_step"]
    temperature_ticks = np.arange(np.ceil(minimum / step), np.floor(maximum / step) + 1) * step
    if minimum <= 100 <= maximum:
        temperature_ticks = np.unique(np.append(temperature_ticks, 100.0))
    figure.update_xaxes(title_text=f"Temperature [{CELSIUS}]", range=[minimum, maximum],
                        tickmode="array", tickvals=temperature_ticks, tick0=0,
                        dtick=step, showticklabels=True, ticklabeloverflow="allow",
                        minor={"ticks": "inside", "ticklen": 4, "tickwidth": TICK_WIDTH,
                             "dtick": settings["temperature_step"] / 2, "tick0": 0, "tickcolor": AXIS_COLOR, "showgrid": False})
    figure.update_xaxes(showgrid=False, showline=True, linewidth=2, linecolor=AXIS_COLOR, ticks="inside", ticklen=7, tickwidth=TICK_WIDTH,
                        tickcolor=AXIS_COLOR, tickfont={"size": 17, "color": AXIS_COLOR},
                        title_font={"size": 19, "color": AXIS_COLOR}, mirror=False,
                        side="bottom", layer="above traces", automargin=True)
    figure.update_yaxes(showgrid=False, showline=True, linewidth=2, linecolor=AXIS_COLOR, ticks="inside", ticklen=7, tickwidth=TICK_WIDTH,
                        tickcolor=AXIS_COLOR, tickfont={"size": 17, "color": AXIS_COLOR},
                        title_font={"size": 19, "color": AXIS_COLOR}, mirror=False,
                        side="left", layer="above traces", automargin=True)
    if panel in (None, "A"):
        for rank, (column, name) in enumerate([("storage", "G'"), ("loss", 'G"'), ("complex", "G*")], 1):
            figure.add_trace(go.Scatter(x=[None], y=[None], name=name, mode="markers",
                                       marker={"color": COLORS[column], "size": 15, "symbol": "circle"},
                                       showlegend=True, legendrank=rank, hoverinfo="skip"), row=1, col=1)
    figure.update_layout(template="plotly_white", height=440 if panel else 900,
                         margin={"t": 45, "b": 65, "l": 110, "r": 185 if panel != "B" else 25, "pad": 0},
                         font={"family": "Trebuchet MS", "size": 17, "color": AXIS_COLOR},
                         legend={"orientation": "v", "y": 1, "yanchor": "top", "x": 1.02, "xanchor": "left",
                                 "font": {"size": 14}, "itemsizing": "constant", "traceorder": "normal",
                                 "itemclick": False, "itemdoubleclick": False},
                         paper_bgcolor="white", plot_bgcolor="white")
    return figure
