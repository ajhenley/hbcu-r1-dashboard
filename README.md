# HBCU & R1 Benchmarking Dashboard

How close is every HBCU to R1 research status, and how do the 102 HBCUs compare on research, doctoral output and student outcomes?

This dashboard is built entirely on public federal data: the NSF HERD Survey and U.S. Department of Education IPEDS. It has four views:

- **R1 tracker.** Every HBCU plotted against the two R1 thresholds ($50M+ in annual R&D, 70+ research doctorates a year) on a 3-year average, with a "closest to R1" table that shows the remaining gap for each school.
- **HBCU benchmarks.** Ranked comparisons on seven measures: R&D, R&D growth, federal share, research doctorates, retention, and 6-year graduation rates (all students and Pell recipients). Also a research-growth trend against the HBCU field.
- **Scorecard.** For any HBCU: its value, the HBCU median, its rank and percentile on every measure, where its research money comes from, and its doctoral output by year.
- **Data & methods.** Sources, definitions and caveats.

Built by Alton J. Henley.

## Analysis notebook

`notebooks/hbcu_r1_analysis.ipynb` walks through the same analysis step by step:

1. Loads and cleans the raw federal files.
2. Validates the results against ACE's published figures for Howard.
3. Works through the findings: who meets R1, research growth, funding mix, and research scale vs. graduation rates.
4. Ends with a scorecard function you can run for any HBCU.

To run it, you need the raw files in `data/raw/`:

```bash
pip install -r requirements-notebook.txt
jupyter lab notebooks/hbcu_r1_analysis.ipynb
```

The saved copy includes its outputs, so it can be read without running anything. Charts are interactive in Jupyter. To also save static images that display on GitHub, run with `PLOTLY_RENDERER="notebook_connected+png"`.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The processed data in `data/processed/` is included, so the app runs immediately.

## Deploy

**Streamlit Community Cloud (free, easiest).** Push this folder to a GitHub repo, then go to share.streamlit.io and choose New app. Pick the repo and set `app.py` as the entry point.

**Heroku**, same setup as your other apps:

```bash
heroku create hbcu-r1-dashboard
git push heroku main
```

The `Procfile` and `.python-version` are already set up.

## Refresh the data

1. Download the newer files into `data/raw/`:
   - NSF HERD public-use files (`herdYYYY.csv`), from ncses.nsf.gov/explore-data/microdata/higher-education-research-development
   - IPEDS complete data files (`HDYYYY.csv`, `CYYYY_A.csv`, `EFYYYYD.csv`, `DRVGRYYYY.csv`), from nces.ed.gov/ipeds/datacenter/DataFiles.aspx
2. Run `python pipeline/build_data.py`.

The pipeline picks up years by file name, prefers revised (`_RV`) IPEDS files, and uses the three most recent fiscal years that both sources cover. Raw files are git-ignored because they're large.

## Method notes

- **Research doctorates** = IPEDS award level 17 (doctor's degree, research/scholarship), all fields, first major.
- **R&D** = HERD total R&D expenditures (question 1, row g), in current dollars.
- **Fiscal years line up one to one:** HERD FY2024 matches IPEDS completions 2024 (awards from July 2023 to June 2024).
- **Validation:** the pipeline reproduces the figures ACE reported for Howard's FY2023 R1 evaluation, about $85M in R&D and 96 research doctorates.
- **Status here is not the official designation.** Positions are computed on newer data than the 2025 Carnegie designations, which appear separately.
- **Small programs aren't in HERD's full survey.** HBCUs with under $1M in R&D answer HERD's short form, which isn't loaded, so they show no R&D figures.

## Design notes

Type is Public Sans, the typeface of the U.S. Web Design System, a fitting choice for a dashboard built on federal data. It is bundled in `static/fonts/` under the SIL Open Font License, so the app needs no external font service.

There are three colors: blue for the selected institution, orange for R1 and benchmark references, and warm gray for other HBCUs. The palette is checked for color-vision deficiency. Threshold lines are dashed and labeled, every chart has hover detail, and the scorecard includes a table view of its numbers.

## Project layout

```
app.py                     Streamlit app
notebooks/                 analysis notebook (hbcu_r1_analysis.ipynb)
pipeline/build_data.py     raw federal files -> tidy tables
data/processed/            institutions.csv, rd_by_year.csv, doctorates_by_year.csv
data/raw/                  put raw downloads here (git-ignored)
```
# hbcu-r1-dashboard
# hbcu-r1-dashboard
