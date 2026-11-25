# HBCU & R1 benchmarking dashboard
# streamlit run app.py   (data comes from pipeline/build_data.py)

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "processed"
R1_RD_M = 50.0  # $M
R1_DOC = 70

FOCUS = "#2a78d6"      # selected school
REFERENCE = "#eb6834"  # orange = R1 only (thresholds, R1 schools)
PEER = "#a9b0ba"
INK = "#1b2433"
INK_2 = "#4f5b6b"      # medians
GRID = "#e6eaef"
SURFACE = "#ffffff"
FONT = "Public Sans, system-ui, -apple-system, Segoe UI, sans-serif"
CHART_CONFIG = {"displayModeBar": False, "responsive": True}

st.set_page_config(page_title="HBCU & R1 Benchmarking", page_icon="📊", layout="wide")

st.markdown(f"<style>{(ROOT / 'static' / 'style.css').read_text()}</style>", unsafe_allow_html=True)


# Data
@st.cache_data
def load():
    inst = pd.read_csv(DATA / "institutions.csv")
    rd = pd.read_csv(DATA / "rd_by_year.csv")
    doc = pd.read_csv(DATA / "doctorates_by_year.csv")
    for c in ["total_latest", "total_3yr"]:
        inst[c.replace("total", "rd") + "_m"] = inst[c] / 1000
    money = ["federal", "state_local", "business", "nonprofit", "institution", "other", "total"]
    rd[money] = rd[money] / 1000
    return inst, rd, doc


inst, rd, doc = load()
hbcu = inst[inst["hbcu"]].copy()
r1 = inst[inst["carnegie_research"] == "R1"].copy()
LATEST = int(inst["latest_fy"].iloc[0])
WINDOW = f"FY{LATEST - 2}–FY{LATEST}"
RET_YEAR = int(inst["retention_year"].max())
GR_YEAR = int(inst["grad_rate_year"].max())
GR_COHORT = GR_YEAR - 6      # 6-yr bachelor's rates
GR_COHORT_2YR = GR_YEAR - 3  # 3-yr rates at 2-year schools


# level + research designation
def peer_group(r):
    if r.level != "4-year":
        return "2-year HBCUs"
    if r.carnegie_research in ("R1", "R2"):
        return "HBCU research universities (R1 and R2)"
    if r.carnegie_research == "Research College/University":
        return "HBCU research colleges and universities"
    return "other 4-year HBCUs"


hbcu["peer_group"] = hbcu.apply(peer_group, axis=1)


def cap(s):
    return s[:1].upper() + s[1:]


def fmt_m(x):
    if pd.isna(x):
        return "—"
    return f"${x:,.1f}M" if x < 1000 else f"${x / 1000:,.2f}B"


def fmt_pct(x):
    if pd.isna(x):
        return "—"
    # don't let 99.6% show as 100%
    return f"{x:.1%}" if 0.995 <= x < 1 else f"{x:.0%}"


def fmt_rate(x):
    return "—" if pd.isna(x) else f"{x:.0f}%"


def base_layout(fig, height=440, **kw):
    fig.update_layout(
        height=height, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK, size=13),
        margin=dict(l=10, r=20, t=30, b=10),
        hoverlabel=dict(bgcolor="white", font_color=INK, font_family=FONT, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font_color=INK_2), **kw)
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont_color=INK_2, title_font_color=INK_2)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont_color=INK_2, title_font_color=INK_2)
    return fig


def rank_of(series: pd.Series, value, higher_is_better=True):
    s = series.dropna()
    if pd.isna(value) or s.empty:
        return "—"
    r = (s > value).sum() + 1 if higher_is_better else (s < value).sum() + 1
    return f"{r} of {len(s)}"


def percentile(series: pd.Series, value, higher_is_better=True):
    # share of the other schools beaten, so #1 reads 100%
    s = series.dropna()
    if pd.isna(value) or len(s) < 2:
        return None
    beaten = (s < value).sum() if higher_is_better else (s > value).sum()
    return beaten / (len(s) - 1)


