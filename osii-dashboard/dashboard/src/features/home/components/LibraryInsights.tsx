import { useState } from "react";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import InsightsOutlinedIcon from "@mui/icons-material/InsightsOutlined";
import { Button, Card, CardContent, Chip, Collapse, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

import { ScopeSuggestions } from "../../../components/discovery/ScopeSuggestions";
import { useScopeKeywordSuggestions } from "../../../hooks/useScopeKeywordSuggestions";
import { ScopeEnrichmentsPanel } from "../../files/components/ScopeEnrichmentsPanel";
import { ScopeWikiPanel } from "../../files/components/ScopeWikiPanel";

const ROOT_SCOPE = { scope_type: "root" as const };

export function LibraryInsights() {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<"wiki" | "artifacts">("wiki");
  const suggestions = useScopeKeywordSuggestions(ROOT_SCOPE);

  const searchKeyword = (keyword: string) => {
    const params = new URLSearchParams({
      q: keyword,
      mode: "hybrid",
      scope_type: "root",
    });
    navigate(`/search?${params.toString()}`);
  };

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
                <Typography variant="h6" fontWeight={700}>Library Insights</Typography>
                <Chip size="small" variant="outlined" label={`${suggestions.artifactCount} artifact${suggestions.artifactCount === 1 ? "" : "s"}`} />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                Root-level knowledge products derived from all processed files. Expand only when you want to explore them.
              </Typography>
            </Stack>
            <Button
              size="small"
              variant="text"
              endIcon={<ExpandMoreOutlinedIcon sx={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "Collapse" : "Explore insights"}
            </Button>
          </Stack>

          <ScopeSuggestions scope={ROOT_SCOPE} compact onSelect={searchKeyword} />

          <Collapse in={expanded} unmountOnExit>
            <Stack spacing={2} sx={{ pt: 0.5 }}>
              <Tabs value={tab} onChange={(_, value: "wiki" | "artifacts") => setTab(value)}>
                <Tab label="Wiki" value="wiki" />
                <Tab label="Artifacts" value="artifacts" />
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
