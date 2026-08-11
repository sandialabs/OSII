# Example keyword and entity enrichments

OSII includes two small, dependency-free enrichment examples that demonstrate
the standard table and entity-list artifact formats. They work on one document
or an aggregate scope such as a collection and require no model service.

Open a document's **Enrichments** tab or the **Derived artifacts** section of a
collection, then select one of the example actions. Results appear in the same
view when the background job finishes.

## Noun/adjective phrase keywords

**Generate Keyword Snapshot** produces the top 20 frequency-ranked 2-, 3-, and
4-grams after:

1. splitting English text into sentence-like units;
2. removing function words and common verbs;
3. retaining words classified as nouns or adjectives by OSII's compact local
   morphology rules;
4. reducing regular plural nouns and comparative/superlative adjectives to a
   lemma; and
5. counting each 2-, 3-, and 4-token sequence.

The table contains rank, phrase, n-gram size, total frequency, and collection
document frequency. Row provenance identifies every source document in which
the phrase occurred.

This intentionally lightweight English ruleset is not a statistical POS model.
Its method is recorded as `osii-local-english-morphology-v1`, so a team can
compare or replace it with a domain NLP Processor without changing the artifact
consumer. It avoids an implicit spaCy/NLTK model download in the guaranteed
local profile.

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