# label -> (column, higher is better, formatter)
RESEARCH = {
    "R&D expenditures (FY latest, $M)": ("rd_latest_m", True, fmt_m),
    "R&D growth over 2 years": ("rd_growth_2yr", True, lambda v: f"{v:+.0%}"),
    "Federal share of R&D": ("federal_share", True, fmt_pct),
    "Research doctorates (FY latest)": ("research_doctorates_latest", True, lambda v: f"{v:,.0f}"),
}
RETENTION = {"First-year retention rate (%)": ("retention_rate", True, fmt_rate)}
STAFFING = {"Students per faculty member": ("student_faculty_ratio", False, lambda v: f"{v:.0f} to 1")}
OUTCOMES_4YR = {**RETENTION,
                "6-year graduation rate, bachelor's (%)": ("grad_rate_6yr", True, fmt_rate),
                "6-year graduation rate, Pell recipients (%)": ("grad_rate_pell", True, fmt_rate),
                **STAFFING}
OUTCOMES_2YR = {**RETENTION,
                "Completion within 150% of normal time (%)": ("grad_rate_150", True, fmt_rate),
                # transferring out counts as a win at a 2-year school
                "Transfer-out rate (%)": ("transfer_rate", True, fmt_rate),
                **STAFFING}
METRICS = {**RESEARCH, **OUTCOMES_4YR, **OUTCOMES_2YR}


def metrics_for(r):
    outcomes = OUTCOMES_4YR if r.level == "4-year" else OUTCOMES_2YR
    return {**RESEARCH, **outcomes} if r.in_herd else outcomes


def label_of(m):
    return m.replace("FY latest", f"FY{LATEST}")


# Sidebar
with st.sidebar:
    st.markdown("<div class='brand'>HBCU & R1 Benchmarking</div>"
                f"<div class='brand-sub'>Federal data through FY{LATEST}</div>", unsafe_allow_html=True)
    names = hbcu.sort_values("name")["name"].tolist()
    # ?school= so links can point at a school
    wanted = st.query_params.get("school", "Howard University")
    default = names.index(wanted) if wanted in names else 0
    pick = st.selectbox("Choose an institution", names, index=default)
    st.query_params["school"] = pick
    me = hbcu[hbcu["name"] == pick].iloc[0]
    group_n = int((hbcu["peer_group"] == me.peer_group).sum())
    # needs a key, otherwise it resets when the label changes
    scope = st.radio("Compare with", ["peers", "all"], key="scope",
                     format_func=lambda k: (f"Peer group: {cap(me.peer_group)} ({group_n})" if k == "peers"
                                            else f"All HBCUs ({len(hbcu)})"))
    st.markdown(
        "<p class='side-note'>Peer groups pair schools of the same level (4-year or 2-year) and research "
        f"designation.</p><p class='side-note'>R1 status takes <b>$50M+</b> in annual R&D "
        f"and <b>70+</b> research doctorates a year. Research figures are 3-year averages for {WINDOW}.</p>"
        "<p class='side-note'>Sources: NSF Higher Education Research and Development Survey and "
        "U.S. Department of Education IPEDS.</p>"
        "<div class='credit'>Built by <b>Alton J. Henley</b></div>", unsafe_allow_html=True)

pool = hbcu[hbcu["peer_group"] == me.peer_group] if scope == "peers" else hbcu
POOL = me.peer_group if scope == "peers" else "all HBCUs"
MED_LABEL = "Peer median" if scope == "peers" else "HBCU median"
RESEARCH_COLS = {c for c, _, _ in RESEARCH.values()}


def compare_set(col):
    # non-HERD schools show up as 0 doctorates, so leave them out of research ranks
    return pool[pool["in_herd"]] if col in RESEARCH_COLS else pool


def section(title, text=None):
    st.markdown(f"<div class='sec'><h3>{title}</h3>" + (f"<p>{text}</p>" if text else "") + "</div>",
                unsafe_allow_html=True)


