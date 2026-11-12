### PR #TBD - 2026-07-31
- Fix PPTX directory processing and make configuration fallback behavior consistent.
- Correct multi-page bbox JSON and byte-return serialization; align output backends with the common save interface.

### PR #TBD - 2026-11-06
- Add an opt-in OSII processor module with bounded document bytes and Nemotron bounding-box provenance.
- Configure endpoint credentials locally and isolate temporary request files, with offline API tests.

### PR #TBD - 2026-05-07
- Implement recursive directory crawling for input files.
- Add --file_extensions CLI argument for custom file filtering.
- Refactor file gathering logic into a dedicated utils module.
