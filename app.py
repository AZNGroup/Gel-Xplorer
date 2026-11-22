from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path

from openpyxl.utils import get_column_letter
import pandas as pd
import streamlit as st

from analysis import REPORTING_BLOCK_SIZE, REPORTING_THRESHOLD, VERSION, Settings, analyze
from exports import export_workbook, figure_image
from figures import CELSIUS, axis_defaults, build_figure, crossover_temperature, derivative_plot_data
from importing import detect_layout, extract_raw, input_summary


LOG_COLUMNS = ["temperature", "complex", "log_complex", "log_derivative", "forward_temperature_span", "log_second_derivative"]
st.set_page_config(page_title="Gel Xplorer", page_icon=":material/science:", layout="wide")
st.markdown("""<style>
[class*="st-key-scientific_figure"] {overflow-x:auto;}
[class*="st-key-scientific_figure"] > .stElementContainer {min-width:640px;overflow:visible;}
[class*="st-key-scientific_figure"] [data-testid="stPlotlyChart"] {min-width:640px;}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=8)
def read_tables(content, suffix):
    if suffix.lower() == ".csv":
        return {"CSV": pd.read_csv(BytesIO(content), header=None, dtype=object,
                                   sep=None, engine="python", encoding="utf-8-sig")}
    with pd.ExcelFile(BytesIO(content), engine="openpyxl") as workbook:
        return {name: workbook.parse(name, header=None, dtype=object) for name in workbook.sheet_names}


@st.cache_data(show_spinner=False, max_entries=4)
def excel_download(records, markers, configuration, failures):
    return export_workbook(records, markers, configuration, failures)


def page_footer():
    st.space("large")
    st.html(f"""<div style="border-top:1px solid #d7dfe8;margin-top:1.5rem;padding:1.2rem 0 0.5rem;
                text-align:center;color:#5b6b7c;font-size:0.82rem;line-height:1.8;">
  <div><span style="font-family:Georgia,serif;font-size:1.05rem;font-weight:600;color:#0b5394;">Gel Xplorer</span>
       <span style="color:#8295a7;">&nbsp;v{VERSION}</span></div>
  <div>Developed by Wing Shan Ko &nbsp;&middot;&nbsp; Singapore Institute of Technology</div>
  <div style="color:#8295a7;">All data is processed locally; no information is sent to external servers</div>
  <div style="max-width:52rem;margin:0.9rem auto 0;color:#8295a7;line-height:1.6;">
   If you use Gel Xplorer in your research, publications, or academic studies, please cite the following work: </div>
  <div style="max-width:52rem;margin:0.45rem auto 0.9rem;line-height:1.6;">
    <strong>Citation format:</strong> Ko, W. S., Chin, T. G. J., Tang, K. Y., Chai, C. H. T.,
    Jiang, Y., Ye, E., Du, J., &amp; Nelson, A. Z. (2026).
    <em>Practical rheology: Apparent gelation temperature metrics for enabling high-throughput
    screening of plant-based protein functionality</em> [Manuscript under review].</div>
<div style="max-width:52rem;margin:0.9rem auto 0;color:#8295a7;line-height:1.6;">
Note: This citation will be updated upon publication with the final journal information and DOI. </div>
    
  <div>For bug reporting, feature requests, or general feedback regarding Gel Xplorer, please reach out to Arif Z Nelson at
       <a href="mailto:arif.nelson@singaporetech.edu.sg"
          style="color:#0b5394;text-decoration:none;">arif.nelson@singaporetech.edu.sg</a></div>
</div>""")


st.html("""<div style="background:linear-gradient(135deg,#0b5394 0%,#073763 100%);
            border-radius:0.5rem;padding:1.7rem 2rem;margin-bottom:0.75rem;">
  <h1 style="font-family:Georgia,serif;color:#ffffff;margin:0;font-size:2.3rem;font-weight:600;">Gel Xplorer</h1>
  <p style="color:#d6e4f5;margin:0.45rem 0 0;font-size:0.98rem;line-height:1.45;">
    Framework for apparent gelation temperature determination beyond conventional crossover analysis</p>
  <p style="color:#aec8e8;margin:0.8rem 0 0;font-size:0.88rem;line-height:1.55;">
    A local, browser-based application that estimates the apparent gelation temperature from
    rheology temperature-ramp data &mdash; temperature (&deg;C), storage modulus (G') and loss
    modulus (G"). Developed for high-throughput material characterisation, the tool provides a rapid, reproducible, and user-friendly workflow for assessing thermal gelation behaviour directly within the browser.</p>
</div>""")
st.markdown(f":blue-badge[:material/science: Rheology] "
            f":gray-badge[:material/device_thermostat: Apparent gelation temperature] "
            f":gray-badge[v{VERSION}]")
st.session_state.pop("pending_parameters", None)
with st.container(border=True):
    st.markdown("""**How it works**

1. Upload a temperature ramp dataset, with temperature (°C), storage modulus G' and loss modulus G\"
2. Ensure that the columns are read correctly
3. Adjust the averaging and noise threshold accordingly
4. Click "Analyze" to get the apparent gelation temperature value. Figure and Excel download are available afterwards""")
st.subheader("Step 1. Raw data", anchor=False, icon=":material/upload_file:")
st.caption(f"Upload Excel (.xlsx) or CSV files with temperature ({CELSIUS}), G' (Pa) and G\" (Pa).")
uploads = st.file_uploader("Raw data", type=["xlsx", "csv"], accept_multiple_files=True,
                           label_visibility="collapsed")
sources = [(upload.name, upload.getvalue()) for upload in uploads]
if not sources:
    page_footer()
    st.stop()

st.subheader("Step 2. Check the imported columns", anchor=False, icon=":material/fact_check:")
st.caption("Pick the sheet(s) to analyze. The software automatically suggests the first data row and the "
           "temperature, G' and G\" columns; adjust them if needed and confirm against the preview before continuing.")
jobs = []
input_config = []
summaries = []
import_valid = True
for file_number, (filename, content) in enumerate(sources):
    prefix = f"input_{file_number}_{sha256(content).hexdigest()[:12]}"
    try:
        with st.spinner(f"Reading {filename}"):
            tables = read_tables(content, Path(filename).suffix)
    except Exception as error:
        st.error(f"{filename}: {error}")
        continue
    template = all(frame.shape[1] >= 28 and str(frame.iloc[0, 0]).startswith("Fill in the raw data")
                   for frame in tables.values() if len(frame))
    with st.expander(filename, expanded=True):
        sheets = st.multiselect("Sheets", list(tables), default=list(tables) if template else list(tables)[:1], key=prefix + "_sheets")
        if not sheets:
            continue
        sheet_panels = st.tabs(sheets) if len(sheets) > 1 else [st.container()]
        for sheet, sheet_panel in zip(sheets, sheet_panels):
            with sheet_panel:
                preview = tables[sheet]
                if preview.shape[1] < 3:
                    st.error(f"{sheet}: at least three columns are required.")
                    import_valid = False
                    continue
                suggestion = detect_layout(preview)
                sheet_key = prefix + "_" + sha256(sheet.encode()).hexdigest()[:10]
                if suggestion["unit_issue"]:
                    st.error(suggestion["unit_issue"])
                    import_valid = False
                first_row = int(st.number_input("First data row", min_value=1, value=suggestion["first_data_row"], key=sheet_key + "_start"))
                last_row = None

                def column_label(index, frame=preview, header_row=suggestion["header_row"]):
                    label = "" if header_row is None else str(frame.iloc[header_row - 1, index])
                    return f"{get_column_letter(index + 1)}: {label[:55]}"

                controls = st.columns(3)
                selected_columns = []
                for index, label in enumerate([f"Temperature ({CELSIUS})", "Storage Modulus G' (Pa)", 'Loss Modulus G" (Pa)']):
                    with controls[index]:
                        selected_columns.append(st.selectbox(label, list(range(preview.shape[1])), index=suggestion["columns"][index],
                                                             format_func=column_label, key=sheet_key + f"_column_{index}"))
                effective_first_row = first_row
                included_preview = preview.iloc[effective_first_row - 1:effective_first_row + 7, selected_columns].copy()
                included_preview.index = included_preview.index + 1
                st.dataframe(included_preview.fillna("").astype(str).rename(columns=lambda index: get_column_letter(index + 1)), height=180)
                try:
                    details = input_summary(preview, first_row, 0, selected_columns)
                    details.pop("Excluded measurements", None)
                    summaries.append({"Dataset": f"{filename} / {sheet}", "Import": suggestion["confidence"],
                                      **details})
                except ValueError as error:
                    st.error(str(error))
                    import_valid = False
                input_config.append({"file": filename, "sha256": sha256(content).hexdigest(), "sheets": [sheet],
                                     "import_notes": suggestion["notes"],
                                     "first_data_row": first_row, "last_data_row": last_row,
                                     "effective_first_data_row": effective_first_row,
                                     "columns_1_based": [index + 1 for index in selected_columns]})
                jobs.append((f"{file_number + 1}: {filename} / {sheet}", preview, effective_first_row,
                             last_row, selected_columns))

if summaries:
    st.markdown("**Input summary**")
    st.dataframe(pd.DataFrame(summaries), hide_index=True)

with st.form("analysis_settings", enter_to_submit=False):
    st.subheader("Step 3. Analysis settings", anchor=False, icon=":material/tune:")
    st.caption("Adjust the averaging and noise threshold, then click Analyze. "
               "The settings apply to all datasets and are checked only when you click Analyze.")
    st.info("There are no universal default values: the appropriate Moving average and Noise threshold "
            "depend on the datapoint density of your temperature ramp. Densely sampled data may need "
            "more averaging to suppress noise; sparsely sampled data may need little or none. "
            "Adjust them to suit your measurement.", icon=":material/info:")
    setting_columns = st.columns(2)
    with setting_columns[0]:
        block_text = st.text_input("Moving average",
                                   value=str(st.session_state.get("analysis_block_size", REPORTING_BLOCK_SIZE)),
                                   key="analysis_block_size_text",
                                   help="The number of consecutive raw points averaged into one point "
                                        "(non-overlapping). Set to 0 to disable averaging. "
                                        "Choose a value that suits your datapoint density.")
    with setting_columns[1]:
        threshold_text = st.text_input("Noise threshold",
                                       value=str(st.session_state.get("analysis_threshold", REPORTING_THRESHOLD)),
                                       key="analysis_threshold_text",
                                       help="Enter a finite, non-negative number. "
                                            "Eliminates potential experimental noise at early stage.")
    overrides = {}
    if len(jobs) > 1:
        with st.expander("Per-dataset adjustments (optional)", icon=":material/tune:"):
            st.caption("Leave a field blank to use the shared values above for that dataset.")
            header = st.columns([2, 1, 1])
            header[1].markdown("**Moving average**")
            header[2].markdown("**Noise threshold**")
            for label, *_ in jobs:
                override_key = "override_" + sha256(label.encode()).hexdigest()[:10]
                override_row = st.columns([2, 1, 1], vertical_alignment="center")
                override_row[0].markdown(label)
                block_override = override_row[1].text_input(
                    f"Moving average for {label}", value="", placeholder="shared",
                    key=override_key + "_block", label_visibility="collapsed")
                threshold_override = override_row[2].text_input(
                    f"Noise threshold for {label}", value="", placeholder="shared",
                    key=override_key + "_threshold", label_visibility="collapsed")
                overrides[label] = (block_override.strip(), threshold_override.strip())
    st.subheader("Step 4. Analyze", anchor=False, icon=":material/play_arrow:")
    st.caption("Click Analyze to calculate the apparent gelation temperature.")
    submitted = st.form_submit_button("Analyze", icon=":material/play_arrow:", type="primary",
                                      width="stretch", disabled=not jobs or not import_valid)

if submitted:
    parameter_errors = []
    block_size = threshold = None
    try:
        block_size = int(block_text)
        if not 0 <= block_size <= 101:
            raise ValueError
    except ValueError:
        parameter_errors.append("Moving average must be a whole number from 0 to 101 (0 disables averaging).")
    try:
        threshold = float(threshold_text)
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError
    except ValueError:
        parameter_errors.append("Noise threshold must be a finite, non-negative number.")
    dataset_settings, overrides_config = {}, {}
    for label, *_ in jobs:
        dataset_block, dataset_threshold = block_size, threshold
        block_override, threshold_override = overrides.get(label, ("", ""))
        if block_override:
            try:
                dataset_block = int(block_override)
                if not 0 <= dataset_block <= 101:
                    raise ValueError
            except ValueError:
                parameter_errors.append(f"{label}: Moving average must be a whole number from 0 to 101 (0 disables averaging).")
        if threshold_override:
            try:
                dataset_threshold = float(threshold_override)
                if not math.isfinite(dataset_threshold) or dataset_threshold < 0:
                    raise ValueError
            except ValueError:
                parameter_errors.append(f"{label}: Noise threshold must be a finite, non-negative number.")
        dataset_settings[label] = (dataset_block, dataset_threshold)
        if block_override or threshold_override:
            overrides_config[label] = {"block_size": dataset_block, "threshold": dataset_threshold}
    if parameter_errors:
        for error in parameter_errors:
            st.error(error)
        page_footer()
        st.stop()
    configuration = {"application_version": VERSION, "block_size": block_size, "threshold": threshold,
                     "temperature_unit": CELSIUS, "modulus_unit": "Pa", "inputs": input_config,
                     "reported_method": "log_second_derivative",
                     "averaging": "none" if block_size == 0 else "non_overlapping_blocks"}
    if overrides_config:
        configuration["per_dataset_overrides"] = overrides_config
    fingerprint = sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    records, failures = {}, {}
    with st.spinner("Analyzing"):
        for label, frame, first_row, last_row, columns in jobs:
            dataset_block, dataset_threshold = dataset_settings[label]
            try:
                records[label] = analyze(extract_raw(frame, first_row, last_row, columns),
                                         Settings(dataset_block, dataset_threshold))
                records[label]["preprocessing"] = {"first_data_row": first_row,
                                                   "effective_first_data_row": first_row}
            except Exception as error:
                failures[label] = str(error)
    configuration["analysis_utc"] = datetime.now(timezone.utc).isoformat()
    st.session_state["analysis_run"] = (fingerprint, records, failures, configuration)
    st.toast("Analysis complete", icon=":material/check_circle:")

run = st.session_state.get("analysis_run")
if not run or run[3]["inputs"] != input_config or not import_valid:
    page_footer()
    st.stop()
fingerprint, records, failures, saved_configuration = run
for label, error in failures.items():
    st.error(f"{label}: {error}")
if not records:
    page_footer()
    st.stop()

st.divider()
st.subheader("Results", anchor=False, icon=":material/insights:")
if "per_dataset_overrides" in saved_configuration:
    st.caption(f"Computed with Moving average = {saved_configuration['block_size']} and "
               f"noise threshold = {saved_configuration['threshold']:g}, with per-dataset adjustments "
               "shown in the comparison table. Edits in Step 3 take effect only after you click Analyze again.")
else:
    st.caption(f"Computed with Moving average = {saved_configuration['block_size']} and "
               f"noise threshold = {saved_configuration['threshold']:g}. "
               "Edits in Step 3 take effect only after you click Analyze again.")
summary_slot = st.empty()
if len(records) == 1:
    selected = next(iter(records))
else:
    selected = st.selectbox("Dataset", list(records),
                            help="Choose which dataset's result and figure to view below.")
result = records[selected]
for warning in result["warnings"]:
    if warning.startswith("Final temperature hold:"):
        st.info(warning)
value = result["results"]["log_inflection"]
metric_slot = st.empty()
marker_temperature = value
with st.container():
    st.subheader("Figure", anchor=False, icon=":material/show_chart:")
    marker_key = f"marker_{fingerprint}_{selected}"
    st.caption("The controls under each plot change the appearance only; they do not affect "
               "the apparent gelation temperature or Excel calculations.")
    upper_chart = st.container(key="scientific_figure_a")
    with st.expander("Customise upper plot (appearance only)", icon=":material/tune:"):
        base_defaults = axis_defaults(result)
        st.markdown("**Temperature axis — applies to both plots**")
        axis_columns = st.columns(3)
        with axis_columns[0]:
            temperature_min = float(st.number_input(f"Minimum temperature ({CELSIUS})", value=base_defaults["temperature_min"], key=marker_key + "_xmin"))
        with axis_columns[1]:
            temperature_max = float(st.number_input(f"Maximum temperature ({CELSIUS})", value=base_defaults["temperature_max"], key=marker_key + "_xmax"))
        with axis_columns[2]:
            temperature_step = float(st.number_input(f"Major temperature interval ({CELSIUS})", min_value=0.01,
                                                      value=base_defaults["temperature_step"], key=marker_key + "_xstep"))
        st.markdown("**Modulus axis (log scale)** — enter powers of 10: for example, 2 means 100 Pa.")
        modulus_columns = st.columns(2)
        with modulus_columns[0]:
            low_power = float(st.number_input("Minimum modulus exponent (10^n)", value=base_defaults["modulus_min_power"], step=1.0, key=marker_key + "_ymin"))
        with modulus_columns[1]:
            high_power = float(st.number_input("Maximum modulus exponent (10^n)", value=base_defaults["modulus_max_power"], step=1.0, key=marker_key + "_ymax"))
    lower_chart = st.container(key="scientific_figure_b")
    with st.expander("Customise lower plot (appearance only)", icon=":material/tune:"):
        valid_derivative_points = int(derivative_plot_data(result).iloc[:, 1].notna().sum())
        hide_last = int(st.number_input("Hide last derivative points", min_value=0,
                                        max_value=max(1, valid_derivative_points - 1), value=0, step=1,
                                        disabled=valid_derivative_points <= 1, key=marker_key + "_hide_last",
                                        help="Plot only: hides final calculated derivative points without changing the reported result or Excel calculations."))
        defaults = axis_defaults(result, hide_last)
        st.markdown("**Second-derivative axis**")
        derivative_columns = st.columns(2)
        derivative_step = max((defaults["derivative_max"] - defaults["derivative_min"]) / 20, 1e-8)
        with derivative_columns[0]:
            derivative_min = float(st.number_input("Minimum derivative", value=defaults["derivative_min"],
                                                   step=derivative_step, format="%.6g", key=marker_key + "_dymin"))
        with derivative_columns[1]:
            derivative_max = float(st.number_input("Maximum derivative", value=defaults["derivative_max"],
                                                   step=derivative_step, format="%.6g", key=marker_key + "_dymax"))
    axes = {"temperature_min": temperature_min, "temperature_max": temperature_max,
            "temperature_step": temperature_step, "modulus_min_power": low_power, "modulus_max_power": high_power,
            "derivative_min": derivative_min, "derivative_max": derivative_max,
            "derivative_exclude_last": hide_last}
    if temperature_min >= temperature_max or low_power >= high_power or derivative_min >= derivative_max:
        st.error("Each axis maximum must be greater than its minimum.")
        axes = defaults
    axis_positions = st.session_state.setdefault("figure_axis_settings", {})
    axis_positions[marker_key] = axes
    figure = build_figure(result, marker_temperature, axis_settings=axes)
    with upper_chart:
        st.plotly_chart(build_figure(result, marker_temperature, panel="A", axis_settings=axes),
                        width="stretch",
                        config={"toImageButtonOptions": {"format": "svg", "filename": "gelation_figure_moduli"}})
    with lower_chart:
        st.plotly_chart(build_figure(result, marker_temperature, panel="B", axis_settings=axes),
                        width="stretch",
                        config={"toImageButtonOptions": {"format": "svg", "filename": "gelation_figure_derivative"}})
    st.subheader("Step 5. Export results", anchor=False, icon=":material/download:")
    st.caption("Download the figure and Excel workbook.")
    export_row = st.container(horizontal=True, vertical_alignment="bottom")
    with export_row:
        figure_format = st.selectbox("Figure format", ["PNG", "SVG", "PDF", "HTML"], width=200)
    extension = figure_format.lower()
    mime = {"PNG": "image/png", "SVG": "image/svg+xml", "PDF": "application/pdf", "HTML": "text/html"}[figure_format]

    def current_figure_download(snapshot=figure, chosen_format=extension):
        if chosen_format == "html":
            return snapshot.to_html(include_plotlyjs=True)
        return figure_image(snapshot, chosen_format)

    with export_row:
        st.download_button("Download figure", current_figure_download,
                           f"gelation_figure.{extension}", mime, icon=":material/download:", on_click="ignore")
markers = {label: item["results"]["log_inflection"] for label, item in records.items()}
value_column = f"Apparent gelation temperature ({CELSIUS})"
per_dataset_run = "per_dataset_overrides" in saved_configuration
summary = pd.DataFrame([
    {"Dataset": label, value_column: markers[label],
     **({"Moving average": item["settings"]["block_size"],
         "Noise threshold": item["settings"]["threshold"]} if per_dataset_run else {})}
    for label, item in records.items()])
if len(records) > 1:
    with summary_slot.container():
        st.markdown("**Comparison across datasets**")
        display_summary = summary.copy()
        display_summary[value_column] = display_summary[value_column].map(
            lambda value: "Not found" if pd.isna(value) else f"{value:.1f}")
        st.dataframe(display_summary, hide_index=True)
with metric_slot.container():
    with st.container(horizontal=True):
        st.metric("Apparent gelation temperature",
                  "Not found" if marker_temperature is None else f"{marker_temperature:.1f} {CELSIUS}",
                  border=True, width="stretch")
        crossover = crossover_temperature(result["raw"])
        if crossover is not None:
            st.metric("Moduli crossover temperature", f"{crossover:.2f} {CELSIUS}",
                      border=True, width="stretch")
    displayed = derivative_plot_data(result, hide_last)
    if marker_temperature is not None and marker_temperature not in displayed.temperature_C.to_numpy():
        st.warning("The reported temperature is outside the figure-only retained derivative points.")

export_configuration = {**saved_configuration, "figure_axes": {
    label: axis_positions.get(f"marker_{fingerprint}_{label}", axis_defaults(item))
    for label, item in records.items()}}
try:
    with st.spinner("Preparing Excel workbook"):
        workbook_bytes = excel_download(records, markers, export_configuration, failures)
    with export_row:
        st.download_button("Download Excel workbook", workbook_bytes, file_name="gelation_results.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")
except Exception as error:
    st.error(f"Excel export unavailable: {error}")
page_footer()
