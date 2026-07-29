# This file is generated from the similarly named .ipynb notebook.
# Edit this Python companion for normal code changes; preserve the notebook as an artifact.

# %% [markdown]
# # Welcome to OSII: The On-Store Intelligence Index
#
# This notebook gives a concise introduction to the OSII backend and its main ideas.
#
# OSII is a structured backend for turning technical file collections into a durable, inspectable representation of:
#
# - extracted content
# - derived synthesis
# - enrichments
# - search-ready artifacts
#
# The backend is designed so that raw source files do not have to be repeatedly reprocessed just to support new downstream behaviors.
#
# ## The main idea
#
# A technical file collection often contains:
#
# - reports
# - experiment folders
# - simulation outputs
# - notes
# - supporting reference material
#
# OSII turns that collection into a structured backend where:
#
# 1. extraction produces canonical object-level artifacts
# 2. synthesis produces scope-aware summaries and interpretations
# 3. enrichment produces additional derived artifacts such as keywords or wiki bundles
# 4. indexing produces chunked retrieval artifacts for search
#
# The result is a backend that can support browsing, analysis, and future agent workflows without treating source files as the only working representation.
#
# ## Core concepts
#
# The backend revolves around three ideas:
#
# ### Objects
# Stable content units, usually corresponding to one source file.
#
# ### Scopes
# Ways of grouping objects for processing and analysis.
# Supported scope types include:
#
# - `root`
# - `folder`
# - `collection`
# - `object`
#
# ### Artifacts
# Outputs attached to an object or scope.
#
# Important artifact families include:
#
# - canonical extraction artifacts
# - text representations
# - syntheses
# - enrichments
# - indexing artifacts
#
# ## Extraction, synthesis, and enrichment
#
# ### Extraction
# Extraction creates the canonical representation of a source file.
#
# Examples:
#
# - extracted text
# - manifest records
# - source provenance
# - extracted image artifacts
#
# ### Synthesis
# Synthesis creates interpretive outputs over one scope.
#
# Examples:
#
# - file-level summary
# - folder-level experiment description
# - collection-level summary of a curated set of documents
#
# ### Enrichment
# Enrichment creates additional derived artifacts that are useful but not canonical.
#
# Examples:
#
# - keyword extraction
# - future entity extraction
# - wiki bundles
# - future analytical products
#
# ## Why scope matters
#
# A folder and a collection are not the same thing.
#
# A folder is structural:
#
# - it reflects source organization
# - it may correspond to one experiment, one run, or one case
#
# A collection is logical:
#
# - it may span multiple folders
# - it may be curated for analysis
# - it may represent a thematic or comparative grouping
#
# OSII supports both because they answer different questions.
#
# ## The current package
#
# This notebook interacts directly with the installed `osii` package.
#
# The goal is to use the backend primarily as a Python package, while still demonstrating its CLI and API surfaces in later notebooks.

# %%
import json
import osii

print("Imported osii successfully.")
print(osii)

# %% [markdown]
# ## Capability registries
#
# The backend exposes registries for:
#
# - extractors
# - file synthesizers
# - folder synthesizers
# - collection synthesizers
# - enrichers
#
# This makes the backend inspectable and helps downstream tools discover what is available.

# %%
from osii.extraction.registry import list_extractor_descriptions
from osii.synthesis.registry import list_synthesizer_descriptions
from osii.synthesis.folder_registry import list_folder_synthesizer_descriptions
from osii.synthesis.collection_registry import list_collection_synthesizer_descriptions
from osii.enrichment.registry import list_enricher_descriptions

# %%
extractors = list_extractor_descriptions()
file_synthesizers = list_synthesizer_descriptions()
folder_synthesizers = list_folder_synthesizer_descriptions()
collection_synthesizers = list_collection_synthesizer_descriptions()
enrichers = list_enricher_descriptions()

capabilities = {
    "extractors": extractors,
    "file_synthesizers": file_synthesizers,
    "folder_synthesizers": folder_synthesizers,
    "collection_synthesizers": collection_synthesizers,
    "enrichers": enrichers,
}

capabilities

# %% [markdown]
# ## Extractors
#
# Extractors define how source files become canonical OSII object artifacts.
#
# Each extractor advertises:
#
# - name
# - display name
# - description
# - version

# %%
extractors

# %% [markdown]
# ## File synthesizers
#
# File synthesizers operate on one object at a time and produce file-level summaries or descriptions.

# %%
file_synthesizers

# %% [markdown]
# ## Folder synthesizers
#
# Folder synthesizers operate over source-structure-informed scopes.
#
# This is especially important when a folder itself represents a meaningful unit such as:
#
# - one experiment
# - one simulation case
# - one run directory

# %%
folder_synthesizers

# %% [markdown]
# ## Collection synthesizers
#
# Collection synthesizers operate on logical user-defined groupings.
#
# These are useful when the meaningful unit is not the folder tree but a curated set of objects.

# %%
collection_synthesizers

# %% [markdown]
# ## Enrichers
#
# Enrichers create additional derived artifacts that are useful for analysis and navigation.
#
# Current enrichers include:
#
# - stats-based keyword extraction
# - a wiki-bundle stub

# %%
enrichers

# %% [markdown]
# ## A note on chunking and search
#
# Canonical extraction segments are not the same thing as retrieval chunks.
#
#
# Extraction produces canonical text and provenance.
#
# Search and embeddings may later derive their own chunks from preferred text using strategies such as:
#
# - paragraph chunking
# - overlapping windows
#
# This allows retrieval behavior to evolve without rerunning extraction.

# %% [markdown]
# ## What comes next
#
# The next notebook will build an OSII store from a real data root and inspect the resulting backend structure.
#
# That notebook will demonstrate:
#
# - creating the OSII database
# - inspecting root, folders, and objects
# - looking at canonical extraction artifacts