def meter(label, value_html, pct, note):
    pct = 0 if pd.isna(pct) else pct
    scale = max(1.5, min(pct, 2.0))
    width = min(pct / scale, 1) * 100
    tick = 100 / scale
    cls = "fill met" if pct >= 1 else "fill"
    return (f"<div><div class='meter-label'>{label}</div><div class='meter-value'>{value_html}</div>"
            f"<div class='track'><div class='{cls}' style='width:{width:.1f}%'></div>"
            f"<div class='tick' style='left:{tick:.1f}%'></div></div>"
            f"<div class='meter-note'>{note}</div></div>")


def rate_meter(label, col, hi=True):
    v, med = me[col], pool[col].median()
    width = 0 if pd.isna(v) else max(0, min(v, 100))
    tick = "" if pd.isna(med) else f"<div class='tick median' style='left:{med:.1f}%'></div>"
    note = ("No data reported" if pd.isna(v) else
            f"{MED_LABEL} {fmt_rate(med)} &nbsp;·&nbsp; rank {rank_of(pool[col], v, hi)}")
    return (f"<div><div class='meter-label'>{label}</div><div class='meter-value'>{fmt_rate(v)}</div>"
            f"<div class='track'><div class='fill' style='width:{width:.1f}%'></div>{tick}</div>"
            f"<div class='meter-note'>{note}</div></div>")


def fact(value, label):
    return f"<div class='fact'><div class='fact-v'>{value}</div><div class='fact-l'>{label}</div></div>"


def headline(r):
    if r.meets_rd and r.meets_doc:
        return f"{r['name']} clears both R1 research thresholds."
    if r.meets_rd:
        gap = R1_DOC - r.research_doctorates_3yr
        return f"{r['name']} clears the R&D threshold and is {gap:,.1f} doctorates a year short of R1."
    if r.meets_doc:
        gap = R1_RD_M - r.rd_3yr_m
        return f"{r['name']} clears the doctorate threshold and is {fmt_m(gap)} a year short on R&D."
    return (f"{r['name']} is at {r.pct_of_rd_threshold:.0%} of the R&D threshold and "
            f"{r.pct_of_doc_threshold:.0%} of the doctorate threshold.")


def headline_outcomes(r):
    parts = []
    if pd.notna(r.retention_rate):
        parts.append(f"keeps {r.retention_rate:.0f}% of its first-year students")
    if r.level == "4-year" and pd.notna(r.grad_rate_6yr):
        parts.append(f"graduates {r.grad_rate_6yr:.0f}% of bachelor's students within six years")
    elif r.level != "4-year" and pd.notna(r.grad_rate_150):
        parts.append(f"sees {r.grad_rate_150:.0f}% finish within 150% of normal time")
    if not parts:
        return f"{r['name']} has not reported retention or graduation rates for these years."
    return f"{r['name']} " + " and ".join(parts) + "."


kicker = (f"{me.city}, {me.state} &nbsp;|&nbsp; {me.control}, {me.level} &nbsp;|&nbsp; "
          f"Official 2025 designation: {me.carnegie_research}")
if me.in_herd:
    growth = ("" if pd.isna(me.rd_growth_2yr) else
              f"{'up' if me.rd_growth_2yr >= 0 else 'down'} {abs(me.rd_growth_2yr):.0%} since FY{LATEST - 2}")
    hero_body = f"""
  <h1>{headline(me)}</h1>
  <div class="hero-sub">Three-year averages for {WINDOW}, measured against the R1 thresholds. The orange mark on each bar is the threshold.</div>
  <div class="hero-grid">
    {meter("Research and development spending", fmt_m(me.rd_3yr_m) + "<small>a year</small>",
           me.pct_of_rd_threshold, f"{fmt_pct(me.pct_of_rd_threshold)} of the $50M threshold")}
    {meter("Research doctorates awarded", f"{me.research_doctorates_3yr:,.1f}<small>a year</small>",
           me.pct_of_doc_threshold, f"{fmt_pct(me.pct_of_doc_threshold)} of the 70-doctorate threshold")}
    <div class="facts">
      {fact(fmt_m(me.rd_latest_m), f"R&D in FY{LATEST}{', ' + growth if growth else ''}")}
      {fact(rank_of(compare_set("rd_latest_m")["rd_latest_m"], me.rd_latest_m), f"Research spending rank among {POOL}")}
      {fact(fmt_rate(me.retention_rate), f"First-year retention, fall {RET_YEAR}")}
    </div>
  </div>"""
