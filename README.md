This project uses the arxiv metadata-v5 to create an interactive dashboard for viewing influential preprints.

Once installed, the dash app, can be run locally using the commands:

```bash
$ conda activate arxivexplorer
$ python app.py
```

Also see the jupter notebook for scratch work done before the dash app was made.

### Installation

First create the conda environment using:

```bash
$ conda env create --file=environment.yml
$ conda activate arxivexplorer
```

Then once the `arxivexplorer` enviroment is activated create the web data using:

```bash
$ make build_features
```

Finally, run the dash app locally using:

```bash
$ python app.py
```

The app can also be run on heroku by following the instructions.

### Data

This app uses the arxiv metadata-v5 available from the Google cloud, at "gs://arxiv-dataset/metadata-v5". Specifically, the files "arxiv-metadata-oai.json" and "internal-citations.json" are used.

### References
* https://www.kaggle.com/steubk/arxiv-taxonomy-e-top-influential-papers?rvi=1