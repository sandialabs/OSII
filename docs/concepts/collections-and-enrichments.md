# Collections and enrichments

A collection is a deliberate, reusable OSII scope. It is not another copy of a folder or its originals. Instead, it records stable OSII document identities, so the same related documents can be used together for an enrichment, a table, Search, Chat, a synthesis, or a sidecar-package export.

## A collection is more flexible than a folder

A folder is often a useful starting point: *the documents for Project Aurora* might arrive together under one folder. But a collection can also represent an intentional selection that the file tree cannot express:

- files selected from several folders;
- a one-off upload set;
- the whole configured source root at a particular Intake; or
- documents added later because they belong to the same question.

OSII stores collection membership by document identity. Moving an original file does not make its collection membership disappear; source-path rescan keeps OSII's source awareness current. Collections do not copy original files.

## Create one during Intake

On the **Intake** page, set the document scope first. Then select **Create a logical collection from this Intake** and give it a meaningful name. When the scope is a selected folder, OSII suggests that folder's name, but you can change it.

The collection is created when the run is queued. Each document is added as it finishes processing. This means an interrupted run, a paused run, or an individual processing error cannot leave a collection claiming documents that OSII did not successfully prepare. You can add or remove members later from the collection page.

## Collections make enrichments useful together

An enrichment creates a derived artifact from a scope. An object enrichment answers a question about one document; a folder, root, or collection enrichment can answer it across many documents. Tables are especially useful at that broader scope: each row can represent an object, a document section, or another discovered record, while every row can retain its source-file provenance.

Use a collection when the meaningful set of documents is defined by purpose rather than directory layout. For example, create a `Supplier contracts — renewal review` collection from contracts in Legal, invoices in Finance, and uploaded correspondence; then run a collection enrichment to produce a sortable renewal table.

In the dashboard table view, `Source File` is hidden at first to keep broad tables compact. It is always available from **Columns**, and copied CSV includes whichever columns are currently visible.