else:
    four = me.level == "4-year"
    cohort = GR_COHORT if four else GR_COHORT_2YR
    second = (rate_meter("6-year graduation rate, bachelor's", "grad_rate_6yr") if four else
              rate_meter("Completion within 150% of normal time", "grad_rate_150"))
    extra = (fact(fmt_rate(me.grad_rate_pell), "6-year graduation rate, Pell recipients") if four else
             fact(fmt_rate(me.transfer_rate), "Transfer-out rate"))
    ratio = "—" if pd.isna(me.student_faculty_ratio) else f"{me.student_faculty_ratio:.0f} to 1"
    hero_body = f"""
  <h1>{headline_outcomes(me)}</h1>
  <div class="hero-sub">Compared with {f"all {len(pool)} HBCUs" if scope == "all" else f"the {len(pool)} schools in its peer group, {POOL}"}. The white mark on each bar is the median. Retention is for fall {RET_YEAR}; graduation rates follow students who entered in fall {cohort}.</div>
  <div class="hero-grid">
    {rate_meter("First-year retention", "retention_rate")}
    {second}
    <div class="facts">
      {extra}
      {fact(ratio, "Students per faculty member")}
      {fact("Under $1M", "Annual research spending, below NSF's full-survey range")}
    </div>
  </div>"""
st.markdown(f'<div class="hero"><div class="hero-kicker">{kicker}</div>{hero_body}</div>',
            unsafe_allow_html=True)

# non-research schools open on their scorecard
TAB_LABELS = {"r1": "R1 tracker", "bench": "HBCU benchmarks", "card": f"Scorecard: {pick}",
              "about": "Data & methods"}
order = ["r1", "bench", "card", "about"] if me.in_herd else ["card", "bench", "r1", "about"]
tabs = dict(zip(order, st.tabs([TAB_LABELS[k] for k in order])))
tab_r1, tab_bench, tab_card, tab_about = tabs["r1"], tabs["bench"], tabs["card"], tabs["about"]

