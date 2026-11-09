import math
from pathlib import Path
import unittest

from openpyxl import load_workbook
import pandas as pd

from analysis import Settings, analyze, log_inflection_candidates


# Excel workbooks holding the original spreadsheet calculation. Several tests
# check that this app reproduces their numbers.
DATA = Path(__file__).resolve().parent / "tests" / "data"
REFERENCE = DATA / "excel_reference_template.xlsx"
SAMPLE_PPI = DATA / "sample_ppi_raw.xlsx"  # raw temperature, G', G" only


class ImportSuggestions(unittest.TestCase):
    def test_reordered_columns_metadata_and_unit_row(self):
        from importing import detect_layout, extract_raw, input_summary

        frame = pd.DataFrame([["Instrument export", None, None, None],
                              ["Loss modulus G\"", "Time", "Temperature", "Storage modulus G'"],
                              ["Pa", "s", "C", "Pa"], [1, 0, 25, 2], [2, 1, 26, 3]])
        suggested = detect_layout(frame)
        self.assertEqual(suggested["columns"], [2, 3, 0])
        self.assertEqual(suggested["first_data_row"], 4)
        self.assertEqual(suggested["confidence"], "Detected")
        raw = extract_raw(frame, 4, None, suggested["columns"])
        self.assertEqual(raw.iloc[0].tolist(), [25, 2, 1])
        summary = input_summary(frame, 4, 1, suggested["columns"])
        self.assertEqual(summary["Measurements"], 1)
        self.assertEqual(summary["Minimum temperature"], 26)

    def test_headerless_ambiguous_and_unsupported_units(self):
        from importing import detect_layout

        raw = pd.DataFrame([[25, 1, 2], [26, 2, 3]])
        self.assertEqual(detect_layout(raw)["first_data_row"], 1)
        self.assertEqual(detect_layout(raw)["confidence"], "Needs confirmation")
        units = pd.DataFrame([["Temp (C)", "G' (kPa)", 'G" (kPa)'], [25, 1, 2]])
        self.assertIsNotNone(detect_layout(units)["unit_issue"])
        duplicate = pd.DataFrame([["Temperature", "Storage", "Storage", "Loss"], [25, 1, 2, 3]])
        self.assertEqual(detect_layout(duplicate)["confidence"], "Needs confirmation")


class ReportedWarnings(unittest.TestCase):
    def test_essential_warnings_keep_only_the_reported_method(self):
        from analysis import essential_warnings

        raw = pd.DataFrame({"temperature": range(6), "storage": [1.0] * 6, "loss": [0.1] * 6})
        warnings = essential_warnings(analyze(raw))
        self.assertTrue(any("Fewer than five" in warning for warning in warnings))
        self.assertTrue(any("log10(G*) positive-to-negative" in warning for warning in warnings))
        self.assertFalse(any("First derivative:" in warning for warning in warnings))


