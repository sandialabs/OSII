// src/features/browse/components/BrowseBreadcrumbs.tsx
import { Breadcrumbs, Link, Typography } from "@mui/material";

import type { FolderScopeDescriptor } from "../../../api/types";

type BrowseBreadcrumbsProps = {
  items: FolderScopeDescriptor[];
  onNavigate: (folderId: string) => void;
};

export function BrowseBreadcrumbs({
  items,
  onNavigate,
}: BrowseBreadcrumbsProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <Breadcrumbs
      aria-label="folder breadcrumbs"
      separator="›"
      sx={{
        "& .MuiBreadcrumbs-separator": {
          color: "text.secondary",
          mx: 0.5,
        },
      }}
    >
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        const label = item.path ? item.label.split("/").slice(-1)[0] : "root";

        if (isLast) {
          return (
            <Typography
              key={item.folder_id}
              variant="body2"
              color="text.primary"
              fontWeight={600}
            >
              {label}
            </Typography>
          );
        }

        return (
          <Link
            key={item.folder_id}
            component="button"
            type="button"
            underline="hover"
            color="text.secondary"
            onClick={() => onNavigate(item.folder_id)}
            sx={{
              fontSize: "0.9rem",
              cursor: "pointer",
              background: "none",
              border: "none",
              p: 0,
            }}
          >
            {label}
          </Link>
        );
      })}
    </Breadcrumbs>
  );
}