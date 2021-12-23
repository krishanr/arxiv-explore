from pathlib import Path
import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)
from requests_futures.sessions import FuturesSession
import requests
import json

project_dir = Path(__file__).resolve().parents[1]

top_k, threshold = 3, 10

df_papers =  pd.read_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-paper.csv",dtype={'id': object})
df_versions =  pd.read_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-version.csv",dtype={'id': object})
df_taxonomy = pd.read_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-taxonomy.csv")
df_categories = pd.read_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-category.csv",dtype={'id': object})
df_citations = pd.read_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-citation.csv" ,dtype={'id': object, 'id_reference' : object})

def top_k_influential_full(df_citation_counts, top_k=3, threshold=10):
    # First merge the categories to the citations.
    cits = df_citation_counts.merge(df_categories.merge(df_taxonomy, on="category_id"), left_on="id_reference", right_on="id", how='right')

    cits = cits.loc[cits.groupby(['category_id','year'])['id_x'].nlargest(top_k).reset_index()['level_2']]
    cits = cits.query ( "id_x > @threshold" )
    cits = cits.rename(columns={"id_x":"references", "id_reference":"id"})
    cits = cits.merge(df_papers,on="id")
    
    return cits

def get_cp_id(req_result):
    if req_result:
        return json.loads(req_result.text)['paperId']
    else:
        return ""

def main():
    (project_dir / "data/web").mkdir(parents=True, exist_ok=True)

    # Create a dataframe, _df, containing arXiv category sizes.

    _df = df_categories.merge(df_taxonomy, on="category_id", how="left").drop_duplicates(["id","group_name"]) \
                   .groupby("category_id").agg({"id":"count", "group_name" : "min", "category_name" : "min", "category_description" : "min"}) \
                   .sort_values(by="id",ascending=False).reset_index()
    _df['count'] = _df.id

    _df.to_csv((project_dir / "data/web/arxiv-group-count.csv"), index=False)

    print("Made arxiv-group-count csv file.")

    # Now create a table containing the top 3 citations in each category per year. 
    # A heatmap will be created from this and shown when one of the cells in the above tree map is clicked.

    df_citation_counts = df_citations.merge( df_versions.query("version == 'v1'")[["id","year"]], on ="id").groupby(["year","id_reference"]).count()
    df_citation_counts = df_citation_counts.reset_index()

    df_citation_counts = df_citation_counts.merge( df_versions.query("version == 'v1'")[["id","year"]], left_on ="id_reference", right_on ="id")
    df_citation_counts = df_citation_counts.rename(columns={"id_x":"id", "year_x" : "year", "year_y" : "year_orig"})
    df_citation_counts = df_citation_counts.drop(columns='id_y')

    cits_full = top_k_influential_full(df_citation_counts, top_k, threshold)
    cits_full.year = cits_full.year.astype('int')
    cits_full.year_orig = cits_full.year_orig.astype('int')

    # Add ids for the connected papers app.
    # Code to get connected papers url from here: https://static.arxiv.org/static/browse/0.3.2.8/js/connectedpapers.js
    cp_ids = []
    arxiv_to_cp_map = {}
    with FuturesSession(max_workers=5) as session: # max_workers should not be too high so you don't make too many requests per second and get blocked
        for (arxiv_id, future) in [ (arxiv_id, session.get(f"https://rest.connectedpapers.com/id_translator/arxiv/{arxiv_id}")) for arxiv_id in  cits_full['id'].tolist()]:
            try:
                cache = arxiv_to_cp_map.get(arxiv_id, "")
                if not cache:
                    cache = get_cp_id(future.result())
                    arxiv_to_cp_map[arxiv_id] = cache
                cp_ids.append(cache)            
            except:
                cp_ids.append("")

    assert len(cp_ids) == cits_full.shape[0], "Unexpected mismatch between connected papers ids and size of the cits_full dataframe."
    cits_full['cp_id'] = cp_ids

    cits_full.to_csv((project_dir / "data/web/arxiv-metadata-influential.csv"), index=False)
    
    print("Made arxiv-metadata-influential csv file.")

if __name__ == "__main__":
    main()