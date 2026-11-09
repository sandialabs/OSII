import { useState, type ReactNode } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Typography } from "@mui/material";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";

/** Compact scope panels remember each user's choice on this browser. */
export function ScopeSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const key = `osii:scope-section:${id}`;
  const [open, setOpen] = useState(() => localStorage.getItem(key) === "open");
  return <Accordion expanded={open} onChange={(_, value) => { setOpen(value); localStorage.setItem(key, value ? "open" : "closed"); }} variant="outlined" disableGutters slotProps={{ transition: { unmountOnExit: true } }} sx={{ "&:before": { display: "none" } }}>
    <AccordionSummary expandIcon={<ExpandMoreOutlined />}><Typography fontWeight={700}>{title}</Typography></AccordionSummary>
    <AccordionDetails>{children}</AccordionDetails>
  </Accordion>;
}
