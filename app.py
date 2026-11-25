"""arXiv Explorer: the most-cited arXiv preprints by category and year.

Run locally:  uv run python app.py       (http://127.0.0.1:8050)
Production:   gunicorn app:server

URL state:    /?cat=<view>&paper=<arXiv id>
              view is "" (all of arXiv), "group:<group name>", or an arXiv category code like "cs.LG".
"""

import json
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from pipeline.jsonl import read_jsonl

DATA = Path(__file__).resolve().parent / "data"
TOP_K = 3
ARXIV_RED = "#b31b1b"
TEXT, TEXT_2, GRID = "#191919", "#666666", "#e6e6e6"
# Single-hue sequential ramp (light -> arXiv red) for category size.
SIZE_SCALE = [[0, "#f6d5d5"], [0.5, "#e07a7a"], [1, ARXIV_RED]]
ROOT_ID = "all"

# ---------------------------------------------------------------- data

taxonomy = pd.DataFrame(json.loads((DATA / "taxonomy.json").read_text())).set_index("code")
counts = json.loads((DATA / "categories.json").read_text())
taxonomy["count"] = [counts.get(c, {}).get("count", 0) for c in taxonomy.index]
taxonomy = taxonomy[taxonomy["count"] > 0]

top = pd.DataFrame(read_jsonl(DATA / "top_papers.jsonl"))
top = top[top["category"].isin(taxonomy.index) & (top["citations"] > 0)]
top["group"] = top["category"].map(taxonomy["group"])
papers = top.sort_values("citations", ascending=False).drop_duplicates("arxiv_id").set_index("arxiv_id")
GROUPS = sorted(taxonomy["group"].unique())

_state = json.loads((DATA / "state.json").read_text())
UPDATED = max(datetime.fromisoformat(v) for v in _state.values()).strftime("%B %-d, %Y") if _state else "never"


def parse_url(search: str | None) -> tuple[str, str | None]:
    q = parse_qs((search or "").lstrip("?"))
    view = q.get("cat", [""])[0]
    valid = view[6:] in GROUPS if view.startswith("group:") else view in taxonomy.index
    if not valid:
        view = ""
    paper = q.get("paper", [None])[0]
    return view, paper if paper in papers.index else None


def make_url(view: str, paper: str | None = None) -> str:
    params = {k: v for k, v in {"cat": view, "paper": paper}.items() if v}
    return "?" + urlencode(params) if params else ""


def view_name(view: str) -> str:
    if not view:
        return "all of arXiv"
    if view.startswith("group:"):
        return view[6:]
    return f"{taxonomy.at[view, 'name']} ({view})"


def view_papers(view: str) -> pd.DataFrame:
    """Top-K papers per posting year within a view (category, group or all)."""
    if view.startswith("group:"):
        rows = top[top["group"] == view[6:]]
    elif view:
        rows = top[top["category"] == view]
    else:
        rows = top
    rows = rows.sort_values("citations", ascending=False).drop_duplicates(["year", "arxiv_id"])
    return rows.groupby("year").head(TOP_K).sort_values(["year", "citations"])


def displayed_level(view: str) -> str:
    """Treemap node to zoom to: a selected category is shown inside its group."""
    if not view:
        return ROOT_ID
    return view if view.startswith("group:") else f"group:{taxonomy.at[view, 'group']}"


# ---------------------------------------------------------------- figures


