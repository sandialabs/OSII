import { Tab, Tabs } from "@mui/material";
export type IntakeSection = "add" | "process" | "activity";
export function IntakeSections({ value, onChange }: { value: IntakeSection; onChange: (value: IntakeSection) => void }) {
  return <Tabs value={value} onChange={(_, next: IntakeSection) => onChange(next)} variant="scrollable" allowScrollButtonsMobile aria-label="Intake sections"><Tab value="add" label="Add files" /><Tab value="process" label="Process library" /><Tab value="activity" label="Activity" /></Tabs>;
}
