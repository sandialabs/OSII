import { useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import { apiJson } from "../../../api/client";
import type { ScopeDescribeRequest } from "../../../api/types";
import { DerivedProductEditor } from "./DerivedProductEditor";
import { ToolActionPanel } from "./ToolActionPanel";

type Product = {
  family: "enrichment" | "synthesis";
  filename: string;
  title: string;
  artifact_type?: string;
};
export function ScopeEnrichmentsPanel({
  scope,
  showActions = true,
}: {
  scope: ScopeDescribeRequest;
  showActions?: boolean;
}) {
  const query = useQuery({
    queryKey: ["products", "list", scope],
    queryFn: () =>
      apiJson<{ products: Product[] }>("/api/products/list", {
        method: "POST",
        json: scope,
      }),
  });
  const products =
    query.data?.products.filter(
      (item) =>
        item.artifact_type !== "wiki_markdown" || item.filename.endsWith(".md"),
    ) ?? [];
  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={700}>
        Saved products
      </Typography>
      {showActions ? <ToolActionPanel scope={scope} /> : null}
      {query.isLoading ? <Typography>Loading products…</Typography> : null}
      {query.isError ? (
        <Alert severity="warning">
          Could not load products.{" "}
          <Button onClick={() => void query.refetch()}>Retry</Button>
        </Alert>
      ) : null}
      {!query.isLoading && !query.isError && !products.length ? (
        <Alert severity="info">No other saved products for this scope.</Alert>
      ) : null}
      {products.map((item) => (
        <Accordion
          key={`${item.family}:${item.filename}`}
          variant="outlined"
          disableGutters
          slotProps={{ transition: { unmountOnExit: true } }}
        >
          <AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}>
            <Typography fontWeight={650}>{item.title}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <DerivedProductEditor
              scope={scope}
              filename={item.filename}
              family={item.family}
            />
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}
