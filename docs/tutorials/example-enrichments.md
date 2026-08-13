# Example keyword and entity enrichments

OSII includes two small, dependency-free enrichment examples that demonstrate
the standard table and entity-list artifact formats. They work on one document
or an aggregate scope such as a collection and require no model service.

Open a document's **Enrichments** tab or the **Derived artifacts** section of a
collection, then select one of the example actions. Results appear in the same
view when the background job finishes.

At root and collection scope, the same keyword artifact supplies the compact
suggestion chips in Search, Chat, collection pages, and **Home → Library
Insights**. If the snapshot does not exist, those views offer an explicit
**Generate keyword snapshot** action. OSII does not generate it automatically
or implement a second transient keyword algorithm in the dashboard.

## Noun/adjective phrase keywords

**Generate Keyword Snapshot** produces the top 20 frequency-ranked 2-, 3-, and
4-grams after:

1. splitting English text into sentence-like units;
2. removing function words and common verbs;
3. retaining words classified as nouns or adjectives by OSII's compact local
   morphology rules;
4. reducing regular plural nouns and comparative/superlative adjectives to a
   lemma; and
5. counting each consecutive 2-, 3-, and 4-token sequence without joining
   across a rejected verb or function word.

The table contains rank, phrase, n-gram size, total frequency, and collection
document frequency. Row provenance identifies every source document in which
the phrase occurred.

This intentionally lightweight English ruleset is not a statistical POS model.
Its method is recorded as `osii-local-english-morphology-v1`, so a team can
compare or replace it with a domain NLP Processor without changing the artifact
consumer. It avoids an implicit spaCy/NLTK model download in the guaranteed
local profile.

Despite that deliberately compact implementation, multiword noun/adjective
frequency is often an unusually effective overview of messy corpora: repeated
phrases preserve more subject context than isolated high-frequency words. A
suggestion chip always launches ordinary scope-aware hybrid search, so the
user can inspect the grounded evidence rather than treating the ranking as a
summary claim.

## Named entity candidates

**Generate Entity List** finds repeated capitalized phrases, multiword names,
and acronyms. It emits the standard `entity_list` format with:

- stable entity IDs;
- conservative candidate types;
- capitalization aliases;
- total and document frequency; and
- grounded file IDs and character offsets for up to 25 mentions per entity.

The output deliberately says *candidate*: capitalization alone cannot reliably
distinguish people, organizations, places, and sentence-initial words. A domain
enricher or model-backed NER processor can later produce a higher-confidence
entity list using the same standard format and dashboard view.

## Stable artifact paths

For an object, the examples are stored at:

```text
objects/<file-id>/enrichments/keywords--noun_adjective_ngrams.json
objects/<file-id>/enrichments/entities--entity_candidates.json
```

Collection artifacts use the same filenames beneath
`collections/<collection-id>/enrichments/`. Metadata sits beside each payload
in a `.meta.json` file.

Root artifacts use:

```text
enrichments/keywords--noun_adjective_ngrams.json
enrichments/entities--entity_candidates.json
```

The collapsed Library Insights view renders all standard root artifacts using
the same generic table, entity-list, knowledge-graph, and wiki-Markdown views.
OSII does not yet generate a knowledge graph itself, and embedding-space
projection is intentionally deferred until there is a standard projection
artifact plus explicit computation and cache semantics.
