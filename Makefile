## Get the raw data to be used later. This works in the arxivexplorer conda environment.
create_dataset:
	python arxiv_explorer/create_dataset.py

## Script to create the data used by the dash app.
build_features: create_dataset
	python arxiv_explorer/build_web_data.py

