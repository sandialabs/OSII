import assert from "node:assert/strict";
import test from "node:test";
import { libraryWorkflowSteps, queuePollInterval } from "../src/domain/workflow.ts";

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


test("queue polling is slow when idle and fast through active transitions", () => {
  assert.equal(queuePollInterval(), 30_000);
  assert.equal(queuePollInterval([]), 30_000);
  assert.equal(queuePollInterval([{status: "completed"}, {status: "error"}, {status: "paused"}]), 30_000);
  for (const status of ["queued", "pending", "running", "pausing", "cancelling"]) {
    assert.equal(queuePollInterval([{status: "completed"}, {status}]), 3000);
  }
});


test("connection labels identify the service, independently of model names", async () => {
  const {suggestedConnectionName, sameEndpoint} = await import("../src/features/models/connectionName.ts");
  assert.equal(suggestedConnectionName("https://api.company.example/v1"), "Company");
  assert.equal(suggestedConnectionName("http://localhost:11434"), "Local models");
  assert.equal(suggestedConnectionName(""), "Connection");
  assert.ok(sameEndpoint("https://EXAMPLE.com/v1/", "https://example.com/v1"));
  assert.ok(!sameEndpoint("https://example.com/v1", "https://example.com/v2"));
  assert.ok(!sameEndpoint("", ""));
});


test("endpoint name suggestions work for arbitrary hosts and IP addresses", async () => {
  const {suggestedConnectionName} = await import("../src/features/models/connectionName.ts");
  assert.equal(suggestedConnectionName("https://openrouter.ai/api/v1"), "Openrouter");
  assert.equal(suggestedConnectionName("https://www.api.invented.example/v1"), "Invented");
  assert.equal(suggestedConnectionName("http://192.168.1.150:8080/v1"), "Model server");
});

test("flow reports distinguish fatal errors from successful fallback recovery", async () => {
  const {flowTestStatus, flowTestError, flowStepLabel} = await import("../src/domain/processingFlowTests.ts");
  const failed = {processor: "reader-a", ok: false, diagnostics: {error: "No text returned"}};
  const recovered = {step: "extract", ok: true, attempts: [failed, {processor: "reader-b", ok: true}]};
  const report = {ok: true, tested_at: "2026-11-19T00:00:00Z", results: [recovered]};
  assert.equal(flowTestStatus(report).label, "Ready · fallback used");
  const workingPrimary = {...recovered, attempts: [{processor: "reader-a", ok: true}, failed]};
  assert.equal(flowTestStatus({...report, results: [workingPrimary]}).label, "Ready · backup reader failed");
  assert.equal(flowTestStatus({...report, ok: false}).label, "Needs attention");
  assert.equal(flowTestStatus({...report, results: [{ok: true}]}).label, "Ready");
  assert.equal(flowTestStatus(null).label, "Not tested");
  assert.equal(flowTestError(failed), "No text returned");
  assert.equal(flowTestError({ok: false, diagnostics: {error: 'processor failed: HTTP 500: {"detail":{"error":"No module named fastapi","traceback":"long trace"}}'}}), "No module named fastapi");
  assert.match(flowTestError({ok: null}), /No compatible sample/);
  assert.equal(flowStepLabel({step: "synthesize", processor: "custom-wiki", ok: false}), "Generate summaries");
  assert.equal(flowStepLabel({step: "enrich", processor: "custom", ok: true}), "Enrich documents");
});


test("flow results put a late-stage failure ahead of successful reader checks", async () => {
  const {flowTestEntries} = await import("../src/domain/processingFlowTests.ts");
  const entries = flowTestEntries({ok: false, tested_at: "now", results: [
    {ok: true, step: "extract"}, {ok: true, attempts: [{ok: false}, {ok: true}]}, {ok: false, step: "embed"},
  ]});
  assert.deepEqual(entries.map(entry => entry.index), [2, 1, 0]);
  assert.deepEqual(entries.map(entry => entry.attention), [true, true, false]);
});


test("endpoint grouping keeps model aliases and distinct credentials intact", async () => {
  const {groupModelConnections} = await import("../src/features/models/connectionName.ts");
  const writing = {id: "base", type: "ollama", base_url: "http://localhost:11434/", credential_env: "", chat_model: "writer"};
  const embedding = {id: "minilm", type: "ollama", base_url: "http://localhost:11434", credential_env: "", embedding_model: "embedder"};
  const separate = {...writing, id: "private", credential_env: "OTHER_KEY"};
  const groups = groupModelConnections([writing, embedding, separate]);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].members.map(member => member.id), ["base", "minilm"]);
  assert.equal(groups[0].primary.id, "base");
  assert.equal(groups[0].name, "Local models");
  assert.equal(groups[0].members[1], embedding);
  assert.equal(embedding.embedding_model, "embedder");
  assert.equal(groupModelConnections([{...writing, display_name: "My service"}])[0].name, "My service");
});


test("legacy generated service-plus-model labels no longer identify the connection by one model", async () => {
  const {connectionDisplayName} = await import("../src/features/models/connectionName.ts");
  const connection = {id:"stable-alias", type:"openai", base_url:"https://api.company.example/v1", credential_env:"CORP_KEY", chat_model:"vendor/gpt-example", display_name:"Company - GPT Example"};
  assert.equal(connectionDisplayName(connection), "Company");
  assert.equal(connectionDisplayName({...connection, display_name:"Research service"}), "Research service");
  assert.equal(connection.id, "stable-alias");
});
