// src/features/folders/pages/FoldersPage.tsx
import { useMemo, useState } from "react";
import {
  Alert,
  Card,
  CardContent,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listFolderScopes } from "../../../api/scopes";
import { buildFolderRoute } from "../../../utils/routes";
import { useBrowsingScope } from "../../../app/providers/BrowsingScopeProvider";

export function FoldersPage() {
  const navigate = useNavigate();
  const { setFolderScope } = useBrowsingScope();
  const [filter, setFilter] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["scopes", "folders"],
    queryFn: listFolderScopes,
  });

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) {
      return data?.scopes ?? [];
    }

    return (data?.scopes ?? []).filter((scope) => {
      return (
        scope.label.toLowerCase().includes(needle) ||
        scope.path.toLowerCase().includes(needle) ||
        scope.folder_id.toLowerCase().includes(needle)
      );
    });
  }, [data?.scopes, filter]);

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>
          Folder Scopes
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browse structural folder scopes discovered from the source hierarchy.
        </Typography>
      </Stack>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <TextField
              fullWidth
              label="Filter folders"
              placeholder="Filter by label, path, or folder ID"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />

            {isLoading ? (
              <Stack direction="row" spacing={2} alignItems="center">
                <CircularProgress size={24} />
                <Typography>Loading folder scopes…</Typography>
              </Stack>
            ) : isError ? (
              <Alert severity="error">
                Failed to load folder scopes.
                {error instanceof Error ? ` ${error.message}` : ""}
              </Alert>
            ) : filtered.length === 0 ? (
              <Typography color="text.secondary">No folder scopes found.</Typography>
            ) : (
              <List dense disablePadding>
                {filtered.map((scope) => (
                  <ListItemButton
                    key={scope.folder_id}
                    onClick={() => {
                      setFolderScope(scope);
                      navigate(buildFolderRoute(scope.folder_id));
                    }}
                  >
                    <ListItemText
                      primary={scope.label}
                      secondary={scope.path || "root"}
                    />
                  </ListItemButton>
                ))}
              </List>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}