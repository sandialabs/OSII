# OSII documentation

OSII turns documents and datasets into a library you can browse, search,
enrich, and ask questions about. Originals stay unchanged, and results retain
links to their evidence.

## Get started

1. [Start OSII](operations/runbook-development.md).
2. Open **Setup** to check document readers and connect any models you want to use.
3. In **Intake**, select files, choose processing, test the selected endpoints,
   and queue the work. Choose text-only processing to work without a model.
4. Browse **Files**, search the library, or group documents in **Collections**.

Use the [single-file tutorial](tutorials/single-file.md) for a small CLI example.
The [Python notebooks](tutorials/python-demonstrations.md) are a separate optional
download.

## Find a guide

| You want to… | Read… |
| --- | --- |
| Understand the data and component boundaries | [Architecture](concepts/architecture.md) |
| Configure chat, embeddings, or reranking | [Model endpoints](operations/model-endpoints.md) |
| Inspect extraction versions and OCR | [Extraction versions](reference/extraction-versions.md) |
| Generate a cited wiki | [Wiki tutorial](tutorials/llm-wiki.md) |
| Add a processor | [Extend OSII](extending/index.md) |
| Add a dashboard workflow | [Frontend extensions](extending/frontend-tools.md) |
| Call Core from another application | [REST API](reference/api/index.md) |
| Contribute a change | [Contributor guide](contributing/developer-guide.md) |

For large folders or network shares, use the [inventory guide](operations/large-volumes.md)
and [shared-drive setup](operations/shared-drives.md). Keep runtime databases on local disk.
