import assert from "node:assert/strict";
import test from "node:test";
import { libraryWorkflowSteps } from "../src/domain/workflow.ts";

const ready = () => ({
  defaults: { extractor: "local.native-text", embedder: "openai.embedder" },
  source: { ready_for_intake: true },
  extractors: [{ id: "local.native-text", available: true }],
  embedders: [{ id: "openai.embedder", available: true, dimensions: 3 }],
  language_model: { available: true, model: "chat-model" },
});
const overview = () => ({
  file_count: 3,
  processing: {
    text_count: 3,
    indexed_count: 3,
    semantic_index: { status: "ready", dimensions: 3 },
  },
});

test("model setup alone is not completed intake", () => {
  const steps = libraryWorkflowSteps(ready());
  assert.equal(steps.filter((step) => step.complete).length, 4);
  assert.equal(steps.find((step) => !step.complete).id, "text");
});

test("an empty collection and partial or invalid index never finish the journey", () => {
  const empty = overview();
  empty.file_count = 0;
  empty.processing.text_count = 0;
  empty.processing.indexed_count = 0;
  assert.equal(
    libraryWorkflowSteps(ready(), empty).filter((step) => step.complete).length,
    4,
  );
  const partial = overview();
  partial.processing.indexed_count = 2;
  assert.equal(libraryWorkflowSteps(ready(), partial).at(-1).complete, false);
  const invalid = overview();
  invalid.processing.semantic_index.status = "invalid";
  assert.equal(libraryWorkflowSteps(ready(), invalid).at(-1).complete, false);
});

test("lexical hashing is not accepted as a semantic embedding model", () => {
  const lexical = ready();
  lexical.defaults.embedder = "local.hashing";
  lexical.embedders = [{ id: "local.hashing", available: true }];
  assert.equal(
    libraryWorkflowSteps(lexical, overview()).find(
      (step) => step.id === "embedding",
    ).complete,
    false,
  );
});

test("all six checkpoints require reachable models, readable text and matching index dimensions", () => {
  assert.equal(
    libraryWorkflowSteps(ready(), overview()).every((step) => step.complete),
    true,
  );
  const noChat = ready();
  noChat.language_model.available = false;
  assert.equal(
    libraryWorkflowSteps(noChat, overview()).find(
      (step) => step.id === "language",
    ).complete,
    false,
  );
  const differentDimensions = overview();
  differentDimensions.processing.semantic_index.dimensions = 5;
  assert.equal(
    libraryWorkflowSteps(ready(), differentDimensions).at(-1).complete,
    false,
  );
  assert.equal(
    libraryWorkflowSteps(ready(), overview(), false)[0].complete,
    false,
  );
});

// Source references may provide regions, only a page/text span, or no location.
import { pageBoundingRegions } from "../src/domain/textGrounding.ts";

test("source regions preserve optional geometry and confidence by page", () => {
  const segments = [
    { id: "words", source_origin: { page: 2, coordinate_space: "normalized-page", regions: [{ text: "Word", bbox: [0.1, 0.2, 0.4, 0.3], confidence: 0.91 }] } },
    { id: "page-only", source_origin: { page: 2 } },
    { id: "unlocated", source_origin: {} },
  ];
  assert.equal(pageBoundingRegions(segments, 1).length, 0);
  assert.deepEqual(pageBoundingRegions(segments, 2), [{ text: "Word", bbox: [0.1, 0.2, 0.4, 0.3], confidence: 0.91 }]);
});

test("pixel source coordinates require dimensions and invalid boxes are ignored", () => {
  const origin = { page: 1, coordinate_space: "page-pixels", page_width: 1000, page_height: 2000 };
  assert.deepEqual(pageBoundingRegions([{ source_origin: { ...origin, bbox: [100, 200, 400, 600] } }], 1)[0].bbox, [0.1, 0.1, 0.4, 0.3]);
  assert.equal(pageBoundingRegions([{ source_origin: { page: 1, bbox: [0.8, 0.2, 0.1, 0.3] } }], 1).length, 0);
  assert.equal(pageBoundingRegions([{ source_origin: { page: 1, coordinate_space: "pdf-points", bbox: [1, 2, 4, 5] } }], 1).length, 0);
});
