# Suggested collections

Both OSII-local and OSII-server can propose a few related groups of documents.
Suggestions are working hypotheses for organizing a library. They do not claim
that the documents form an authoritative taxonomy, or that every document belongs
in a collection.

## Using suggestions

When **Collections** is empty, it shows starter suggestions with names, reasons,
document counts, and expandable document previews. **Create collection** saves
one immediately; **Create all suggestions** saves the remaining choices in
sequence. The other suggestions stay visible after the first save for the rest
of that visit. Returning to a populated Collections page shows saved collections.

Suggestions remain available under **Toolbox → Create Collections → Suggested**.
Enter a goal in **Describe the collections you want**, then choose **Suggest with
AI**. For example: “Separate practical gardening advice, urban forest management,
and historical accounts; leave unrelated directories out.” This asks the
configured chat model for proposals. Creating those proposals is a separate action.

Names, descriptions, and document references are saved through the existing
collection APIs. Hosted collections start private. They remain editable using
the existing collection controls. Original files, extracted text, and processing
jobs are not changed by creating a collection. A partial batch preserves its
completed collections; retry in the same view creates the remaining choices.

## Automatic starter method

`osii.domain.collection_suggestions.topic_proposals` is shared, pure Python Core
logic. It takes supplied document descriptors and optional saved document vectors.
It performs no storage operations or model requests. The HTTP adapter is
`osii.api.collection_suggestion_routes`; shared presentation is
`CollectionSuggestions.tsx`.

The algorithm (`starter-topics-v1`) works as follows:

1. Read every available library document, following all catalog pages. Source
   PDFs and Office files are not opened. Each descriptor uses its filename,
   available suggested title, up to 1,000 characters of saved synthesis, and up
   to 1,200 characters of saved text. These excerpts are inputs to a starter
   heuristic, not a complete reading of every document.
2. Where available, load compatible saved document embeddings. Chunk vectors
   are normalized, averaged per document, and normalized again using the
   existing document-space code. Stale, incompatible, invalid, or known lexical
   hashing indices do not supply semantic topics. An unavailable semantic space
   leaves saved-text suggestions available. No embeddings are generated.
3. Build a text space from weighted words and adjacent-word pairs. Saved titles
   and syntheses receive more weight than raw OCR. English stopwords, generic
   administrative/contact wording, opaque identifiers, and one-off terms are
   filtered. Simple plural normalization is a heuristic. At most 200 terms per
   document and 2,048 recurring vocabulary terms are retained; the dense matrix
   is bounded to 64 MiB. There is no 500- or 1,000-document input cutoff.
4. Cluster normalized vectors with deterministic spherical k-means. Seed count
   grows roughly with the square root of the document count, up to 12, using a
   central first seed and farthest-first subsequent seeds. There are at most 16
   iterations. Saved embeddings are used in their original space; PCA/UMAP
   screen coordinates are not used to infer topic membership.
5. Retain documents close to each cluster center. The minimum cosine score is
   0.50 for saved embeddings or 0.32 for text features, and membership is also
   trimmed relative to the cluster median. A proposal contains at most the 100
   strongest members. Weak matches can remain unassigned.
6. Name and check a topic using shared terms in saved titles or the opening
   synthesis line (a text opening when neither is available). This avoids
   turning a recurring phone number, contact name, or incidental body mention
   into the collection title. Members must match an anchor phrase or at least
   two anchor words. Normally at least four supporting documents are required;
   libraries under 12 documents may form a two-document group. Label spelling
   is preserved instead of applying plural stemming to names.
7. Prefer coherent embedding groups, supplement them with text groups, and
   suppress strongly overlapping or near-duplicate proposals. Offer up to six
   starter collections. Insufficient evidence can produce fewer or none;
   the algorithm does not force a partition of the library.

The method is deterministic for unchanged inputs. Automatic results are cached
as derived data: an existing PostgreSQL settings entry for PostgreSQL-backed
libraries, or `cache/collection-suggestions.json` for sidecars. Cache identity
includes the algorithm version, saved descriptors, and index/corpus identity.
Prompt text and AI-guided results are not written into this shared cache.

## Prompt-guided method

`guided_proposals` accepts a completion callback so Python developers can test
it without an HTTP server or a particular model SDK. It uses the existing chat
endpoint, model, and API key only after an explicit **Suggest with AI** action.
Opening Collections does not invoke a model.

Every document is considered for candidate selection. Prompt words rank relevant
saved descriptors, and topic groups contribute representatives in round-robin
order. The model receives at most 96 candidates, each with an integer ID, a
bounded title, and at most 420 characters of saved description. This is one
bounded model call with a 4,000-output-token budget. It does not send the complete
library or document bodies to the chat model. The response reports both the
library count and candidate count so this limit is visible.

The model is asked for three to six distinct, coherent groups, while being
allowed to return fewer if evidence is weak. It can name and describe a group
and choose supplied integer IDs. Core validates the JSON, names, counts, ID
types, and memberships, rejects invented/out-of-range IDs and singleton groups,
and suppresses near-duplicate proposed memberships. Document descriptions are
explicitly treated as untrusted data in the system prompt. No model response
executes a collection command. Normal API authorization and active-document
validation still apply when the user creates a proposed collection.

Hosted GET/POST routes require authentication; POST retains CSRF enforcement.
Hosted prompt generation is rate-limited per account and globally. Provider or
validation failures leave existing collections and the previous suggestions
available. A configured endpoint is checked when used, not represented as a
successful connection test merely because configuration exists.

## Limits and extension points

OCR quality, incomplete synthesis, English-oriented tokenization, broad embedding
clusters, and excerpt selection can all affect the result. Inspect previews and
edit collections as needed. Prompt descriptions may infer a theme incorrectly;
they remain AI suggestions. Rare subjects outside the bounded model candidates
may need a more specific prompt or manual selection.

A different clustering or RAG strategy can replace the pure proposal functions
while retaining the descriptor/known-ID boundary and shared UI. Keep data loading,
model credentials, authentication, and persistence in adapters. Keep suggestions
separate from the four processor kinds: this is Core collection organization,
not a new extractor, embedder, synthesizer, or enricher.
