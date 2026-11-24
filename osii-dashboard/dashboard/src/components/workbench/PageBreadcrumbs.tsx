import { Breadcrumbs, Link, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

export function PageBreadcrumbs({ parents, current }: {
  parents: readonly { label: string; to: string }[];
  current: string;
}) {
  return (
    <Breadcrumbs aria-label="Breadcrumbs" separator="›"
      sx={{ "& .MuiBreadcrumbs-li": { minWidth: 0, overflowWrap: "anywhere" } }}>
      {parents.map(({ label, to }) => (
        <Link component={RouterLink} key={to} to={to} variant="body2" underline="hover">{label}</Link>
      ))}
      <Typography component="span" variant="body2" color="text.secondary" aria-current="page">{current}</Typography>
    </Breadcrumbs>
  );
}