# R1 tracker
with tab_r1:
    section("Where every HBCU stands", "Each dot is an HBCU, placed by its research spending and research "
            "doctorates. Schools above and to the right of both dashed lines meet the R1 thresholds.")
    show_r1 = st.toggle("Include R1 universities for context (log scale)", value=False)

    plot = hbcu[hbcu["in_herd"]].copy()
    fig = go.Figure()
    if show_r1:
        fig.add_trace(go.Scatter(
            x=r1["research_doctorates_3yr"].clip(lower=1), y=r1["rd_3yr_m"].clip(lower=0.1),
            mode="markers", name="R1 universities", text=r1["name"],
            marker=dict(size=8, color=REFERENCE, opacity=0.55, line=dict(color=SURFACE, width=1)),
            hovertemplate="<b>%{text}</b><br>R&D: $%{y:,.1f}M<br>Doctorates: %{x:,.0f}<extra>R1</extra>"))
    peers = plot[plot["unitid"] != me.unitid]
    fig.add_trace(go.Scatter(
        x=peers["research_doctorates_3yr"].clip(lower=1 if show_r1 else 0),
        y=peers["rd_3yr_m"].clip(lower=0.1), mode="markers", name="HBCUs", text=peers["name"],
        marker=dict(size=9, color=PEER, line=dict(color=SURFACE, width=2)),
        customdata=peers[["carnegie_research"]],
        hovertemplate="<b>%{text}</b><br>R&D: $%{y:,.1f}M<br>Doctorates: %{x:,.0f}"
                      "<br>%{customdata[0]}<extra></extra>"))
    lead = peers.nlargest(3, "r1_readiness")
    for _, r in lead.iterrows():
        fig.add_annotation(x=max(r.research_doctorates_3yr, 1) if show_r1 else r.research_doctorates_3yr,
                           y=r.rd_3yr_m, text=r["name"], showarrow=False, xanchor="right", xshift=-9,
                           font=dict(color=INK_2, size=11))
    if me.in_herd:
        fig.add_trace(go.Scatter(
            x=[max(me.research_doctorates_3yr, 1 if show_r1 else 0)], y=[me.rd_3yr_m],
            mode="markers+text", name=pick, text=[pick], textposition="top left",
            textfont=dict(color=INK, size=13),
            marker=dict(size=14, color=FOCUS, line=dict(color=SURFACE, width=2)),
            hovertemplate=f"<b>{pick}</b><br>R&D: $%{{y:,.1f}}M<br>Doctorates: %{{x:,.0f}}<extra></extra>"))
    fig.add_hline(y=R1_RD_M, line=dict(color=REFERENCE, dash="dash", width=1.5),
                  annotation_text="$50M R&D threshold", annotation_position="top left",
                  annotation_font_color=INK_2)
    fig.add_vline(x=R1_DOC, line=dict(color=REFERENCE, dash="dash", width=1.5),
                  annotation_text="70 doctorates", annotation_position="bottom right",
                  annotation_font_color=INK_2)
    base_layout(fig, height=520)
    fig.update_xaxes(title=f"Research doctorates per year ({WINDOW} average)",
                     type="log" if show_r1 else "linear")
    fig.update_yaxes(title=f"R&D expenditures, $ millions ({WINDOW} average)",
                     type="log" if show_r1 else "linear")
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)
    st.markdown(f"<p class='note'>{len(hbcu) - len(plot)} HBCUs report under $1M in R&D and are "
                "not plotted.</p>", unsafe_allow_html=True)

    section("Closest to R1", "Ranked by each school's weaker measure as a share of its threshold. "
            "The gaps show what is still needed each year, on the 3-year average.")
    near = plot.sort_values("r1_readiness", ascending=False).head(12)
    st.dataframe(pd.DataFrame({
        "Institution": near["name"],
        "Designation (2025)": near["carnegie_research"],
        "R&D 3-yr avg": near["rd_3yr_m"].map(fmt_m),
        "R&D gap": (R1_RD_M - near["rd_3yr_m"]).clip(lower=0).map(lambda v: "met" if v == 0 else fmt_m(v)),
        "Doctorates 3-yr avg": near["research_doctorates_3yr"].map(lambda v: f"{v:,.1f}"),
        "Doctorate gap": (R1_DOC - near["research_doctorates_3yr"]).clip(lower=0)
                          .map(lambda v: "met" if v == 0 else f"{v:,.1f}"),
        "Readiness": near["r1_readiness"].map(lambda v: fmt_pct(min(v, 1))),
    }), hide_index=True, width="stretch")

