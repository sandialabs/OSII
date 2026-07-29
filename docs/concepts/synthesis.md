# Synthesis architecture

## Purpose

This document defines the synthesis-layer architecture for `ai-ready-ingest`.

Synthesis is a post-extraction layer that reads canonical OSII bundles and produces derived, interpretable representations for users, dashboards, and downstream tools such as MCP-based agents.

The synthesis layer is responsible for:
- reading already-extracted OSII bundles
- applying one synthesis strategy at a time
- writing derived synthesis outputs
- supporting experimentation with multiple strategies
- supporting hierarchical synthesis across objects, folders, and the root scope

This is the primary document a technical contributor should read before adding a new synthesizer.

---

## Why synthesis is broader than summarization

Synthesis is intentionally broader than summary generation.

Depending on the scope and content, a synthesizer may produce:
- a concise summary
- a qualitative description
- an interpretation of related files as one logical unit
- a guide pointing the user toward the most relevant artifacts
- a structured report-like output

Examples:
- object-level recursive synthesis of a long report
- folder-level interpretation of an experiment folder containing settings and output files
- folder-level guide to a simulation result set, pointing to relevant artifacts and child objects

---

## Synthesis dimensions

Every synthesis strategy should be understood along three dimensions:

### 1. Scope
What level of the OSII hierarchy it operates on:
- `object`
- `folder`
- `root`

### 2. Mode
What kind of synthesis it performs:
- `summary`
- `description`
- `guide`
- `report`
- `interpretation`

### 3. Domain
What kind of content it is especially suited for:
- `generic`
- `experiment`
- `simulation`
- `literature`
- other project-specific domains

These dimensions are intended to guide both implementation and future UI/MCP selection logic.

---

## Package layout

```text
ai-ready-ingest/osii/synthesis/
  __init__.py
  base.py
  common.py
  registry.py
  firstN_synthesizer.py
  recursive_synthesizer.py
  folder_firstN_synthesizer.py
  folder_registry.py
  cli.py
  folder_cli.py
```

---

## Current and future synthesizer families

### Object synthesizers
Operate on one extracted object bundle.

Examples:
- `firstN`
- `recursive`

### Folder synthesizers
Operate on one folder node plus child object/folder outputs.

Examples:
- `firstN_folder`
- future recursive folder synthesis
- future simulation folder guide
- future experiment folder interpreter

### Root synthesizers
Operate at the top level.

The root may often reuse the same logic as a folder synthesizer, applied to the root folder scope.

---

## Registry model

Every synthesizer description should expose at least:
- `name`
- `display_name`
- `description`
- `version`
- `scope`
- `mode`
- `domain`

Conceptual example:

```json
{
  "name": "recursive",
  "display_name": "Recursive Synthesizer",
  "description": "Recursively synthesizes extracted text by chunking and combining.",
  "version": "1.0",
  "scope": "object",
  "mode": "summary",
  "domain": "generic"
}
```

Folder-level example:

```json
{
  "name": "simulation_folder_guide",
  "display_name": "Simulation Folder Guide",
  "description": "Produces a qualitative interpretation of a simulation folder and points to relevant artifacts and child objects.",
  "version": "1.0",
  "scope": "folder",
  "mode": "guide",
  "domain": "simulation"
}
```

This metadata is intended to help dashboards and MCP tools choose the right strategy for a given scope and content type.

---

## Hierarchical synthesis

Synthesis should support three scopes:

### Object-level synthesis
Input:
- one extracted OSII object bundle

Output:
- `objects/<file_id>/synth.txt`

### Folder-level synthesis
Input:
- one folder node
- child object syntheses
- child folder syntheses
- or fallback extracted text if synthesis is missing

Output:
- `folders/folder-<folder_id>.synth.txt`

### Root-level synthesis
Input:
- the root folder scope

Output:
- `root.synth.txt`

This hierarchy supports intelligent top-down traversal by MCP tools.

---

## How synthesizers should read input

### Object-level
Typical flow:
1. list records in `manifest.jsonl`
2. filter to `kind == "text"`
3. resolve corresponding files in `segments/`
4. concatenate, clean, or otherwise transform the text
5. write derived synthesis output

### Folder-level
Typical flow:
1. read the folder manifest
2. gather child folder syntheses if present
3. gather child object syntheses if present
4. fall back to child extracted text when needed
5. synthesize a folder-level interpretation, guide, or summary
6. write derived folder synthesis output

This allows synthesis to be built bottom-up across the hierarchy.

---

## How to add a new synthesizer

### Step 1: define the strategy along the three dimensions
Before writing code, decide:
- scope: object / folder / root
- mode: summary / description / guide / report / interpretation
- domain: generic / experiment / simulation / literature / etc.

### Step 2: define what inputs it should actually use
Examples:
- object text only
- child folder syntheses
- child object syntheses
- artifact metadata
- file names and provenance

### Step 3: implement the synthesizer class
Create a new file under `ai-ready-ingest/osii/synthesis/`.

### Step 4: expose a good description
Every synthesizer should define:
- `display_name`
- `description`
- and the registry metadata: `scope`, `mode`, `domain`

### Step 5: register it
Add it to the appropriate registry.

### Step 6: test it standalone
Use the object or folder synthesis CLI as appropriate.

---

## Current examples

### `firstN`
- scope: object
- mode: summary
- domain: generic

### `recursive`
- scope: object
- mode: summary
- domain: generic

### `firstN_folder`
- scope: folder
- mode: summary
- domain: generic

These are baseline strategies, not the full set of synthesis types the architecture is intended to support.

---

## Expert context

Synthesizers may accept optional free-text expert guidance.

This guidance can help shape:
- what to emphasize
- what to downplay
- preferred structure or level of detail
- how to interpret grouped extracted inputs

Examples:
- "Focus on experimental setup, assumptions, and final conclusions."
- "Emphasize calibration issues and uncertainty statements."
- "Interpret these input/output files together as one experiment."

Requirements:
- expert context is optional
- lack of expert context must not block synthesis
- if expert context influences prompt-driven synthesis, run metadata should record that it was used
