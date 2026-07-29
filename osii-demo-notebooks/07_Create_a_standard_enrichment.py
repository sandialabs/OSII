# %% [markdown]
# # 07 — Create a standard enrichment artifact
#
# Enrichers return standard artifacts that the dashboard and agents can render.
# This bundled enricher creates a table of keywords for the whole corpus.

# %%
from osii.enrichment.stats_keywords import StatsKeywordsEnricher

from _demo_support import demo_paths

# %%
_, _, OSII_ROOT = demo_paths()
enrichment = StatsKeywordsEnricher().enrich(
    osii_store=OSII_ROOT,
    scope={"scope_type": "root"},
    enricher_config={"top_k": 10},
)
print(enrichment)

# %% [markdown]
# The returned artifact is a standard `table`. A custom external enricher can
# return the same table, a knowledge graph, an entity list, or wiki Markdown.