# HBCU benchmarks
with tab_bench:
    section(f"Compare {POOL} on one measure",
            f"{pick} is highlighted. The dotted line marks the median.")
    measures = {k: v for k, v in {**metrics_for(me), **METRICS}.items()
                if compare_set(v[0])[v[0]].notna().sum() >= 3}
    left, right = st.columns([2, 1])
    label = left.selectbox("Measure", list(measures), index=0, format_func=label_of)
    col, hi, f = measures[label]
    d = compare_set(col).dropna(subset=[col]).sort_values(col, ascending=not hi)
    if len(d) > 10:
        top_n = right.slider("Institutions shown", 10, min(60, len(d)), min(25, len(d)))
    else:
        top_n = len(d)
        right.caption(f"All {len(d)} institutions with data are shown.")
    shown = d.head(top_n)
    if me.unitid not in shown["unitid"].values and me.unitid in d["unitid"].values:
        shown = pd.concat([shown, d[d["unitid"] == me.unitid]])
    shown = shown.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=shown[col], y=shown["name"], orientation="h",
        marker=dict(color=[FOCUS if u == me.unitid else PEER for u in shown["unitid"]],
                    cornerradius=4, line=dict(color=SURFACE, width=1)),
        text=[f(v) for v in shown[col]], textposition="outside", textfont=dict(color=INK_2, size=11),
        hovertemplate="<b>%{y}</b><br>" + label_of(label) + ": %{text}<extra></extra>", cliponaxis=False))
    med = d[col].median()
    fig.add_vline(x=med, line=dict(color=INK_2, dash="dot", width=1.5),
                  annotation_text=f"{MED_LABEL}: {f(med)}", annotation_position="top",
                  annotation_font_color=INK_2)
    base_layout(fig, height=max(380, 22 * len(shown) + 80), showlegend=False)
    lo = min(0, shown[col].min() * 1.2)
    fig.update_xaxes(title=label_of(label), range=[lo, shown[col].max() * 1.16],
                     tickformat=".0%" if "share" in label or "growth" in label else None)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color=INK))
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)
    standing = (f"{pick} ranks {rank_of(d[col], me[col], hi)} {POOL} with data." if pd.notna(me[col])
                else f"{pick} does not report this measure.")
    st.markdown(f"<p class='note'>{standing} Retention is for fall {RET_YEAR}. Bachelor's graduation "
                f"rates follow students who entered in fall {GR_COHORT}; 2-year completion and transfer "
                f"rates follow students who entered in fall {GR_COHORT_2YR}.</p>", unsafe_allow_html=True)

    trend_text = "Total R&D spending by fiscal year, against the median HBCU and the 10 largest HBCU research programs."
    if me.in_herd:
        section(f"Research growth: {pick} and the HBCU field", trend_text)
    else:
        section("Research growth across the HBCU field",
                trend_text + f" {pick} reports under $1M a year and is not shown.")
    trend = rd[rd["unitid"].isin(hbcu["unitid"])]
    hb_med = trend.groupby("fy")["total"].median()
    mine = rd[rd["unitid"] == me.unitid].set_index("fy")["total"]
    top10 = trend[trend["fy"] == LATEST].nlargest(10, "total")["unitid"]
    top10_med = trend[trend["unitid"].isin(top10)].groupby("fy")["total"].median()
    fig = go.Figure()
    for series, name, color in [(mine, pick, FOCUS),
                                (top10_med, "Median of the 10 largest HBCU research programs", INK_2),
                                (hb_med, "Median HBCU in HERD", PEER)]:
        if series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=[f"FY{y}" for y in series.index], y=series.values, name=name, mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
            hovertemplate="%{x}: $%{y:,.1f}M<extra>" + name + "</extra>"))
    fig.add_hline(y=R1_RD_M, line=dict(color=REFERENCE, dash="dash", width=1.5),
                  annotation_text="$50M R1 threshold", annotation_position="top left",
                  annotation_font_color=INK_2)
    base_layout(fig, height=380, hovermode="x unified")
    fig.update_yaxes(title="R&D expenditures, $ millions", rangemode="tozero")
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