class WorkbookParity(unittest.TestCase):
    def test_zero_disables_averaging_in_analysis_and_excel(self):
        from io import BytesIO
        from exports import export_workbook

        raw = pd.DataFrame({"temperature": range(12), "storage": [2.0 ** (index / 2) for index in range(12)],
                            "loss": [0.2] * 12})
        result = analyze(raw, Settings(block_size=0))
        unchanged = analyze(raw, Settings(block_size=1))
        pd.testing.assert_frame_equal(result["blocks"], unchanged["blocks"])
        self.assertEqual(len(result["blocks"]), len(raw))
        self.assertEqual(result["settings"]["block_size"], 0)
        self.assertEqual(result["results"], unchanged["results"])
        exported = load_workbook(BytesIO(export_workbook({"No averaging": result})), data_only=True)
        output = exported.worksheets[1]
        self.assertEqual(output.max_row, len(raw) + 1)
        for index, point in result["blocks"].iterrows():
            self.assertEqual(output[f"A{index + 2}"].value, point.temperature)
            self.assertAlmostEqual(output[f"B{index + 2}"].value, point["complex"])
        self.assertEqual(exported["Summary"]["C2"].value, 0)
        exported.close()
        with self.assertRaises(ValueError):
            analyze(raw, Settings(block_size=-1))

    def test_sample_raw_data_matches_excel_and_exports(self):
        from io import BytesIO
        from exports import DATA_COLUMNS, export_workbook

        # Excel gave 54.82 (log) and 49.21 (linear) for this raw sample at threshold 0.02.
        sheet = load_workbook(SAMPLE_PPI, read_only=True).worksheets[0]
        rows = list(sheet.iter_rows(min_row=2, max_col=3, values_only=True))
        result = analyze(pd.DataFrame(rows, columns=["temperature", "storage", "loss"]),
                         Settings(threshold=0.02))
        self.assertAlmostEqual(result["results"]["log_inflection"], 54.82333333333333, places=10)
        self.assertAlmostEqual(result["results"]["linear_inflection"], 49.20666666666667, places=10)
        book = load_workbook(BytesIO(export_workbook({"Sample": result})), data_only=True)
        self.assertEqual(book.sheetnames, ["Summary", "Sample"])
        self.assertEqual(book["Summary"]["B2"].value, result["results"]["log_inflection"])
        self.assertEqual(book["Summary"]["B2"].number_format, "0.0")
        output = book["Sample"]
        self.assertEqual(output["E2"].value, result["results"]["log_inflection"])
        self.assertEqual(output["E2"].number_format, "0.0")
        self.assertEqual(output.max_row, len(result["blocks"]) + 1)
        for index, block in result["blocks"].iterrows():
            for column, (field, _) in enumerate(DATA_COLUMNS, 1):
                value = output.cell(index + 2, column).value
                if math.isnan(block[field]):
                    self.assertIsNone(value)
                else:
                    self.assertTrue(math.isclose(value, block[field], rel_tol=1e-10, abs_tol=1e-10))

    def test_partial_blocks_follow_excel_padding(self):
        from io import BytesIO
        from exports import export_workbook

        for count in [4, 5]:
            with self.subTest(measurements=count):
                raw = pd.DataFrame({"temperature": range(count), "storage": [9.0] * count,
                                    "loss": [0.0] * count})
                result = analyze(raw)
                self.assertEqual(result["blocks"].complex.iloc[-1], 9.0 * (count % 3) / 3)
                self.assertEqual(result["blocks"].temperature.iloc[-1], raw.temperature.iloc[3:].mean())
                exported = load_workbook(BytesIO(export_workbook({"Partial block": result})), data_only=True)
                output = exported.worksheets[1]
                self.assertEqual(output.max_row, len(result["blocks"]) + 1)
                self.assertEqual(output[f"B{output.max_row}"].value, result["blocks"].complex.iloc[-1])
                self.assertEqual(output[f"A{output.max_row}"].value, result["blocks"].temperature.iloc[-1])
                exported.close()

    def test_all_frequency_sheets(self):
        self.assertTrue(REFERENCE.exists(), f"Reference workbook missing: {REFERENCE}")
        book = load_workbook(REFERENCE, data_only=True)
        checked = 0
        mapping = {"E": "temperature", "F": "complex", "H": "delta_temperature",
                   "I": "delta_complex", "J": "linear_derivative", "N": "log_derivative",
                   "Q": "forward_temperature_span", "R": "half_span", "S": "log_complex",
                   "T": "delta_log_complex", "U": "linear_second_derivative",
                   "V": "log_second_derivative"}
        for sheet in book:
            with self.subTest(sheet=sheet.title):
                rows = [row for row in sheet.iter_rows(min_row=5, max_col=3, values_only=True)
                        if isinstance(row[0], (int, float))]
                result = analyze(pd.DataFrame(rows, columns=["temperature", "storage", "loss"]),
                                 Settings(threshold=sheet["AB3"].value))
                for address, actual in [("G4", result["maximum_modulus"]),
                                        ("G6", result["maximum_temperature"]),
                                        ("M6", result["linear_threshold_temperature"]),
                                        ("P6", result["log_threshold_temperature"])]:
                    self.assertTrue(math.isclose(actual, sheet[address].value, rel_tol=1e-10, abs_tol=1e-10), address)
                    checked += 1
                for address, key in [("Z3", "linear_peak"), ("Z4", "log_peak"),
                                     ("Z5", "linear_inflection"), ("Z6", "log_inflection")]:
                    expected = sheet[address].value
                    actual = result["results"][key]
                    if isinstance(expected, str) and expected.startswith("#"):
                        self.assertIsNone(actual, address)
                    else:
                        self.assertEqual(actual, expected, address)
                    checked += 1
                for index, actual in result["raw"].iterrows():
                    expected = sheet[f"D{index + 5}"].value
                    self.assertTrue(math.isclose(actual["complex"], expected, rel_tol=1e-10, abs_tol=1e-10))
                    checked += 1
                for index, block in result["blocks"].iterrows():
                    row = 6 + 3 * index
                    for column, field in mapping.items():
                        expected = sheet[f"{column}{row}"].value
                        if isinstance(expected, (int, float)):
                            self.assertTrue(math.isclose(block[field], expected, rel_tol=1e-10, abs_tol=1e-10),
                                            f"{sheet.title}!{column}{row}: {block[field]} != {expected}")
                            checked += 1
                        elif expected is None or (isinstance(expected, str) and expected.startswith("#")):
                            self.assertTrue(pd.isna(block[field]), f"{column}{row} should be undefined")
        book.close()

    def test_input_guards_and_no_result(self):
        raw = pd.DataFrame({"temperature": range(21), "storage": [1.0] * 21, "loss": [0.0] * 21})
        self.assertTrue(all(value is None for value in analyze(raw)["results"].values()))
        self.assertTrue(all(value is None for value in analyze(raw, Settings(threshold=0))["results"].values()))
        with self.assertRaises(ValueError):
            analyze(raw, Settings(threshold=-0.01))
        raw.loc[1, "temperature"] = 0
        with self.assertRaises(ValueError):
            analyze(raw, Settings(block_size=1))

    def test_repeated_temperatures_retained_when_block_means_increase(self):
        from io import BytesIO
        from exports import export_workbook
        from figures import derivative_plot_data

        raw = pd.DataFrame({"temperature": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 13],
                            "storage": [2.0 ** (i / 2) for i in range(15)], "loss": [0.2] * 15})
        original = raw.copy()
        result = analyze(raw)
        pd.testing.assert_frame_equal(result["input_raw"], original)
        self.assertEqual(len(result["raw"]), 15)
        pd.testing.assert_frame_equal(result["blocks"], analyze(raw.iloc[:-1])["blocks"])
        self.assertEqual(result["hold_rows_excluded"], 1)
        expected_modulus = math.sqrt(raw.storage.iloc[-1] ** 2 + 0.2 ** 2)
        self.assertAlmostEqual(result["raw"]["complex"].iloc[-1], expected_modulus)
        self.assertTrue(any("Final temperature hold:" in note for note in result["warnings"]))
        derivative_plot_data(result)
        workbook = load_workbook(BytesIO(export_workbook({"Repeats": result})), data_only=True)
        self.assertEqual(workbook["Repeats"].max_row, len(result["blocks"]) + 1)
        workbook.close()
        for size in (0, 1):
            with self.subTest(block_size=size):
                result = analyze(raw, Settings(block_size=size))
                pd.testing.assert_frame_equal(result["blocks"], analyze(raw.iloc[:-1], Settings(block_size=size))["blocks"])
        flat = raw.copy()
        flat["temperature"] = 25
        with self.assertRaisesRegex(ValueError, "heating ramp before"):
            analyze(flat)
        decreasing = raw.copy()
        decreasing.loc[1, "temperature"] = -1
        with self.assertRaisesRegex(ValueError, "non-decreasing"):
            analyze(decreasing)
        pd.testing.assert_frame_equal(raw, original)


