"""The treemap is only redrawn when the view (category/group) changes, not when a paper is selected."""

import plotly.graph_objects as go
from dash import no_update

import app as site


def treemap_of(search, shown_view):
    return site.render(search, shown_view)[0]


def test_selecting_a_paper_leaves_the_treemap_alone():
    assert treemap_of("?cat=cs.LG&paper=1706.03762", "cs.LG") is no_update


def test_changing_the_view_redraws_the_treemap():
    assert isinstance(treemap_of("?cat=cs.LG", "group:Physics"), go.Figure)
    assert isinstance(treemap_of("?cat=group:Physics", "cs.LG"), go.Figure)
    assert isinstance(treemap_of("", "cs.LG"), go.Figure)


def test_first_render_draws_the_treemap():
    assert isinstance(treemap_of("?cat=cs.LG&paper=1706.03762", None), go.Figure)


def test_render_reports_the_view_it_shows():
    *_, shown_view = site.render("?cat=cs.LG&paper=1706.03762", "cs.LG")
    assert shown_view == "cs.LG"
    *_, shown_view = site.render("", "cs.LG")
    assert shown_view == ""


def click(tile_id, search):
    return site.next_url("treemap", {"points": [{"id": tile_id}]}, search)


def test_a_selected_category_is_shown_zoomed_on_its_own_tile():
    # Plotly zooms into a category tile when it's clicked, so the figure must agree.
    assert site.treemap_figure("cs.LG").data[0].level == "cat:cs.LG"
    assert site.treemap_figure("group:Physics").data[0].level == "group:Physics"
    assert site.treemap_figure("").data[0].level == "all"


def test_clicking_the_current_tile_goes_up_one_level():
    assert click("cat:cs.LG", "?cat=cs.LG&paper=1706.03762") == "?cat=group%3AComputer+Science"
    assert click("group:Physics", "?cat=group%3APhysics") == ""
    assert click("all", "") == ""


def test_clicking_a_tile_selects_it():
    assert click("group:Physics", "") == "?cat=group%3APhysics"
    assert click("cat:hep-th", "?cat=group%3APhysics") == "?cat=hep-th"