# Scorecard
with tab_card:
    extras = " and ".join(x for x, ok in [("has a medical school", me.medical_school),
                                            ("is a land-grant institution", me.land_grant)] if ok)
    section(f"How {pick} compares with {POOL}",
            f"Rank and percentile are among {POOL} that report each measure ({len(pool)} schools in the group)." +
            (f" {pick} {extras}." if extras else ""))
    rows = []
    for lbl, (c, hi, f) in metrics_for(me).items():
        v = me[c]
        s = compare_set(c)[c].dropna()
        pct = percentile(s, v, hi)
        bar = ("<span class='pval'>—</span>" if pct is None else
               f"<div class='pbar'><div class='ptrack'><div class='pfill' style='width:{pct * 100:.0f}%'></div>"
               f"<div class='pmid'></div></div><span class='pval'>{pct:.0%}</span></div>")
        rows.append(f"<tr><td>{label_of(lbl)}</td>"
                    f"<td class='v'>{'—' if pd.isna(v) else f(v)}</td>"
                    f"<td class='m'>{'—' if s.empty else f(s.median())}</td>"
                    f"<td class='m'>{rank_of(s, v, hi)}</td><td>{bar}</td></tr>")
    st.markdown("<div class='score-wrap'><table class='score'><thead><tr><th>Measure</th><th>Value</th>"
                f"<th>{MED_LABEL}</th><th>Rank</th><th>Percentile (line = median)</th>"
                "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)

    if not me.in_herd:
        rates = {k: v for k, v in metrics_for(me).items() if k not in STAFFING}
        section(f"Where {pick} sits in the group",
                f"Each gray dot is one of the {POOL}; the dark mark is the median.")
        st.markdown(f"<span class='legend-key'><span class='dot' style='background:{FOCUS}'></span>{pick}</span>"
                    f"<span class='legend-key'><span class='dot' style='background:{PEER}'></span>Other schools</span>",
                    unsafe_allow_html=True)
        fig = go.Figure()
        for lbl, (c, hi, f) in rates.items():
            s = pool.dropna(subset=[c])
            others = s[s["unitid"] != me.unitid]
            y = label_of(lbl).replace(" (%)", "")
            fig.add_trace(go.Scatter(
                x=others[c], y=[y] * len(others), mode="markers", text=others["name"],
                marker=dict(size=11, color=PEER, opacity=0.75, line=dict(color=SURFACE, width=1)),
                hovertemplate="<b>%{text}</b><br>%{x:.0f}%<extra></extra>"))
            if not s.empty:
                fig.add_trace(go.Scatter(
                    x=[s[c].median()], y=[y], mode="markers", hoverinfo="skip",
                    marker=dict(symbol="line-ns", size=26, line=dict(color=INK, width=2.5))))
            if pd.notna(me[c]):
                fig.add_trace(go.Scatter(
                    x=[me[c]], y=[y], mode="markers",
                    marker=dict(size=16, color=FOCUS, line=dict(color=SURFACE, width=2)),
                    hovertemplate=f"<b>{pick}</b><br>%{{x:.0f}}%<extra></extra>"))
        base_layout(fig, height=110 * len(rates) + 70, showlegend=False)
        fig.update_layout(margin=dict(r=40))
        fig.update_xaxes(title="Percent", range=[0, 100], ticksuffix="%")
        fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=INK), autorange="reversed")
        st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)
        st.markdown(f"<p class='note'>Retention is for fall {RET_YEAR}; graduation rates follow students "
                    f"who entered in fall {GR_COHORT if me.level == '4-year' else GR_COHORT_2YR}. "
                    f"{pick} reports under $1M a year in research, so research measures are not shown.</p>",
                    unsafe_allow_html=True)
    else:
        a, b = st.columns(2)
        with a:
            section("Where the research money comes from", f"R&D spending by source, FY{LATEST}.")
            src = rd[(rd["unitid"] == me.unitid) & (rd["fy"] == LATEST)]
            if src.empty:
                st.info(f"No HERD data for FY{LATEST}.")
            else:
                s = src.iloc[0]
                parts = pd.Series({"Federal government": s.federal, "Institution funds": s.institution,
                                   "Nonprofit organizations": s.nonprofit, "Business": s.business,
                                   "State and local government": s.state_local, "All other sources": s.other})
                parts = parts.sort_values()
                fig = go.Figure(go.Bar(
                    x=parts.values, y=parts.index, orientation="h",
                    marker=dict(color=FOCUS, cornerradius=4),
                    text=[f"{fmt_m(v)} ({v / s.total:.0%})" for v in parts.values],
                    textposition="outside", textfont=dict(color=INK_2, size=11), cliponaxis=False,
                    hovertemplate="%{y}: $%{x:,.1f}M<extra></extra>"))
                base_layout(fig, height=300, showlegend=False)
                fig.update_xaxes(title="$ millions", range=[0, parts.max() * 1.45])
                fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont_color=INK)
                st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)
        with b:
            section("Research doctorates awarded", "Doctor's degrees in research or scholarship, by fiscal year.")
            dd = doc[doc["unitid"] == me.unitid]
            fig = go.Figure(go.Bar(
                x=[f"FY{y}" for y in dd["fy"]], y=dd["research_doctorates"],
                marker=dict(color=FOCUS, cornerradius=4), text=dd["research_doctorates"].astype(int),
                textposition="outside", textfont=dict(color=INK_2), cliponaxis=False,
                hovertemplate="%{x}: %{y:,.0f} doctorates<extra></extra>"))
            fig.add_hline(y=R1_DOC, line=dict(color=REFERENCE, dash="dash", width=1.5))
            fig.add_annotation(x=1, xref="paper", y=R1_DOC, xanchor="left", showarrow=False,
                               text="R1: 70", font=dict(color=INK_2, size=12))
            base_layout(fig, height=300, showlegend=False, bargap=0.45)
            fig.update_layout(margin=dict(r=60))
            fig.update_yaxes(title="Doctorates", rangemode="tozero")
            st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

        with st.expander("Show the underlying numbers"):
            raw = (rd[rd["unitid"] == me.unitid].merge(doc[doc["unitid"] == me.unitid],
                                                       on=["unitid", "fy"], how="outer")
                   .drop(columns="unitid").sort_values("fy"))
            raw = raw.rename(columns={
                "fy": "Fiscal year", "federal": "Federal ($M)", "state_local": "State & local ($M)",
                "business": "Business ($M)", "nonprofit": "Nonprofit ($M)", "institution": "Institution ($M)",
                "other": "Other ($M)", "total": "Total R&D ($M)", "research_doctorates": "Research doctorates"})
            st.dataframe(raw.round(1), hide_index=True, width="stretch")

