from pathlib import Path
import requests
import json
import pandas as pd
import numpy as np

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.express as px
from dash.dependencies import Input, Output
import plotly.graph_objects as go

project_dir = Path(__file__).resolve().parents[0]

cits_full = pd.read_csv((project_dir / "data/web/arxiv-metadata-influential.csv"),dtype={'id': object})
_df = pd.read_csv( (project_dir / "data/web/arxiv-group-count.csv") )
cits = None
top_k, threshold = 3, 10

#TODO: how does the app preform for missing categories. E.g. there are 155 categories in counts but only 137 for creating heatmaps?

# Ideas:
# Save treemap click state in url.

# Related sites:
# http://www.arxiv-sanity.com/
# https://www.connectedpapers.com/
# https://www.semanticscholar.org/

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "arXiv explorer"
server = app.server

def df_to_plotly(df):
    return {'z': df.values.tolist(),
            'x': df.columns.tolist(),
            'y': df.index.tolist()}

def get_influential_heatmap(cits): #TODO: citation counts of 0 are in accurate. They just mean the publication didn't appear in the top 3.
    """

        Notes:

        Since many publications have the same number of citations, the influential preprints heatmap isn't guarenteed to be unique, or reproducible.
    """
    cits['titleSmal'] = cits['title'].str[:30] + " ..."
    hm_cits = cits.pivot(index=["id", 'titleSmal', 'title'], columns="year",values="references") # Use id as the index to avoid collisions. Add titleSmal for display.
    hm_cits = hm_cits.fillna(0)

    titles = [ item[1] for item in hm_cits.index.to_list()]
    heatmap_data = df_to_plotly(hm_cits)
    hovertext = list()
    for yi, ( yid,yx,yy) in enumerate(heatmap_data['y']):
        hovertext.append(list())
        for xi, xx in enumerate(heatmap_data['x']):
            hovertext[-1].append('Year: {}<br />Title: {}<br />Citations: {}<br />Id: {}'.format(xx, yy, heatmap_data['z'][yi][xi], yid))

    heatmap_data['y'] = [ item[1] for item in hm_cits.index.to_list()] # Only use titleSmal in the actual heatmap.
    # Setting grid lines: https://community.plotly.com/t/grid-lines-placement-in-heatmap/2628/3
    heatmap = go.Heatmap(**heatmap_data, type = 'heatmap',colorscale=[[0, "#F08080"], [1, "#b31b1b"]], hoverinfo='text', text=hovertext)

    #TODO: what to do when the heatmap is empty? like for general topology?
    return heatmap

@app.callback(
    [
        Output("top_influential_papers", "figure")
    ],
    [
        Input("category_map", "clickData"),
    ],
)
def update_plots(selected_item):
    global cits 
    
    path = None
    if selected_item:
        path = selected_item['points'][0]['id'].split("/")
    else:
        # This occurs when the app first starts.
        # default to the all state.
        selected_item = "all"
        path = ["all"]

    if selected_item and  len(path) < 2:
        # Added this line to remove duplicate ids within a year.
        cits = cits_full.groupby(['year', 'id']).first().reset_index()

        # Collect the influential publications within this group.
        cits = cits.loc[cits.groupby(['year'])['references'].nlargest(top_k).reset_index()['level_1']]
        cits = cits.query ( "references > @threshold" )

        # Make human readable group name
        human_group_name = "arXiv"

    elif len(path) == 2:
        # Select preprints from the selected group, e.g. Mathematics.
        cits = cits_full[cits_full['group_name'] == path[1]]

        # Added this line to remove duplicate ids within a year.
        cits = cits.groupby(['year', 'id']).first().reset_index()

        # Collect the influential publications within this group.
        cits = cits.loc[cits.groupby(['year'])['references'].nlargest(top_k).reset_index()['level_1']]
        cits = cits.query ( "references > @threshold" )

        # Make human readable group name
        human_group_name = path[1]

    elif len(path) == 3:
        # Specify the group_name and category_name, since the 'Numerical Analysis' category appears in
        # mathematics and computer science.
        cits = cits_full[(cits_full['group_name'] == path[1]) & (cits_full['category_name'] == path[2])]
 
        # Make human readable group name
        human_group_name = path[2]
    else:
        import Exception

        #TODO: handle this.
        raise Exception("Unanticipated situation")

    fig = go.Figure(data = [get_influential_heatmap(cits)])

    fig.update_layout(
        title=f"Top influential preprints in {human_group_name}",
        font=dict(family="Open Sans"),
        #yaxis_nticks=16,
        #xaxis_nticks=24,
        xaxis=dict(
                ticks="",
                ticklen=2,
                tickfont=dict(family="sans-serif"),
                tickcolor="#ffffff",
        ),
        yaxis=dict(
            side="left", ticks="", tickfont=dict(family="sans-serif"), ticksuffix=" "
        ),)

    return [fig]

