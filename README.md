## Gel Xplorer Overview

Gel Xplorer is a local, browser-based application that was developed to streamline and estimate the **apparent gelation temperature** from rheology temperature-ramp data — temperature (°C), storage modulus (G') and loss modulus (G") beyond the conventional crossover G'/G". As experimental studies increasingly generate large volumes of rheological data, manual analysis can become laborious and may introduce inconsistencies between datasets. To address this, Gel Xplorer offers a practical approach for high-throughput screening and comparative assessment of rheological behaviour across experiments.

The main program file is `app.py`. On Windows, start the application by double-clicking `Launch.cmd`. The app opens in your web browser and processes files on your computer; it does not send them to an external analysis service.

> This estimate is intended to help identify apparent gelation temperature across different rheological responses, including data with no clear crossover or a broad, noisy one. It should not be treated as a definitive measurement of the material's physical gel point.

## Start the app

1. Install Python 3.12 and ensure that the Python Launcher for Windows (`py`) is installed.
2. Double-click `Launch.cmd` to start Gel Xplorer.
3. On first launch, the app creates its environment and installs the required packages. An internet connection is needed for this initial setup.
4. Once the browser opens, keep the command prompt window open while using the application. Closing this window will stop Gel Xplorer.

Gel Xplorer is developed and tested with Python 3.12. Newer Python versions may be compatible, provided that all dependencies listed in `requirements.txt` support the selected version. However, compatibility with newer Python releases is not guaranteed until tested.

## Use the hosted version
If you prefer not to install Python or run the application locally, you can access the hosted version directly through Streamlit Community Cloud:

https://gelsit.streamlit.app/

The hosted version requires no installation and can be accessed from any modern web browser.

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

## Software development

Gel Xplorer was developed under the supervision of Arif Z Nelson (Associate Professor - Singapore Institute of Technology), who contributed to the conceptualization of the analytical framework and provided scientific guidance throughout the project. Wing Shan Ko designed and implemented the software workflow, including the algorithm development, validation of the gelation temperature determination methodology against the experimental datasets, software testing, user interface development, and documentation.

## Acknowledgements
The development of Gel Xplorer was supported by:

- National Research Foundation (NRF), Prime Minister's Office, Singapore, under its Campus for Research Excellence and Technological Enterprise (CREATE) programme (Proteins4Singapore)
- Agency for Science, Technology and Research (A*STAR) through the RIE2020 Singapore Food Story R&D Programme Industry Alignment Fund Pre-Positioning grants (A21H7a0131 and H21H8a0005)
- A*STAR RIE 2025 New Zealand-Singapore Biotech in Future Foods Research Programme (R25IBIR003)
- National Research Foundation, Singapore, and the Singapore Food Agency (SFA) under the Singapore Food Story R&D 2.0 Programme Second Future Foods Main Grant Call (NRF-SFSRND2FF2-0004)

The authors also acknowledge the Bezos Earth Fund for supporting the Bezos Centre for Sustainable Protein at the National University of Singapore (NUS), and the Good Food Institute.

## Associated Publication

If you use Gel Xplorer in your research, publications, or academic studies, please cite the following work:

Ko, W. S., Chin, T. G. J., Tang, K. Y., Chai, C. H. T., Jiang, Y., Ye, E., Du, J., & Nelson, A. Z. (2026). Practical rheology: Apparent gelation temperature metrics for enabling high-throughput screening of plant-based protein functionality [Manuscript under review].

Note: This citation will be updated upon publication with the final journal information and DOI.

## Bug reports and feedback

For bug reporting, feature requests, or general feedback regarding Gel Xplorer, please reach out to Arif Z Nelson at [arif.nelson@singaporetech.edu.sg](arif.nelson@singaporetech.edu.sg).

## License

Distributed under the MIT License. See [`LICENSE`](./LICENSE) for more information.
