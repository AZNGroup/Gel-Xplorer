# GelSIT
## Overview

GelSIT is a local, browser-based application that estimates the **apparent gelation temperature** from rheology temperature-ramp data — temperature (°C), storage modulus (G') and loss modulus (G") beyond the conventional crossover G'/G". It was developed by Wing Shan Ko at the Singapore Institute of Technology.

The main program file is `app.py`. On Windows, start the application by double-clicking `Launch.cmd`. The app opens in your web browser and processes files on your computer; it does not send them to an external analysis service.

> This estimate is intended to help identify apparent gelation temperature across different rheological responses, including data with no clear crossover or a broad, noisy one. It should not be treated as a definitive measurement of the material's physical gel point.

## Start the app

1. Install Python 3.12 or newer, including the Python Launcher for Windows (`py`).
2. Double-click `Launch.cmd`.
3. On first launch, the app creates its environment and installs the required packages. An internet connection is needed for this initial setup.
4. When the browser opens, keep the console window open while you use the app.

The launcher uses the newest installed Python 3 version. Newer Python releases can be used when the packages listed in `requirements.txt` support them; compatibility with future releases is not guaranteed until tested.

The app should open automatically in your browser. If it does not, use the address shown in the console window. For the currently running instance, the address is [http://127.0.0.1:8501](http://127.0.0.1:8501). The port may differ when you start the app again.

## Prepare your data

Upload an Excel workbook (`.xlsx`) or a UTF-8 CSV file. Each worksheet or CSV should contain temperature ramp with:

- Temperature in °C
- Storage modulus, G', in Pa
- Loss modulus, G", in Pa

Temperature should generally rise through the data. Small measurement fluctuations are allowed with a warning, but a larger drop is rejected because the analysis expects one heating ramp. G' and G" may rise or fall. The app does not sort rows or convert units. Negative modulus values receive special handling and may exclude data from the calculation. CSV files may use commas, semicolons, or tabs as delimiters.

## Analyze your data

1. Upload one or more files and select the worksheet or worksheets to analyze.
2. Check the preview. Confirm the first data row and the columns for temperature, G', and G". The app suggests these automatically, but you can change them for each worksheet.
3. Review the input summary and correct any row or column selections that do not match your data.
4. Choose the analysis settings. The defaults are a three-point moving average and a noise threshold of `0.02`, but the appropriate values depend on the datapoint density of your temperature ramp — adjust them to suit your measurement. Set **Moving average** to `0` to disable averaging. The settings apply to all datasets; with several datasets, open **Per-dataset adjustments** to give individual datasets their own values. The app starts looking for gelation once the first derivative of log10(G*) reaches the noise threshold, then checks whether its second derivative changes from positive to negative. A threshold of `0` means the first derivative must be zero or higher; it does not turn off this step.
5. Click **Analyze**. The app displays the apparent gelation temperature and figure for each successful dataset.

## Understand and download results

- **Apparent gelation temperature:** The app reports the first qualifying positive-to-negative crossing in the second derivative of log10(G*), after the noise threshold is met. If no crossing qualifies, the result is **Not found**.
- **Moduli crossover temperature:** If present, this is shown separately and is not used to calculate the apparent gelation temperature.
- **Figure:** Shows the moduli and second derivative of log10(G*). Figure customisation changes the appearance only; it does not change the reported result.
- **Excel workbook:** Download the calculated data and summary for your datasets.
- **Figure file:** Download the figure as PNG, SVG, PDF, or HTML. PNG, SVG, and PDF export require Chrome or Edge to be installed.

## If something looks wrong

- Check the preview and confirm the selected data row and all three columns.
- Confirm the input uses °C and Pa. Convert other units before uploading.
- Make sure the temperature values do not decrease as you move down the heating ramp.
- **Not found** means no crossing met the analysis criteria; it does not mean the temperature is zero.
- If the app does not start on first launch, check the console for an error and confirm that Python 3.12 or newer and an internet connection are available.

## Bug report

For bug reporting, please reach out to [arif.nelson@singaporetech.edu.sg](arif.nelson@singaporetech.edu.sg).

## Reference

If you use this tool in your research or academic studies, please cite our work using the temporary format below. This work is currently under revision, and the citation will be updated with the finalised title and journal details upon publication: 

Ko, W. S., Chin, T. G. J., Tang, K. Y., Chai, C. H. T., Jiang, Y., Ye, E., Du, J., & Nelson, A. Z. (2026). Practical rheology: Apparent gelation temperature metrics for enabling high-throughput screening of plant-based protein functionality [Manuscript submitted for publication].

## License

Distributed under the MIT License. See [`LICENSE`](./LICENSE) for more information.
