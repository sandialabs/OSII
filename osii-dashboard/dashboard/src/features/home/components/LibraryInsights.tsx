import { useState } from "react";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import InsightsOutlinedIcon from "@mui/icons-material/InsightsOutlined";
import { Button, Card, CardContent, Chip, Collapse, Stack, Tab, Tabs, Typography } from "@mui/material";

import { useScopeKeywordSuggestions } from "../../../hooks/useScopeKeywordSuggestions";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";
import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";

const ROOT_SCOPE = { scope_type: "root" as const };

export function LibraryInsights() {
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<"wiki" | "artifacts">("wiki");
  const suggestions = useScopeKeywordSuggestions(ROOT_SCOPE);

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={1}
            justifyContent="space-between"
            alignItems={{ xs: "flex-start", sm: "center" }}
          >
            <Stack spacing={0.35}>
              <Stack direction="row" spacing={1} alignItems="center">
                <InsightsOutlinedIcon color="primary" />
                <Typography variant="h6" fontWeight={700}>Library wikis & products</Typography>
                <Chip size="small" variant="outlined" label={`${suggestions.artifactCount} saved`} />
              </Stack>

            </Stack>
            <Button
              size="small"
              variant="text"
              endIcon={<ExpandMoreOutlinedIcon sx={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "Collapse" : "Open"}
            </Button>
          </Stack>

          <Collapse in={expanded} unmountOnExit>
            <Stack spacing={2} sx={{ pt: 0.5 }}>
              <Tabs value={tab} onChange={(_, value: "wiki" | "artifacts") => setTab(value)}>
                <Tab label="Wiki" value="wiki" />
                <Tab label="Products" value="artifacts" />
              </Tabs>
              {tab === "wiki" ? <ScopeWikiPanel scope={ROOT_SCOPE} title="OSII Library" /> : null}
              {tab === "artifacts" ? <ScopeEnrichmentsPanel scope={ROOT_SCOPE} /> : null}
            </Stack>
          </Collapse>
        </Stack>
      </CardContent>
    </Card>
  );
}