class TerminalTemperatureHold(unittest.TestCase):
    def ramp(self, count=54):
        return pd.DataFrame({"temperature": [float(i) for i in range(count)],
                             "storage": [10 ** (0.3 * (i // 3) + 0.15 * math.sin(1.2 * (i // 3)))
                                         for i in range(count)],
                             "loss": [0.1] * count})

    def test_exact_and_noisy_holds_leave_ramp_calculations_unchanged(self):
        from figures import derivative_plot_data

        for count in (53, 54):
            ramp = self.ramp(count)
            target = ramp.temperature.iloc[-1]
            for offsets in ([0.0] * 30, [0.04, -0.04, 0.01, -0.03, 0.0] * 4):
                hold = pd.DataFrame({"temperature": [target + offset for offset in offsets],
                                     "storage": [-100.0, 1e9] * (len(offsets) // 2),
                                     "loss": [0.1] * len(offsets)})
                raw = pd.concat([ramp, hold], ignore_index=True)
                original = raw.copy(deep=True)
                for size in (0, 1, 3, 5):
                    with self.subTest(count=count, offsets=offsets[:2], size=size):
                        baseline = analyze(ramp, Settings(block_size=size))
                        result = analyze(raw, Settings(block_size=size))
                        pd.testing.assert_frame_equal(result["blocks"], baseline["blocks"])
                        self.assertEqual(result["results"], baseline["results"])
                        self.assertEqual(result["maximum_modulus"], baseline["maximum_modulus"])
                        self.assertEqual(result["log_threshold_temperature"], baseline["log_threshold_temperature"])
                        self.assertEqual(result["hold_rows_excluded"], len(hold))
                        pd.testing.assert_frame_equal(result["input_raw"], original)
                        self.assertEqual(len(result["raw"]), len(raw))
                        pd.testing.assert_frame_equal(derivative_plot_data(result), derivative_plot_data(baseline))
                pd.testing.assert_frame_equal(raw, original)

    def test_ordinary_ramp_internal_repeats_and_cooling_guards(self):
        ramp = self.ramp()
        ramp["temperature"] *= 0.01
        self.assertEqual(analyze(ramp)["hold_rows_excluded"], 0)
        ramp = self.ramp()
        ramp.loc[1, "temperature"] = 0
        self.assertEqual(analyze(ramp)["hold_rows_excluded"], 0)
        with self.assertRaisesRegex(ValueError, "Averaged block temperatures"):
            analyze(ramp, Settings(block_size=0))
        ramp = self.ramp()
        ramp.loc[len(ramp) - 1, "temperature"] = 51.5
        with self.assertRaisesRegex(ValueError, "non-decreasing"):
            analyze(ramp)
        ramp = self.ramp()
        ramp["temperature"] = 25.0
        with self.assertRaisesRegex(ValueError, "heating ramp before"):
            analyze(ramp)

    def test_raw_export_and_plot_retain_hold_and_identify_excluded_rows(self):
        from io import BytesIO
        from exports import export_workbook
        from figures import build_figure

        ramp = self.ramp()
        raw = pd.concat([ramp, ramp.iloc[[-1]], ramp.iloc[[-1]], ramp.iloc[[-1]]], ignore_index=True)
        result = analyze(raw)
        figure = build_figure(result)
        self.assertEqual(len(figure.data[0].x), len(raw))
        workbook = load_workbook(BytesIO(export_workbook({"Hold": result})), data_only=True)
        self.assertIn("Final temperature hold:", workbook["Summary"]["E2"].value)
        self.assertEqual(workbook["Hold"].max_row, len(result["blocks"]) + 1)
        exported = workbook["Raw Hold"]
        self.assertEqual(exported.max_row, len(raw) + 1)
        self.assertEqual([exported.cell(i + 2, 4).value for i in range(len(raw))],
                         [True] * len(ramp) + [False] * 3)
        self.assertEqual(exported.cell(exported.max_row, 1).value, 53)
        workbook.close()

    def test_upload_hold_notice_and_export(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        ramp = self.ramp()
        raw = pd.concat([ramp, ramp.iloc[[-1]], ramp.iloc[[-1]]], ignore_index=True)
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "hold.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False):
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            result = next(iter(app.session_state["analysis_run"][1].values()))
            self.assertEqual(result["hold_rows_excluded"], 2)
            self.assertTrue(any("excluded 2 rows" in notice.value for notice in app.info))
            self.assertEqual(result["results"], analyze(ramp)["results"])


class Figures(unittest.TestCase):
    def test_major_ticks_include_100_on_temperature_and_modulus_axes(self):
        from figures import build_figure

        raw = pd.DataFrame({"temperature": range(21),
                            "storage": [2.0 ** (index / 2) for index in range(21)],
                            "loss": [4.0] * 21})
        result = analyze(raw)
        axes = {"temperature_min": 20, "temperature_max": 100, "temperature_step": 30,
                "modulus_min_power": 0, "modulus_max_power": 4}
        for panel in (None, "A", "B"):
            with self.subTest(panel=panel):
                figure = build_figure(result, panel=panel, axis_settings=axes)
                self.assertEqual(list(figure.layout.xaxis.tickvals), [30, 60, 90, 100])
                if panel is None:
                    self.assertIn(100, figure.layout.xaxis2.tickvals)
                if panel != "B":
                    self.assertIn(100, figure.layout.yaxis.tickvals)
                    self.assertIn("10<sup>2</sup>", figure.layout.yaxis.ticktext)
        cropped = build_figure(result, axis_settings={**axes, "temperature_max": 80})
        self.assertNotIn(100, cropped.layout.xaxis.tickvals)

    def test_restore_noise_region_points_without_changing_calculations(self):
        from io import BytesIO
        import numpy as np
        from exports import export_workbook
        from figures import derivative_plot_data, build_figure

        raw = pd.DataFrame({"temperature": range(60),
                            "storage": [10 ** (0.2 * (i // 3) + 0.15 * math.sin(i // 3))
                                        for i in range(60)], "loss": [0.1] * 60})
        raw.loc[[1, 16], "storage"] *= -1
        for size in (0, 3, 4):
            with self.subTest(block_size=size):
                result = analyze(raw, Settings(size, 0.02))
                original_blocks = result["blocks"].copy()
                original_raw = result["raw"].copy()
                original_results = result["results"].copy()
                original_boundary = result["log_threshold_temperature"]
                before = export_workbook({"Sample": result})
                plotted = derivative_plot_data(result)
                values = plotted.iloc[:, 1]
                self.assertGreater(values.notna().sum(), original_blocks.log_second_derivative.notna().sum())
                self.assertTrue(values.iloc[:2].isna().all())
                self.assertTrue(values.iloc[-2:].isna().all())
                self.assertTrue(values[plotted.temperature_C < original_boundary].notna().any())
                calculated = original_blocks.log_second_derivative.notna()
                pd.testing.assert_series_equal(values[calculated],
                                               original_blocks.log_second_derivative[calculated],
                                               check_names=False)
                modulus = np.sqrt(raw.storage ** 2 + raw.loss ** 2)
                block_size = max(1, size)
                means = [modulus.iloc[i:i + block_size].sum() / block_size
                         for i in range(0, len(raw), block_size)]
                signal = np.log10(means)
                temperature = original_blocks.temperature.to_numpy()
                expected = (-signal[0] + 16 * signal[1] - 30 * signal[2]
                            + 16 * signal[3] - signal[4]) / (12 * (temperature[4] - temperature[2]) ** 2)
                self.assertAlmostEqual(values.iloc[2], expected)
                figure = build_figure(result)
                curve = next(trace for trace in figure.data if trace.name == "Log second derivative")
                np.testing.assert_allclose(curve.y, values, equal_nan=True)
                pd.testing.assert_frame_equal(result["blocks"], original_blocks)
                pd.testing.assert_frame_equal(result["raw"], original_raw)
                self.assertEqual(result["results"], original_results)
                self.assertEqual(result["log_threshold_temperature"], original_boundary)
                after = export_workbook({"Sample": result})
                before_book = load_workbook(BytesIO(before), data_only=True)
                after_book = load_workbook(BytesIO(after), data_only=True)
                self.assertEqual([list(sheet.values) for sheet in before_book],
                                 [list(sheet.values) for sheet in after_book])
                before_book.close()
                after_book.close()

    def test_exclude_final_derivative_points_is_display_only(self):
        from figures import axis_defaults, derivative_plot_data, build_figure

        raw = pd.DataFrame({"temperature": range(54),
                            "storage": [10 ** (0.3 * (index // 3) + 0.15 * math.sin(1.2 * (index // 3)))
                                        for index in range(54)], "loss": [0.1] * 54})
        result = analyze(raw)
        original = result["blocks"].copy()
        original_result = result["results"].copy()
        full = derivative_plot_data(result)
        trimmed = derivative_plot_data(result, 2)
        self.assertEqual(trimmed.iloc[:, 1].notna().sum(), full.iloc[:, 1].notna().sum() - 2)
        figure = build_figure(result, axis_settings={"derivative_exclude_last": 2})
        curve = next(trace for trace in figure.data if trace.name == "Log second derivative")
        self.assertEqual(list(curve.x), trimmed.temperature_C.tolist())
        self.assertEqual(len(figure.data[0].x), len(raw))
        defaults = axis_defaults(result, 2)
        self.assertEqual(figure.layout.yaxis2.range, (defaults["derivative_min"], defaults["derivative_max"]))
        last_crossing = log_inflection_candidates(result)[-1]
        point_count = int(full.loc[full.temperature_C >= last_crossing].iloc[:, 1].notna().sum())
        hidden_marker = build_figure(result, last_crossing, axis_settings={"derivative_exclude_last": point_count})
        self.assertFalse(any(trace.name == "Selected marker" for trace in hidden_marker.data))
        pd.testing.assert_frame_equal(result["blocks"], original)
        self.assertEqual(result["results"], original_result)
        for invalid in [-1, 0.5, int(full.iloc[:, 1].notna().sum())]:
            with self.assertRaises(ValueError):
                derivative_plot_data(result, invalid)

    def test_static_figure_downloads(self):
        from io import BytesIO
        from PIL import Image
        from exports import figure_image
        from figures import build_figure

        raw = pd.DataFrame({"temperature": range(21), "storage": [2.0 ** (index / 2) for index in range(21)],
                            "loss": [4.0] * 21})
        figure = build_figure(analyze(raw))
        png = figure_image(figure, "png")
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.size, (3600, 3000))
            self.assertGreater(len(image.getcolors(maxcolors=2000000) or []), 10)
        svg = figure_image(figure, "svg")
        self.assertIn(b"<svg", svg)
        self.assertIn(b"Modulus", svg)
        self.assertTrue(figure_image(figure, "pdf").startswith(b"%PDF"))

    def test_colors_crossover_threshold_and_marker(self):
        from figures import crossover_temperature, derivative_plot_data, marker_value, build_figure

        raw = pd.DataFrame({"temperature": range(21), "storage": [2.0 ** (index / 2) for index in range(21)],
                            "loss": [4.0] * 21})
        result = analyze(raw)
        self.assertEqual(crossover_temperature(result["raw"]), 4)
        result["blocks"]["log_second_derivative"] = [float("nan"), float("nan"), 1, -1, 1, -1, float("nan")]
        result["results"]["log_inflection"] = 10.0
        result["log_threshold_temperature"] = 7.0
        figure = build_figure(result, marker_temperature=10)
        self.assertEqual([trace.line.color for trace in figure.data[:3]], ["#c62828", "#245bc4", "#111111"])
        self.assertTrue(any(shape.type == "rect" and shape.x1 == 7 / 20 for shape in figure.layout.shapes))
        selected_marker = next(trace for trace in figure.data if trace.name == "Selected marker")
        self.assertEqual(selected_marker.x[0], 10)
        self.assertAlmostEqual(selected_marker.y[0], marker_value(result["blocks"], 10))
        swatches = [trace for trace in figure.data if trace.showlegend]
        self.assertEqual([trace.name for trace in swatches], ["G'", 'G"', "G*"])
        self.assertTrue(all(trace.mode == "markers" and trace.marker.size == 15 for trace in swatches))
        self.assertGreater(figure.layout.legend.x, 1)
        self.assertFalse(any("Noise" in (annotation.text or "") for annotation in figure.layout.annotations))
        noise_key = next(shape for shape in figure.layout.shapes if shape.type == "rect")
        self.assertEqual((noise_key.name, noise_key.legend, noise_key.showlegend), ("Noise threshold", "legend2", True))
        marker_keys = [shape for shape in figure.layout.shapes if shape.type == "line" and shape.showlegend]
        self.assertEqual(len(marker_keys), 2)
        self.assertTrue(all(shape.line.dash == "6px,4px" for shape in marker_keys))
        exported = derivative_plot_data(result)
        curve = next(trace for trace in figure.data if trace.name == "Log second derivative")
        self.assertEqual(exported.temperature_C.tolist(), list(curve.x))
        pd.testing.assert_series_equal(exported.iloc[:, 1], result["blocks"].log_second_derivative, check_names=False)
        self.assertEqual(next(trace for trace in figure.data if trace.name == "Reported gelation").x[0], 10)
        self.assertEqual(figure.layout.xaxis.range, figure.layout.xaxis2.range)
        self.assertEqual(figure.layout.xaxis.dtick, 20)
        self.assertEqual(figure.layout.xaxis.minor.dtick, 10)
        self.assertEqual(figure.layout.yaxis.ticks, "inside")
        self.assertEqual(figure.layout.yaxis.minor.ticks, "inside")
        for axis in [figure.layout.xaxis, figure.layout.xaxis2, figure.layout.yaxis, figure.layout.yaxis2]:
            self.assertEqual(axis.tickcolor, axis.linecolor)
            self.assertEqual(axis.minor.tickcolor, axis.linecolor)
            self.assertEqual(axis.minor.tickwidth, axis.tickwidth)
            self.assertEqual(axis.tickfont.size, 17)
        self.assertFalse(figure.layout.images)
        self.assertIn("log<sub>10</sub>(G*)", figure.layout.yaxis2.title.text)
        self.assertEqual(figure.layout.margin.pad, 0)
        self.assertIn("10<sup>0</sup>", figure.layout.yaxis.ticktext)
        self.assertFalse(any(annotation.text in ["A)", "B)"] for annotation in figure.layout.annotations))
        for shape in figure.layout.shapes:
            if shape.type == "line" and shape.yref == "y domain" and shape.x0 == shape.x1:
                self.assertEqual(shape.y0, 0)
        shaded = next(shape for shape in figure.layout.shapes if shape.type == "rect")
        self.assertEqual(shaded.xref, "x2 domain")
        self.assertEqual(shaded.yref, "y2 domain")
        self.assertEqual(shaded.x0, 0)
        self.assertEqual((shaded.y0, shaded.y1), (0, 1))
        result["log_threshold_temperature"] = 13.0
        changed = build_figure(result, panel="B")
        self.assertTrue(any(shape.type == "rect" and shape.x1 == 13 / 20 for shape in changed.layout.shapes))
        self.assertIsNone(marker_value(result["blocks"], -1))
        self.assertFalse(any(trace.name == "Selected marker" for trace in changed.data))
        result["log_threshold_temperature"] = 7.0
        rejected = build_figure(result, marker_temperature=13, panel="B")
        self.assertEqual(next(trace for trace in rejected.data if trace.name == "Selected marker").x[0], 10)

    def test_crossing_direction_gaps_and_noise_region(self):
        result = {"log_threshold_temperature": 1,
                  "blocks": pd.DataFrame({"temperature": range(11),
                                          "log_second_derivative": [float("nan"), 1, -1, 1, 0, -1, 1, float("nan"), -1, 1, -1]})}
        self.assertEqual(log_inflection_candidates(result), [2, 10])
        result["log_threshold_temperature"] = 3
        self.assertEqual(log_inflection_candidates(result), [10])
        result["log_threshold_temperature"] = None
        self.assertEqual(log_inflection_candidates(result), [])


class FirstUseWorkflow(unittest.TestCase):
    def test_analysis_only_runs_on_submit_and_drafts_do_not_show_errors(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        raw = pd.DataFrame({"temperature": range(54),
                            "storage": [2.0 ** (index / 2) for index in range(54)],
                            "loss": [0.1] * 54})
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "submit.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), \
                patch("streamlit.download_button", return_value=False), \
                patch("analysis.analyze", wraps=analyze) as calculate:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.metric)
            self.assertEqual(calculate.call_count, 0)
            self.assertEqual(app.text_input(key="analysis_block_size_text").value, "3")
            self.assertEqual(app.text_input(key="analysis_threshold_text").value, "0.02")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(calculate.call_count, 1)
            saved_fingerprint = app.session_state["analysis_run"][0]
            for block, threshold in [("", ""), ("-", "."), ("2.5", "1e"), ("5", "0.03")]:
                with self.subTest(block=block, threshold=threshold):
                    app.text_input(key="analysis_block_size_text").set_value(block)
                    app.text_input(key="analysis_threshold_text").set_value(threshold).run()
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    self.assertEqual(calculate.call_count, 1)
                    self.assertEqual(app.session_state["analysis_run"][0], saved_fingerprint)
                    self.assertTrue(app.metric)
            app.text_input(key="analysis_block_size_text").set_value("5")
            app.text_input(key="analysis_threshold_text").set_value("0.03")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(calculate.call_count, 2)
            self.assertEqual(app.session_state["analysis_run"][3]["block_size"], 5)
            self.assertEqual(app.session_state["analysis_run"][3]["threshold"], 0.03)
            app.run()
            self.assertEqual(calculate.call_count, 2)
            uploaded.name = "different.csv"
            app.run()
            self.assertFalse(app.exception)
            self.assertFalse(app.metric)
            self.assertEqual(calculate.call_count, 2)

    def test_invalid_parameters_reported_only_after_submit(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        uploaded = BytesIO(b"Temperature,Storage,Loss\n25,1,2\n26,2,3\n27,3,4\n")
        uploaded.name = "validation.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), \
                patch("streamlit.download_button", return_value=False), \
                patch("analysis.analyze", wraps=analyze) as calculate:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            for block, threshold, messages in [
                ("", "", ["Moving average", "Noise threshold"]),
                ("-1", "0.02", ["Moving average"]),
                ("102", "0.02", ["Moving average"]),
                ("2.5", "0.02", ["Moving average"]),
                ("3", "-0.1", ["Noise threshold"]),
                ("3", "nan", ["Noise threshold"]),
                ("3", "inf", ["Noise threshold"]),
                ("3", "1e", ["Noise threshold"]),
            ]:
                with self.subTest(block=block, threshold=threshold):
                    app.text_input(key="analysis_block_size_text").set_value(block)
                    app.text_input(key="analysis_threshold_text").set_value(threshold).run()
                    self.assertFalse(app.error)
                    app.text_input(key="analysis_block_size_text").set_value(block)
                    app.text_input(key="analysis_threshold_text").set_value(threshold)
                    next(button for button in app.button if button.label == "Analyze").click().run()
                    self.assertFalse(app.exception)
                    self.assertEqual(len(app.error), len(messages))
                    for error, message in zip(app.error, messages):
                        self.assertIn(message, error.value)
                    self.assertEqual(calculate.call_count, 0)
                    self.assertFalse(app.metric)
            app.text_input(key="analysis_block_size_text").set_value("0")
            app.text_input(key="analysis_threshold_text").set_value("0e0")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(calculate.call_count, 1)
            self.assertEqual(app.session_state["analysis_run"][3]["block_size"], 0)
            self.assertEqual(app.session_state["analysis_run"][3]["threshold"], 0)

    def test_reordered_upload_summary_experiment_and_downloads(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        rows = [["Instrument export", None, None, None],
                ['Loss Modulus G"', "Time", "Temperature", "Storage Modulus G'"],
                ["Pa", "s", "C", "Pa"]]
        rows.extend([[0.1, index, index,
                      10 ** (0.3 * (index // 3) + 0.15 * math.sin(1.2 * (index // 3)))] for index in range(54)])
        upload = BytesIO(pd.DataFrame(rows).to_csv(index=False, header=False).encode())
        upload.name = "reordered.csv"
        with patch("streamlit.file_uploader", return_value=[upload]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertEqual(next(control for control in app.number_input if control.label == "First data row").value, 4)
            self.assertTrue(any(header.value == "Step 3. Analysis settings" for header in app.subheader))
            input_summary_frame = next(frame.value for frame in app.dataframe if "Measurements" in frame.value.columns)
            self.assertEqual(input_summary_frame["Measurements"].iloc[0], 54)
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["analysis_run"][3]["inputs"][0]["columns_1_based"], [3, 4, 1])
            original_settings = app.session_state["analysis_run"][3].copy()
            self.assertNotIn("Run robustness check", [button.label for button in app.button])
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertNotIn("Parameter robustness", workbook.sheetnames)
            workbook.close()
            direct_download = [call for call in downloads.call_args_list if call.args[0] == "Download figure"][-1]
            self.assertTrue(callable(direct_download.args[1]))
            with patch.dict(direct_download.args[1].__globals__, {"figure_image": lambda figure, image_format: b"png"}):
                self.assertEqual(direct_download.args[1](), b"png")
            self.assertNotIn("Prepare figure", [button.label for button in app.button])
            self.assertNotIn("Optimise", [button.label for button in app.button])
            self.assertNotIn("Apply selected parameters", [button.label for button in app.button])
            self.assertNotIn("Parameter combination", [control.label for control in app.selectbox])
            self.assertFalse(any("Agreement tolerance" in control.label or "neighbour agreement" in control.label for control in app.number_input))
            self.assertEqual(app.session_state["analysis_run"][3], original_settings)

    def test_headerless_and_incompatible_units_before_analysis(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        for content, expected_row, disabled in [("25,1,2\n26,2,3\n27,3,4\n", 1, False),
                                                ("Temperature,Storage (kPa),Loss (kPa)\n25,1,2\n26,2,3\n", 2, True)]:
            uploaded = BytesIO(content.encode())
            uploaded.name = "data.csv"
            with patch("streamlit.file_uploader", return_value=[uploaded]):
                app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
                self.assertFalse(app.exception)
                self.assertEqual(next(control for control in app.number_input if control.label == "First data row").value, expected_row)
                self.assertEqual(next(button for button in app.button if button.label == "Analyze").disabled, disabled)


class InterfaceWorkflow(unittest.TestCase):
    def test_routine_yellow_messages_hidden_but_exported(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        raw = pd.DataFrame({"A": range(55),
                            "B": [10 ** (0.3 * (i // 3) + 0.15 * math.sin(1.2 * (i // 3)))
                                  for i in range(55)], "C": [0.1] * 55})
        raw.loc[1, "B"] *= -1
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "warnings.csv"
        expected = analyze(raw.rename(columns={"A": "temperature", "B": "storage", "C": "loss"}))
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertFalse(app.warning)
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.warning)
            _, records, _, configuration = app.session_state["analysis_run"]
            result = next(iter(records.values()))
            self.assertTrue(configuration["inputs"][0]["import_notes"])
            self.assertTrue(result["warnings"])
            self.assertEqual(result["results"], expected["results"])
            pd.testing.assert_frame_equal(result["blocks"], expected["blocks"])
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertEqual(workbook["Summary"]["E2"].value, " | ".join(expected["warnings"]))
            workbook.close()

    def test_hide_points_and_zero_averaging_controls(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        from figures import derivative_plot_data, build_figure

        raw = pd.DataFrame({"temperature": range(54),
                            "storage": [10 ** (0.3 * (index // 3) + 0.15 * math.sin(1.2 * (index // 3)))
                                        for index in range(54)], "loss": [0.1] * 54})
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "hide_points.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            next(button for button in app.button if button.label == "Analyze").click().run()
            original_temperature = app.metric[0].value
            next(control for control in app.number_input if control.label == "Hide last derivative points").set_value(2).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, original_temperature)
            result = next(iter(app.session_state["analysis_run"][1].values()))
            axes = next(iter(app.session_state["figure_axis_settings"].values()))
            self.assertEqual(axes["derivative_exclude_last"], 2)
            figure = build_figure(result, axis_settings=axes)
            curve = next(trace for trace in figure.data if trace.name == "Log second derivative")
            self.assertEqual(len(curve.x), len(derivative_plot_data(result, 2)))
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertAlmostEqual(workbook.worksheets[1]["D4"].value, result["blocks"].log_second_derivative.iloc[2])
            workbook.close()
            app.text_input(key="analysis_block_size_text").set_value("0")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            result = next(iter(app.session_state["analysis_run"][1].values()))
            self.assertEqual(result["settings"]["block_size"], 0)
            self.assertEqual(len(result["blocks"]), len(raw))
            self.assertEqual(app.session_state["analysis_run"][3]["averaging"], "none")

    def test_all_initial_measurements_retained_and_derivative_bounds(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        from figures import build_figure

        raw = pd.DataFrame({"temperature": range(54),
                            "storage": [10 ** (0.3 * (index // 3) + 0.15 * math.sin(1.2 * (index // 3)))
                                        for index in range(54)], "loss": [0.1] * 54})
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "trim_test.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertNotIn("Skip initial measurements", [control.label for control in app.number_input])
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            result = next(iter(app.session_state["analysis_run"][1].values()))
            self.assertEqual(len(result["raw"]), 54)
            self.assertEqual(result["raw"].temperature.iloc[0], 0)
            expected = analyze(raw)
            pd.testing.assert_frame_equal(result["blocks"], expected["blocks"])
            self.assertEqual(result["preprocessing"]["effective_first_data_row"], 2)
            next(control for control in app.number_input if control.label == "Minimum derivative").set_value(-0.1).run()
            next(control for control in app.number_input if control.label == "Maximum derivative").set_value(0.2).run()
            self.assertFalse(app.exception)
            axes = next(iter(app.session_state["figure_axis_settings"].values()))
            figure = build_figure(result, axis_settings=axes)
            self.assertEqual(figure.layout.yaxis2.range, (-0.1, 0.2))
            self.assertEqual(figure.layout.xaxis.range, figure.layout.xaxis2.range)
            with self.assertRaises(ValueError):
                build_figure(result, axis_settings={"derivative_min": 1, "derivative_max": -1})
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertEqual(workbook.worksheets[1]["A2"].value, result["blocks"].temperature.iloc[0])
            workbook.close()

    def test_automatic_marker_ignores_old_manual_selection_and_math_labels(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        raw = pd.DataFrame({"temperature": range(54),
                            "storage": [10 ** (0.3 * (index // 3) + 0.15 * math.sin(1.2 * (index // 3)))
                                        for index in range(54)],
                            "loss": [0.1] * 54})
        candidates = log_inflection_candidates(analyze(raw))
        self.assertGreater(len(candidates), 1)
        uploaded = BytesIO(raw.to_csv(index=False).encode())
        uploaded.name = "multiple_crossings.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            next(button for button in app.button if button.label == "Analyze").click().run()
            fingerprint, records, _, _ = app.session_state["analysis_run"]
            label = next(iter(records))
            app.session_state["figure_marker_positions"] = {f"marker_{fingerprint}_{label}": candidates[-1]}
            app.run()
            self.assertFalse(app.exception)
            self.assertNotIn("Adjust red circle", [control.label for control in app.toggle])
            self.assertFalse(any("Red circle temperature" in control.label for control in app.selectbox))
            self.assertEqual(app.metric[0].value, f"{candidates[0]:.1f} \u00b0C")
            # Single dataset: no comparison summary table, only import preview and input summary.
            self.assertEqual(len(app.dataframe), 2)
            self.assertFalse(app.tabs)
            self.assertFalse(app.latex)
            self.assertIn("Customise upper plot (appearance only)", [item.label for item in app.expander])
            self.assertIn("Customise lower plot (appearance only)", [item.label for item in app.expander])
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertEqual(workbook["Summary"]["B2"].value, candidates[0])
            self.assertEqual(workbook.worksheets[1]["E2"].value, candidates[0])
            workbook.close()

    def test_reference_batch_and_parameter_change(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        uploaded = BytesIO(REFERENCE.read_bytes())
        uploaded.name = REFERENCE.name
        with patch("streamlit.file_uploader", return_value=[uploaded]):
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertFalse(app.exception)
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "65.0 \u00b0C")
            self.assertEqual(len(app.metric), 2)
            self.assertEqual(app.metric[1].label, "Moduli crossover temperature")
            self.assertEqual(len(app.session_state["analysis_run"][1]), 9)
            self.assertFalse(app.radio)
            self.assertNotIn("Limit row range", [control.label for control in app.checkbox])
            self.assertIn("First data row", [control.label for control in app.number_input])
            self.assertNotIn("Reported metric", [control.label for control in app.selectbox])
            original_run = app.session_state["analysis_run"]
            app.text_input(key="analysis_block_size_text").set_value("5").run()
            self.assertEqual(app.session_state["analysis_run"][0], original_run[0])
            self.assertEqual(next(iter(app.session_state["analysis_run"][1].values()))["settings"]["block_size"], 3)
            app.text_input(key="analysis_block_size_text").set_value("5")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(next(iter(app.session_state["analysis_run"][1].values()))["settings"]["block_size"], 5)

    def test_raw_csv_upload(self):
        from io import BytesIO
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        book = load_workbook(REFERENCE, data_only=True)
        rows = [row for row in book.worksheets[0].iter_rows(min_row=5, max_col=3, values_only=True)
                if isinstance(row[0], (int, float))]
        book.close()
        frame = pd.DataFrame(rows, columns=["Temperature", "Storage", "Loss"])
        uploaded = BytesIO(frame.to_csv(index=False).encode())
        uploaded.name = "raw_reference.csv"
        with patch("streamlit.file_uploader", return_value=[uploaded]), patch("streamlit.download_button", return_value=False) as downloads:
            app = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=45).run()
            self.assertFalse(app.exception)
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "65.0 \u00b0C")
            self.assertFalse(app.tabs)
            records = app.session_state["analysis_run"][1]
            self.assertEqual(len(records), 1)
            self.assertEqual(len(next(iter(records.values()))["raw"]), 21)
            self.assertNotIn("Adjust red circle", [control.label for control in app.toggle])
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "65.0 \u00b0C")
            # Single dataset: the comparison summary table is not shown.
            self.assertFalse(any("Apparent gelation temperature (\u00b0C)" in table.value.columns
                                 for table in app.dataframe))
            exported = [call.args[1] for call in downloads.call_args_list if call.args[0] == "Download Excel workbook"][-1]
            workbook = load_workbook(BytesIO(exported), data_only=True)
            self.assertEqual(workbook["Summary"]["B2"].value, 65)
            self.assertEqual(workbook.worksheets[1]["E2"].value, 65)
            workbook.close()
            self.assertNotIn("Download calculations", [call.args[0] for call in downloads.call_args_list])
            next(control for control in app.number_input if control.label == "Minimum temperature (\u00b0C)").set_value(20.0).run()
            next(control for control in app.number_input if control.label == "Maximum temperature (\u00b0C)").set_value(100.0).run()
            self.assertFalse(app.exception)
            axes = next(iter(app.session_state["figure_axis_settings"].values()))
            self.assertEqual((axes["temperature_min"], axes["temperature_max"]), (20, 100))
            self.assertEqual(app.metric[0].value, "65.0 \u00b0C")
            original_run = app.session_state["analysis_run"]
            app.text_input(key="analysis_threshold_text").set_value("0.5").run()
            self.assertEqual(app.session_state["analysis_run"][0], original_run[0])
            self.assertEqual(app.metric[0].value, "65.0 \u00b0C")
            app.text_input(key="analysis_threshold_text").set_value("0.5")
            next(button for button in app.button if button.label == "Analyze").click().run()
            self.assertFalse(app.exception)
            current = next(iter(app.session_state["analysis_run"][1].values()))
            self.assertIsNone(current["log_threshold_temperature"])
            self.assertEqual(app.metric[0].value, "Not found")


if __name__ == "__main__":
    unittest.main()
