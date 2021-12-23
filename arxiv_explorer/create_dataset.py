from pathlib import Path
import subprocess
import  json
import re
from collections import defaultdict

import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)
import requests
from bs4 import BeautifulSoup

project_dir = Path(__file__).resolve().parents[1]

METADATA_PATH = project_dir / "data/raw/archive/arxiv-metadata-oai.json"


def main():
    (project_dir / "data/raw/archive").mkdir(parents=True, exist_ok=True)
    (project_dir / "data/processed/archive").mkdir(parents=True, exist_ok=True)

    # First download the data.
    subprocess.run(["gsutil", "cp", "gs://arxiv-dataset/metadata-v5/arxiv-metadata-oai.json", str(project_dir / "data/raw/archive")])
    subprocess.run(["gsutil", "cp", "gs://arxiv-dataset/metadata-v5/internal-citations.json", str(project_dir / "data/raw/archive")])

    # Now make the data frames.
    with open( (project_dir / "data/raw/archive/internal-citations.json")) as f:
        citations = json.load(f)

    with open(project_dir / "data/processed/archive/arxiv-metadata-ext-citation.csv","w+") as f_out :
        f_out.write("id,id_reference\n")
        for i,id in enumerate(citations):
            for k in citations[id]:
                f_out.write(f'{id},{k}\n')
    
    print("Made the citation csv file.")

    with open(project_dir / "data/processed/archive/arxiv-metadata-ext-category.csv","w+") as f_out :
        f_out.write("id,category_id\n")

        # Use the seen dictionary to remove duplicates found in the data.
        seen = defaultdict(bool)
        with open(METADATA_PATH) as f_in:
            for i,line in enumerate(f_in):
                row = json.loads(line)
                id = row["id"]
                if not seen[id]:
                    categories = row["categories"][0].split()
                    for c in categories:
                        f_out.write ( f'"{id}","{c}"\n'  )
                    seen[id] = True

    print("Made the category csv file.")

    titles = []
    abstracts = []
    ids = []
    authors = []
    journal_refs = []

    with open(METADATA_PATH) as f_in:
        
        seen = defaultdict(bool)
        for i,line in enumerate(f_in):
            row = json.loads(line)

            if not seen[row["id"]]:
                titles.append(row["title"])
                abstracts.append(row["abstract"])
                ids.append(row["id"])
                authors.append(row["authors"]) 
                journal_refs.append(row["journal-ref"])
                seen[row["id"]] = True
            
    df_papers = pd.DataFrame({
        'id' : ids,
        'title' : titles,
        'abstract' : abstracts,
        'authors' : authors,
        'journal-ref' : journal_refs
        
    })
    df_papers.to_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-paper.csv", index=False)
    
    print("Made the paper csv file.")
    
    with open(project_dir / "data/processed/archive/arxiv-metadata-ext-version.csv","w+") as f_out :
        f_out.write("id,version,year,month\n")

        seen = defaultdict(bool)
        with open(METADATA_PATH) as f_in:
            for i,line in enumerate(f_in):
                row = json.loads(line)
                id = row["id"]
                versions = row["versions"]

                if not seen[id]:
                    # Get the year and month of the first version.
                    year_string = id.split("/")
                    if len(year_string) == 1:
                        year_string = year_string[0]
                    else:
                        year_string = year_string[1]

                    year, month = year_string[0:2], year_string[2:4]
                    if int(year) > 90:
                        year = "19" + year
                    else:
                        year = "20" + year
                    month = str(int(month))
                    for v in versions:
                        if v == "v1":
                            f_out.write (f'{id},{v},{year},{month}\n')
                        else:
                            # Don't have date info for other versions.
                            f_out.write (f'{id},{v},,\n')
                    seen[id] = True

    print("Made the version csv file.")

    ## load taxonomy from https://arxiv.org/category_taxonomy
    website_url = requests.get('https://arxiv.org/category_taxonomy').text
    soup = BeautifulSoup(website_url,'lxml')

    root = soup.find('div',{'id':'category_taxonomy_list'})

    tags = root.find_all(["h2","h3","h4","p"], recursive=True)

    level_1_name = ""
    level_2_code = ""
    level_2_name = ""

    level_1_names = []
    level_2_codes = []
    level_2_names = []
    level_3_codes = []
    level_3_names = []
    level_3_notes = []

    for t in tags:
        if t.name == "h2":
            level_1_name = t.text    
            level_2_code = t.text
            level_2_name = t.text
        elif t.name == "h3":
            raw = t.text
            level_2_code = re.sub(r"(.*)\((.*)\)",r"\2",raw)
            level_2_name = re.sub(r"(.*)\((.*)\)",r"\1",raw)
        elif t.name == "h4":
            raw = t.text
            level_3_code = re.sub(r"(.*) \((.*)\)",r"\1",raw)
            level_3_name = re.sub(r"(.*) \((.*)\)",r"\2",raw)
        elif t.name == "p":
            notes = t.text
            level_1_names.append(level_1_name)
            level_2_names.append(level_2_name)
            level_2_codes.append(level_2_code)
            level_3_names.append(level_3_name)
            level_3_codes.append(level_3_code)
            level_3_notes.append(notes)

    df_taxonomy = pd.DataFrame({
        'group_name' : level_1_names,
        'archive_name' : level_2_names,
        'archive_id' : level_2_codes,
        'category_name' : level_3_names,
        'category_id' : level_3_codes,
        'category_description': level_3_notes
        
    })
    df_taxonomy.to_csv(project_dir / "data/processed/archive/arxiv-metadata-ext-taxonomy.csv", index=False)

    print("Made the taxonomy csv file.")

if __name__ == "__main__":
    main()