@app.callback(
    Output('pre_preview', 'style'),
    Output('pre_title', 'children'),
    Output('pre_authors', 'children'),
    Output('pre_abstract', 'children'),
    Output('pre_links', 'children'),
    Input('top_influential_papers', 'clickData'))
def update_graph(hoverData):
    global cits 

    if hoverData is not None:
        id = hoverData['points'][0]['text'].split("<br />")[-1][4:]
    elif cits is not None:
        id = cits.sample(1).id.iloc[0]
    else:
        # Manually create the top arXiv table for initalizing the app.
        temp_cits = cits_full.groupby(['year', 'id']).first().reset_index()

        # Collect the influential publications within this group.
        temp_cits = temp_cits.loc[temp_cits.groupby(['year'])['references'].nlargest(top_k).reset_index()['level_1']]
        temp_cits = temp_cits.query ( "references > @threshold" )

        id = temp_cits.sample(1).id.iloc[0]

    result = cits_full[cits_full['id'] == id]

    link = [ html.Span(f"{id}  ", style={ "font-weight": "lighter"}) , html.A(
        href= f"https://arxiv.org/pdf/{id}",
        children=[  html.Img(src="/assets/pdf-svg.png", title="PDF", style={'height':'10%', 'width':'10%'})   ], 
    ), 
    " ", html.A(
        href= f"https://www.connectedpapers.com/main/{result.cp_id.iloc[0]}/arxiv",
        children=[  html.Img(src="/assets/connected-papers.ico", title="Connected Papers", style={'height':'10%', 'width':'10%'})  ], 
    )]
    metadata = [ html.Span(result.authors.iloc[0]) , html.Br() ,html.Span(result.year_orig.iloc[0]) ]

    return {}, result.title.iloc[0], metadata, result.abstract.iloc[0], link[:2] if pd.isnull(result.iloc[0]).cp_id else link


category_map_fig = px.treemap(_df[~_df['group_name'].isna()].sort_values('id'), path=[px.Constant("all"), 'group_name', 'category_name'], values='count', \
                              color='count', color_continuous_scale='reds')
category_map_fig.update_traces(root_color="lightgrey")
category_map_fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))

category_map = dcc.Graph(
    id='category_map',
    figure=category_map_fig
)

# bootstrap layout: https://dash-bootstrap-components.opensource.faculty.ai/docs/components/layout/
top_influential_papers = dcc.Graph(
    id='top_influential_papers',
)

# setup the header and footer.
header = dbc.NavbarSimple( brand="arXiv explorer", children="View trends in the arXiv at a high level." , brand_href="#", color="#b31b1b", dark=True, )
footer = html.Div(children=["* This dashboard builds on work from ",html.A(
    href="https://www.kaggle.com/steubk/arxiv-taxonomy-e-top-influential-papers",
    children="this"
), " Kaggle notebook.", html.Br(), "** This dashboard is up to date as of April 2020."], style={'font-size': '12px'} )

# setup & apply the layout
layout = html.Div(
    [
        dbc.Row(dbc.Col(header)),
        dbc.Row(dbc.Col(category_map)),
        dbc.Row(dbc.Col(top_influential_papers, width=12)),
        dbc.Row(dbc.Col( dbc.Container(
    [
        html.H5(children="", className="display-5", id="pre_title"),
        html.Hr(className="my-2"),
        html.Div([
            dbc.Row([
                dbc.Col( html.P( "", id="pre_authors" ) , width=10),
                dbc.Col( html.P( "",  id="pre_links" ) , width=2)
            ])
        ]),
        html.P(
            "", id="pre_abstract"
        ),
    ]
),align="center", style={"backgroundColor": "rgb(243, 246, 251)"}), style={"display": "none"}, id="pre_preview"),
        dbc.Row(dbc.Col(footer))
    ]
)

app.layout = layout

if __name__ == '__main__':
    app.run_server(debug=False)