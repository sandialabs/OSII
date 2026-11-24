import { Breadcrumbs, Link, Typography } from "@mui/material";
import { folderBreadcrumbs } from "../contents";

export function BrowseBreadcrumbs({ path, onNavigate }: {
  path: string;
  onNavigate: (path: string) => void;
}) {
  const items = folderBreadcrumbs(path);
  return (
    <Breadcrumbs aria-label="Folder path" separator="›" maxItems={6} itemsAfterCollapse={3}>
      {items.map((item, index) => index === items.length - 1 ? (
        <Typography key={item.path} variant="body2" fontWeight={600} aria-current="location">{item.label}</Typography>
      ) : (
        <Link key={item.path} component="button" type="button" underline="hover"
          onClick={() => onNavigate(item.path)} sx={{ fontSize: "0.875rem" }}>
          {item.label}
        </Link>
      ))}
    </Breadcrumbs>
  );
}