def treemap_figure(view: str) -> go.Figure:
    ids, labels, parents, values, hover = [ROOT_ID], ["arXiv"], [""], [int(taxonomy["count"].sum())], [""]
    for group, g in taxonomy.groupby("group"):
        ids.append(f"group:{group}")
        labels.append(group)
        parents.append(ROOT_ID)
        values.append(int(g["count"].sum()))
        hover.append(f"{len(g)} categories")
    for code, row in taxonomy.iterrows():
        ids.append(f"cat:{code}")
        labels.append(f"{row['name']}<br><span style='font-size:0.8em'>{code}</span>")
        parents.append(f"group:{row['group']}")
        values.append(int(row["count"]))
        desc = row.get("description") or ""
        hover.append(desc[:160] + ("…" if len(desc) > 160 else ""))
    # Colour by log size, scaled to the category range so the root and groups don't flatten the ramp.
    # Root and group tiles (mostly just headers) take the light end of the ramp.
    cmin, cmax = math.log10(taxonomy["count"].min()), math.log10(taxonomy["count"].max())
    colors = [
        cmin if i == ROOT_ID or i.startswith("group:") else math.log10(v) for i, v in zip(ids, values, strict=True)
    ]
    level = displayed_level(view)
    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            customdata=hover,
            level=level,
            maxdepth=3,  # root -> groups -> categories, or group -> categories when zoomed
            marker=dict(
                colors=colors,
                colorscale=SIZE_SCALE,
                cmin=cmin,
                cmax=cmax,
                line=dict(color="#ffffff", width=2),
                pad=dict(t=22),
            ),
            hovertemplate="<b>%{label}</b><br>%{value:,} papers<br>%{customdata}<extra></extra>",
            texttemplate="%{label}",
            root=dict(color="#f3f3f3"),
        )
    )
    fig.update_layout(margin=dict(t=4, l=4, r=4, b=4), height=420, font=dict(family="system-ui, sans-serif"))
    return fig


def log_ticks(lo: float, hi: float) -> list[int]:
    """1-2-5 ticks spanning [lo, hi]; only decades when the range is wide."""
    steps = (1,) if hi / max(lo, 1) > 1000 else (1, 2, 5)
    ticks = [m * 10**e for e in range(8) for m in steps]
    return [t for t in ticks if lo / 2 <= t <= hi * 2]


DOT_BASE, DOT_PER_DECADE = 4, 5  # px: diameter = 4 + 5 * log10(citations), the same scale in every view


def dot_sizes(citations: pd.Series) -> list[float]:
    """Dot diameter grows with log10(citations): 10 -> 9px, 1,000 -> 19px, 100,000 -> 29px."""
    return [DOT_BASE + DOT_PER_DECADE * math.log10(max(c, 1)) for c in citations]


def dots_figure(rows: pd.DataFrame, selected: str | None) -> go.Figure:
    fig = go.Figure()
    if rows.empty:
        fig.add_annotation(text="No cited papers in this category yet.", showarrow=False, font=dict(color=TEXT_2))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
    else:
        # Draw the biggest dots first so smaller ones stay on top and clickable.
        rows = rows.sort_values("citations", ascending=False)
        sizes = dot_sizes(rows["citations"])
        names = rows["category"].map(taxonomy["name"])
        fig.add_trace(
            go.Scatter(
                x=rows["year"],
                y=rows["citations"],
                mode="markers",
                customdata=list(zip(rows["arxiv_id"], rows["title"].str.slice(0, 90), names, strict=True)),
                marker=dict(size=sizes, color=ARXIV_RED, opacity=0.75, line=dict(color="#ffffff", width=1.5)),
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>%{x} · %{y:,} citations<br>"
                    "%{customdata[2]} · arXiv:%{customdata[0]}<extra></extra>"
                ),
            )
        )
        if selected in set(rows["arxiv_id"]):
            i = rows.index.get_loc(rows.index[rows["arxiv_id"] == selected][0])
            s = rows.iloc[i]
            fig.add_trace(
                go.Scatter(
                    x=[s["year"]],
                    y=[s["citations"]],
                    mode="markers",
                    hoverinfo="skip",
                    marker=dict(size=sizes[i] + 8, color="rgba(0,0,0,0)", line=dict(color=TEXT, width=2)),
                )
            )
        ticks = log_ticks(rows["citations"].min(), rows["citations"].max())
        fig.update_yaxes(
            type="log",
            title="Citations (log scale)",
            gridcolor=GRID,
            zeroline=False,
            tickvals=ticks,
            ticktext=[f"{t:,}" for t in ticks],
        )
        fig.update_xaxes(title="Year first posted to arXiv", gridcolor=GRID, tickformat="d")
    fig.update_layout(
        height=420,
        showlegend=False,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=10, l=60, r=20, b=50),
        font=dict(family="system-ui, sans-serif", color=TEXT),
        hoverlabel=dict(bgcolor="#ffffff", font_color=TEXT, bordercolor=GRID),
    )
    return fig


