"""
Builds the CSVs in data/processed/ from the raw NSF and IPEDS files in data/raw/.

    python pipeline/build_data.py

Expects herdYYYY.csv, HDYYYY.csv, CYYYY_A.csv, EFYYYYD.csv and DRVGRYYYY.csv.
Files are matched by name, so dropping in a new year just works. For HD, EF and
DRVGR only the newest year is used; for completions a revised _RV file wins.

Notes:
- FY = the year in the file name. HERD 2024 is the FY ending in 2024, and
  C2024_A is awards from July 2023 to June 2024, so they line up.
- Dollars stay in thousands like HERD reports them.
- Research doctorates = award level 17, CIP 99 (all fields), first major.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

# 2025 Carnegie R1 cutoffs
R1_RD_THOUSANDS = 50_000   # $50M in annual R&D expenditures
R1_DOCTORATES = 70         # 70 research doctorates per year

CARNEGIE_RESEARCH = {1: "R1", 2: "R2", 3: "Research College/University"}
CONTROL = {1: "Public", 2: "Private nonprofit", 3: "Private for-profit"}
LEVEL = {1: "4-year", 2: "2-year", 3: "Less than 2-year"}
HERD_SOURCES = {
    "01.a": "federal",
    "01.b": "state_local",
    "01.c": "business",
    "01.d": "nonprofit",
    "01.e": "institution",
    "01.f": "other",
    "01.g": "total",
}


# Helpers
def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.replace("﻿", "").replace("ï»¿", "").strip().upper() for c in df.columns]
    return df


def _read_ipeds(path: Path, **kw) -> pd.DataFrame:
    return _clean_cols(pd.read_csv(path, encoding="latin-1", low_memory=False, **kw))


def _files(pattern: str) -> dict[int, Path]:
    # {year: path}; an _RV (revised) file replaces the original
    found: dict[int, Path] = {}
    rx = re.compile(pattern, re.IGNORECASE)
    for p in sorted(RAW.iterdir()):
        m = rx.fullmatch(p.name)
        if not m:
            continue
        year = int(m.group(1))
        if year not in found or "_rv" in p.name.lower():
            found[year] = p
    return found


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.strip().replace({".": None, "": None}), errors="coerce")


# Builders
def build_directory() -> tuple[pd.DataFrame, int]:
    hd_files = _files(r"hd(\d{4})\.csv")
    if not hd_files:
        raise SystemExit("No IPEDS directory file (HDYYYY.csv) found in data/raw/")
    year = max(hd_files)
    hd = _read_ipeds(hd_files[year])
    keep = hd[(hd["HBCU"] == 1) | (hd["CARNEGIERSCH"].isin([1, 2]))].copy()
    out = pd.DataFrame({
        "unitid": keep["UNITID"].astype(int),
        "name": keep["INSTNM"].str.strip(),
        "city": keep["CITY"].str.strip(),
        "state": keep["STABBR"].str.strip(),
        "hbcu": keep["HBCU"].eq(1),
        "control": keep["CONTROL"].map(CONTROL).fillna("Other"),
        "level": keep["ICLEVEL"].map(LEVEL).fillna("Other"),
        "carnegie_research": keep["CARNEGIERSCH"].map(CARNEGIE_RESEARCH).fillna("Not designated"),
        "medical_school": keep["MEDICAL"].eq(1),
        "land_grant": keep["LANDGRNT"].eq(1),
        "website": keep["WEBADDR"].fillna("").str.strip(),
    })
    print(f"  directory: HD{year} -> {out.hbcu.sum()} HBCUs, "
          f"{(out.carnegie_research == 'R1').sum()} R1s, {(out.carnegie_research == 'R2').sum()} R2s")
    return out, year


def build_rd(unitids: set[int]) -> pd.DataFrame:
    frames = []
    for year, path in sorted(_files(r"herd(\d{4})\.csv").items()):
        h = pd.read_csv(path, low_memory=False,
                        usecols=["ipeds_unitid", "questionnaire_no", "data"])
        h = h[h["questionnaire_no"].isin(HERD_SOURCES) & h["ipeds_unitid"].isin(unitids)]
        wide = (h.assign(src=h["questionnaire_no"].map(HERD_SOURCES))
                  .pivot_table(index="ipeds_unitid", columns="src", values="data", aggfunc="sum")
                  .reset_index().rename(columns={"ipeds_unitid": "unitid"}))
        wide["fy"] = year
        frames.append(wide)
        print(f"  HERD FY{year}: {len(wide)} matched institutions")
    rd = pd.concat(frames, ignore_index=True)
    cols = ["unitid", "fy"] + list(HERD_SOURCES.values())
    rd = rd.reindex(columns=cols)
    rd["unitid"] = rd["unitid"].astype(int)
    return rd.sort_values(["unitid", "fy"])


def build_doctorates(unitids: set[int]) -> pd.DataFrame:
    frames = []
    for year, path in sorted(_files(r"c(\d{4})_a(?:_rv)?\.csv").items()):
        c = _read_ipeds(path, usecols=lambda x: x.replace("ï»¿", "").strip().upper()
                        in {"UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL", "CTOTALT"})
        c = c[(c["AWLEVEL"] == 17) & (c["MAJORNUM"] == 1) & (_num(c["CIPCODE"]) == 99)
              & c["UNITID"].isin(unitids)]
        frames.append(pd.DataFrame({"unitid": c["UNITID"].astype(int), "fy": year,
                                    "research_doctorates": _num(c["CTOTALT"])}))
        print(f"  completions FY{year} ({path.name}): {len(c)} institutions award research doctorates")
    doc = pd.concat(frames, ignore_index=True)
    # An institution with no level-17 row awarded zero research doctorates that year.
    years = sorted(doc["fy"].unique())
    grid = pd.MultiIndex.from_product([sorted(unitids), years], names=["unitid", "fy"]).to_frame(index=False)
    return grid.merge(doc, how="left").fillna({"research_doctorates": 0})


def build_outcomes(unitids: set[int]) -> pd.DataFrame:
    ef_files, gr_files = _files(r"ef(\d{4})d\.csv"), _files(r"drvgr(\d{4})\.csv")
    out = pd.DataFrame({"unitid": sorted(unitids)})
    if ef_files:
        y = max(ef_files)
        ef = _read_ipeds(ef_files[y])
        out = out.merge(pd.DataFrame({"unitid": ef["UNITID"], "retention_rate": _num(ef["RET_PCF"]),
                                      "student_faculty_ratio": _num(ef["STUFACR"])}), how="left")
        out["retention_year"] = y
        print(f"  retention: EF{y}D")
    if gr_files:
        y = max(gr_files)
        gr = _read_ipeds(gr_files[y])
        out = out.merge(pd.DataFrame({"unitid": gr["UNITID"], "grad_rate_6yr": _num(gr["GBA6RTT"]),
                                      "grad_rate_pell": _num(gr["PGBA6RT"]),
                                      # all degree/certificate seekers, within 150% of normal time;
                                      # the meaningful completion rate for 2-year colleges
                                      "grad_rate_150": _num(gr["GRRTTOT"]),
                                      "transfer_rate": _num(gr["TRRTTOT"])}), how="left")
        out["grad_rate_year"] = y
        print(f"  graduation rates: DRVGR{y}")
    return out


def build_metrics(directory, rd, doc, outcomes) -> pd.DataFrame:
    latest_fy = int(min(rd["fy"].max(), doc["fy"].max()))
    window = [latest_fy - 2, latest_fy - 1, latest_fy]

    def per_inst(df, col):
        w = df[df["fy"].isin(window)]
        return pd.DataFrame({
            f"{col}_latest": df[df["fy"] == latest_fy].set_index("unitid")[col],
            f"{col}_3yr": w.groupby("unitid")[col].mean(),
            f"{col}_first": df[df["fy"] == window[0]].set_index("unitid")[col],
        })

    m = directory.set_index("unitid")
    m = m.join(per_inst(rd, "total")).join(per_inst(doc, "research_doctorates"))
    fed = rd[rd["fy"] == latest_fy].set_index("unitid")
    m["federal_share"] = fed["federal"] / fed["total"]
    m["institution_share"] = fed["institution"] / fed["total"]
    m["rd_growth_2yr"] = m["total_latest"] / m["total_first"] - 1
    m["pct_of_rd_threshold"] = m["total_3yr"] / R1_RD_THOUSANDS
    m["pct_of_doc_threshold"] = m["research_doctorates_3yr"] / R1_DOCTORATES
    m["meets_rd"] = m["total_3yr"] >= R1_RD_THOUSANDS
    m["meets_doc"] = m["research_doctorates_3yr"] >= R1_DOCTORATES
    # How far from R1: the weaker of the two measures, as a share of its threshold.
    m["r1_readiness"] = m[["pct_of_rd_threshold", "pct_of_doc_threshold"]].min(axis=1)
    m["in_herd"] = m["total_latest"].notna()
    m = m.join(outcomes.set_index("unitid"))
    m["latest_fy"] = latest_fy
    m = m.drop(columns=["total_first", "research_doctorates_first"])
    return m.reset_index()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Building tables from", RAW)
    directory, _ = build_directory()
    ids = set(directory["unitid"])
    rd = build_rd(ids)
    doc = build_doctorates(ids)
    outcomes = build_outcomes(ids)
    metrics = build_metrics(directory, rd, doc, outcomes)

    rd.to_csv(OUT / "rd_by_year.csv", index=False)
    doc.to_csv(OUT / "doctorates_by_year.csv", index=False)
    metrics.to_csv(OUT / "institutions.csv", index=False)
    print(f"Wrote {len(metrics)} institutions, FY{rd.fy.min()}-FY{rd.fy.max()}, to {OUT}")


if __name__ == "__main__":
    main()