# Data & methods
with tab_about:
    st.markdown(f"""
#### What this dashboard measures
**R1 thresholds.** Under the 2025 Carnegie research designations, an R1 university spends at least
**$50 million a year on research and development** and awards at least **70 research doctorates a
year**. This dashboard compares each HBCU with those thresholds using the **3-year average for
{WINDOW}**, the most recent data available.

**This is not the official designation.** The 2025 designations were based on earlier fiscal years,
so an institution's position here can differ from its official designation. As a check, this
pipeline reproduces the figures ACE reported for Howard's FY2023 evaluation year: about $85M in R&D
and 96 research doctorates. The *Designation (2025)* column shows the official result; the charts show
where institutions stand on newer data.

#### Peer groups
Each HBCU is compared, by default, with schools of the same level and research designation:
**HBCU research universities (R1 and R2)**, **HBCU research colleges and universities**,
**other 4-year HBCUs** and **2-year HBCUs**. The sidebar switches the comparison to all HBCUs.
Schools that report under $1M a year in research lead with student outcomes instead of the R1
thresholds. For 2-year colleges, the bachelor's graduation rate does not apply, so their pages use
the completion rate within 150% of normal time and the transfer-out rate.

#### Sources
| Measure | Source | Years |
|---|---|---|
| R&D expenditures, by source of funds | NSF National Center for Science and Engineering Statistics, Higher Education Research and Development (HERD) Survey, public-use files | FY{LATEST - 2}–FY{LATEST} |
| Research doctorates | IPEDS Completions (award level 17, all fields, first major) | {WINDOW} |
| HBCU status, Carnegie designation, institution details | IPEDS Institutional Characteristics (HD{LATEST}) | {LATEST} |
| First-year retention | IPEDS Fall Enrollment, Part D | Fall {RET_YEAR} |
| 6-year graduation rates (bachelor's, all and Pell) | IPEDS Graduation Rates (derived variables) | {GR_COHORT} entering cohort |
| Completion within 150% of normal time, transfer-out rate (2-year colleges) | IPEDS Graduation Rates (derived variables) | {GR_COHORT_2YR} entering cohort |
| Students per faculty member | IPEDS Fall Enrollment, Part D | Fall {RET_YEAR} |
| Level (4-year or 2-year) | IPEDS Institutional Characteristics (HD{LATEST}) | {LATEST} |

#### Notes
- HERD's full survey covers institutions with **$1M or more** in R&D. Smaller programs answer a short form
  that isn't loaded here, so those HBCUs show no R&D figures.
- Dollar figures are current (not inflation-adjusted) dollars.
- Retention and graduation rates describe first-time, full-time undergraduates.

To refresh with a new year, add the new raw files to `data/raw/` and run
`python pipeline/build_data.py`.
""")