def paper_card(arxiv_id: str | None):
    if arxiv_id is None:
        return html.P("Click a dot to see a paper's details.", className="text-muted")
    p = papers.loc[arxiv_id]
    authors = ", ".join(p["authors"])
    if p["n_authors"] > len(p["authors"]):
        authors += f" … (+{p['n_authors'] - len(p['authors'])} more)"

    def link(label, href):
        return html.A(label, href=href, target="_blank", rel="noopener", className="me-3")

    return [
        html.H4(p["title"], className="mb-1"),
        html.P(authors, className="text-muted mb-1"),
        html.P(
            f"arXiv:{arxiv_id} · first posted {p['year']} · {p['citations']:,} citations · "
            + ", ".join(p["categories"]),
            className="small text-muted",
        ),
        html.P(p["abstract"], className="mt-2"),
        html.Div(
            [
                link("arXiv abstract", f"https://arxiv.org/abs/{arxiv_id}"),
                link("PDF", f"https://arxiv.org/pdf/{arxiv_id}"),
                link("NASA ADS", f"https://ui.adsabs.harvard.edu/abs/{p['bibcode']}/abstract"),
                link("Connected Papers", f"https://www.connectedpapers.com/api/redirect/arxiv/{arxiv_id}"),
            ]
        ),
    ]


# ---------------------------------------------------------------- layout


def icon_link(label: str, href: str, icon: str) -> html.A:
    """An icon-only link; the label is the tooltip and the screen-reader text."""
    return html.A(
        html.Img(src=app.get_asset_url(icon), alt=""),
        href=href,
        title=label,
        target="_blank",
        rel="noopener",
        className="icon-link",
        **{"aria-label": label},
    )


app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], title="arXiv Explorer")
server = app.server

app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="scroll-to"),  # element id to scroll to once the next render lands
        dbc.Navbar(
            dbc.Container(
                [
                    html.A(dbc.NavbarBrand("arXiv Explorer", className="fw-bold"), href="/"),
                    html.Span("The most-cited preprints in every arXiv category, by year", className="text-white-50"),
                ]
            ),
            color=ARXIV_RED,
            dark=True,
            className="mb-3",
        ),
        dbc.Container(
            [
                dcc.Dropdown(
                    id="search",
                    placeholder="Search categories or paper titles…",
                    searchable=True,
                    clearable=True,
                    className="mb-3",
                ),
                html.P(
                    "Categories sized by number of papers. Click a group to zoom in, a category to select it.",
                    className="small text-muted mb-1",
                ),
                dcc.Graph(id="treemap", config={"displayModeBar": False}),
                html.H5(id="view-title", className="mt-4"),
                dcc.Graph(id="dots", config={"displayModeBar": False}),
                dbc.Card(dbc.CardBody(id="paper"), className="my-3", style={"backgroundColor": "#f6f7fb"}),
                html.Footer(
                    [
                        html.Div(
                            [
                                f"Citation counts from NASA's Astrophysics Data System, last updated {UPDATED}. ",
                                (
                                    f"Shows the top {TOP_K} most-cited papers first posted in each year; "
                                    "cross-listed papers count in every category they are listed in. "
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                icon_link("By Krishan Rajaratnam (PhD)", "https://krishanr.github.io/blog/", "blog.svg"),
                                icon_link(
                                    "Source code on GitHub", "https://github.com/krishanr/arxiv-explore", "github.svg"
                                ),
                            ],
                            className="d-flex gap-3",
                        ),
                    ],
                    id="site-footer",
                    className="small text-muted mb-4 d-flex justify-content-between align-items-end gap-4",
                ),
            ]
        ),
    ]
)

