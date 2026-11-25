import { useEffect } from "react";
import { Alert, LinearProgress, Stack, Typography } from "@mui/material";
import { useParams } from "react-router-dom";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";
import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { useCollection } from "../../../hooks/useCollections";
import { buildCollectionRoute } from "../../../utils/routes";
import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";

export function CollectionWikisPage() {
  const { collectionId = "" } = useParams();
  const collection = useCollection(collectionId, Boolean(collectionId));
  const { setCollectionScope } = useBrowsingScope();
  const record = collection.data?.collection;

  useEffect(() => {
    if (record) setCollectionScope(record.id, record.name);
  }, [record, setCollectionScope]);

  return (
    <Stack spacing={2}>
      <PageBreadcrumbs parents={[
        { label: "Collections", to: "/collections" },
        { label: record?.name ?? "Collection", to: buildCollectionRoute(collectionId) },
      ]} current="Wikis" />
      <Typography component="h1" variant="h5" fontWeight={750}>Wikis</Typography>
      {collection.isLoading ? <LinearProgress aria-label="Loading collection" />
        : collection.isError ? <Alert severity="error">Could not load collection. {collection.error.message}</Alert>
        : record ? <ScopeWikiPanel scope={{ scope_type: "collection", collection_id: collectionId }} title={record.name} />
        : <Alert severity="info">Collection not found.</Alert>}
    </Stack>
  );
}
