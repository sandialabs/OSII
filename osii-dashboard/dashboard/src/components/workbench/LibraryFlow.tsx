import { InputOutlined, OutputOutlined } from "@mui/icons-material";
import { Stack, Typography } from "@mui/material";
import { libraryProducts, type LibraryFlow as Flow } from "../../domain/libraryProducts";

export function LibraryFlow({ reads, writes }: Flow) {
  return (
    <Stack spacing={0.5} aria-label="Library inputs and outputs">
      {([["Reads", reads, OutputOutlined], ["Writes", writes, InputOutlined]] as const).map(([label, products, Icon]) => products.length ? (
        <Stack key={label} direction="row" alignItems="flex-start" spacing={0.75}>
          <Icon sx={{ fontSize: 15, mt: "2px", color: label === "Writes" ? "primary.main" : "text.secondary" }} />
          <Typography variant="caption" color="text.secondary">
            <strong>{label}</strong> {products.map(product => libraryProducts[product]).join(" · ")}
          </Typography>
        </Stack>
      ) : null)}
    </Stack>
  );
}
