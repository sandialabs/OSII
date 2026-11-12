import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, Box, Typography } from "@mui/material";

/** A source deep-link verifies the extracted text, including older representations. */
export function ReportPassage({ text, loading = false }: { text: string; loading?: boolean }) {
  const [params] = useSearchParams();
  const expected = params.get("text_sha256");
  const [matches, setMatches] = useState<boolean | null>(null);
  useEffect(() => {
    let current = true;
    setMatches(null);
    if (!expected || loading || !crypto.subtle) return;
    void crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(hash => {
      const actual = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
      if (current) setMatches(actual === expected);
    }).catch(() => {});
    return () => { current = false; };
  }, [text, expected, loading]);
  if (!params.has("report_source")) return null;
  const start = Number(params.get("char_start")), end = Number(params.get("char_end"));
  const excerpt = Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start
    ? Array.from(text).slice(start, Math.min(end, start + 1400)).join("") : "";
  return <Alert severity={matches === false ? "warning" : matches ? "success" : "info"}>
    <Typography variant="subtitle2">Cited passage · {params.get("report_source")}</Typography>
    {loading ? "Loading the cited extraction…" : <>
      {matches === false ? "This extraction differs from the report’s saved evidence. Compare with the exact excerpt kept in the report."
        : matches ? "Source text matches the report’s evidence fingerprint." : "Compare this passage with the claim in the report."}
      <Box component="blockquote" sx={{ m: 0, mt: 1, whiteSpace: "pre-wrap", maxHeight: 260, overflow: "auto" }}>{excerpt}</Box>
    </>}
  </Alert>;
}
