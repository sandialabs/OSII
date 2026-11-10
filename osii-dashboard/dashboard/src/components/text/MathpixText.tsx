import { useEffect, useState } from "react";
import { Alert, Box, Button, ButtonGroup, Stack } from "@mui/material";
import DOMPurify from "dompurify";
import { renderMathpix } from "./mathpixRenderer";

/** One local renderer for extracted and derived text; the source stays unchanged. */
export function MathpixText({
  text,
  controls = true,
  mode,
}: {
  text: string;
  controls?: boolean;
  mode?: "rendered" | "plain";
}) {
  const [view, setView] = useState<"rendered" | "plain">("rendered");
  const [page, setPage] = useState(0);
  const pageSize = 40_000;
  const count = Math.max(1, Math.ceil(text.length / pageSize));
  const currentPage = Math.min(page, count - 1);
  const visibleText = text.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );
  useEffect(() => setPage(0), [text]);
  const [html, setHtml] = useState("");
  const [error, setError] = useState(false);
  const selected = mode ?? view;
  useEffect(() => {
    const controller = new AbortController();
    if (selected !== "rendered") return;
    setHtml("");
    setError(false);
    void renderMathpix(visibleText, controller.signal)
      .then((rendered) => {
        if (controller.signal.aborted) return;
        const clean = DOMPurify.sanitize(rendered, {
          ADD_TAGS: ["mjx-container"],
          FORBID_TAGS: [
            "script",
            "iframe",
            "object",
            "embed",
            "form",
            "input",
            "button",
            "link",
            "meta",
            "base",
          ],
          FORBID_ATTR: ["style"],
        });
        setHtml(clean);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [visibleText, selected]);
  return (
    <Stack spacing={1} sx={{ minWidth: 0 }}>
      {controls ? (
        <ButtonGroup size="small" aria-label="Text format">
          <Button
            variant={selected === "rendered" ? "contained" : "outlined"}
            onClick={() => setView("rendered")}
          >
            Mathpix Markdown
          </Button>
          <Button
            variant={selected === "plain" ? "contained" : "outlined"}
            onClick={() => setView("plain")}
          >
            Plain text
          </Button>
        </ButtonGroup>
      ) : null}
      {count > 1 ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Button
            size="small"
            disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}
          >
            Previous section
          </Button>
          <Box>
            Section {currentPage + 1} / {count}
          </Box>
          <Button
            size="small"
            disabled={currentPage + 1 === count}
            onClick={() => setPage(currentPage + 1)}
          >
            Next section
          </Button>
        </Stack>
      ) : null}
      {error ? (
        <Alert severity="info">
          Markup could not be rendered. The original text is shown.
        </Alert>
      ) : null}
      {selected === "plain" || error || !html ? (
        <Box
          component="pre"
          sx={{
            m: 0,
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            font: "inherit",
          }}
        >
          {visibleText}
        </Box>
      ) : (
        <Box
          className="mathpix-content"
          sx={{
            overflowWrap: "anywhere",
            "& svg": { maxWidth: "100%" },
            "& img": { maxWidth: "100%" },
            "& mjx-container": { overflowX: "auto", maxWidth: "100%" },
            "& table": { borderCollapse: "collapse", maxWidth: "100%" },
            "& td, & th": {
              border: "1px solid",
              borderColor: "divider",
              p: 0.75,
            },
            "& pre": { overflowX: "auto" },
            "& p": { whiteSpace: "normal" },
          }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </Stack>
  );
}
