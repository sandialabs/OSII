import { Box, Card, CardActionArea, CardContent, Typography } from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";

export function FolderTile({ name, onOpen }: { name: string; onOpen: () => void }) {
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardActionArea onClick={onOpen} aria-label={"Open folder " + name}
        sx={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-start", pt: 1.25 }}>
        <Box sx={{ height: 104, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <FolderOutlinedIcon sx={{ fontSize: 58, color: "warning.main" }} />
        </Box>
        <CardContent sx={{ width: "100%", pt: 1 }}>
          <Typography variant="subtitle2" fontWeight={600} title={name} sx={{ overflowWrap: "anywhere" }}>{name}</Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