# ---------------------------------------------------------------- callbacks


@app.callback(
    Output("url", "search"),
    Output("treemap", "clickData"),
    Output("dots", "clickData"),
    Output("search", "value"),
    Output("scroll-to", "data"),
    Input("treemap", "clickData"),
    Input("dots", "clickData"),
    Input("search", "value"),
    State("url", "search"),
    prevent_initial_call=True,
)
def navigate(tree_click, dot_click, search_value, search):
    """Turn clicks and searches into a new URL (the single source of truth), then reset the inputs."""
    event = {"treemap": tree_click, "dots": dot_click, "search": search_value}.get(ctx.triggered_id)
    url = next_url(ctx.triggered_id, event, search) if event else None
    if url is None:
        return (no_update,) * 5
    # After a search, bring the result into view: the paper panel, or the chart for a category/group.
    scroll = ("paper" if event.startswith("paper:") else "view-title") if ctx.triggered_id == "search" else None
    return url, None, None, None, scroll


# Runs in the browser after the paper panel re-renders, so it scrolls to the updated content.
app.clientside_callback(
    """function(_children, target) {
        if (!target) { return window.dash_clientside.no_update; }
        setTimeout(() => {
            const el = document.getElementById(target);
            if (el) { el.scrollIntoView({behavior: "smooth", block: "start"}); }
        }, 50);
        return null;
    }""",
    Output("scroll-to", "data", allow_duplicate=True),
    Input("paper", "children"),
    State("scroll-to", "data"),
    prevent_initial_call=True,
)


def next_url(source: str, event, search: str | None) -> str:
    view, _ = parse_url(search)
    if source == "treemap":
        clicked = event["points"][0]["id"]
        if clicked == displayed_level(view):
            clicked = ROOT_ID  # clicking the zoomed-in group's header zooms back out
        return make_url("" if clicked == ROOT_ID else clicked.removeprefix("cat:"))
    if source == "dots":
        return make_url(view, event["points"][0]["customdata"][0])
    kind, _, key = event.partition(":")  # search box value: "group:<name>", "cat:<code>" or "paper:<id>"
    if kind == "paper":
        return make_url(papers.at[key, "category"], key)
    return make_url(key if kind == "cat" else event)


@app.callback(
    Output("treemap", "figure"),
    Output("view-title", "children"),
    Output("dots", "figure"),
    Output("paper", "children"),
    Input("url", "search"),
)
def render(search):
    view, paper = parse_url(search)
    rows = view_papers(view)
    if paper is None and not rows.empty:
        paper = rows.loc[rows["citations"].idxmax(), "arxiv_id"]
    title = f"Top {TOP_K} most-cited papers per year in {view_name(view)} (dot size ∝ log citations)"
    return treemap_figure(view), title, dots_figure(rows, paper), paper_card(paper)


SEARCH_INDEX = [(f"group:{g}", g, g.lower()) for g in GROUPS]
SEARCH_INDEX += [(f"cat:{c}", f"{r['name']} ({c})", f"{r['name']} {c}".lower()) for c, r in taxonomy.iterrows()]
SEARCH_INDEX += [
    (f"paper:{i}", f"{r['title'][:100]} ({r['year']})", f"{r['title']} {i}".lower()) for i, r in papers.iterrows()
]


@app.callback(Output("search", "options"), Input("search", "search_value"))
def search_options(text):
    if not text or len(text) < 2:
        return no_update
    words = text.lower().split()
    hits = [(v, label) for v, label, key in SEARCH_INDEX if all(w in key for w in words)]
    return [{"value": v, "label": label} for v, label in hits[:25]]


if __name__ == "__main__":
    app.run(debug=True)
