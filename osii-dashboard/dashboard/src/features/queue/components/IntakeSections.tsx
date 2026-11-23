import { Tab, Tabs } from "@mui/material";
export type IntakeSection = "add" | "activity";
export function IntakeSections({
  value,
  onChange,
  activeCount = 0,
}: {
  value: IntakeSection;
  onChange: (value: IntakeSection) => void;
  activeCount?: number;
}) {
  return (
    <Tabs
      value={value}
      onChange={(_, next: IntakeSection) => onChange(next)}
      variant="scrollable"
      allowScrollButtonsMobile
      aria-label="Intake sections"
    >
      <Tab value="add" label="Prepare files" />
      <Tab
        value="activity"
        label={`Queue & activity${activeCount ? ` (${activeCount} active)` : ""}`}
      />
    </Tabs>
  );
}
