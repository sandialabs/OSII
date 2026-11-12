import { Button, Chip, Stack, Typography } from "@mui/material";
import type { ManagedCapabilityService } from "../../../api/types";

function statusColor(status: string): "success" | "default" | "error" | "info" {
  if (status === "running" || status === "external") return "success";
  if (status === "failed" || status === "unhealthy") return "error";
  if (status === "starting") return "info";
  return "default";
}


export function ServiceRow({ service, busy, onAction, onLogs }: {
  service: ManagedCapabilityService;
  busy: boolean;
  onAction: (action: "start" | "stop" | "restart") => void;
  onLogs?: () => void;
}) {
  const label = service.status === "external" ? "Running externally" : service.status.replace(/_/g, " ");
  return <Stack spacing={0.75} sx={{ py: 0.75 }}>
    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
      <Stack spacing={0.25}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="body2" fontWeight={700}>{service.display_name}</Typography>
          <Chip size="small" color={statusColor(service.status)} label={label} />
        </Stack>
        <Typography variant="caption" color="text.secondary">{service.description}</Typography>
        {service.prerequisite ? <Typography variant="caption" color="text.secondary">{service.prerequisite}</Typography> : null}
      </Stack>
      <Stack direction="row" spacing={0.75} alignItems="center">
        {service.can_start ? <Button size="small" variant="contained" disabled={busy} onClick={() => onAction("start")}>Start</Button> : null}
        {service.can_restart ? <Button size="small" variant="outlined" disabled={busy} onClick={() => onAction("restart")}>Restart</Button> : null}
        {service.can_stop ? <Button size="small" variant="text" disabled={busy} onClick={() => onAction("stop")}>Stop</Button> : null}
        {onLogs ? <Button size="small" variant="text" onClick={onLogs}>Logs</Button> : null}
      </Stack>
    </Stack>
  </Stack>;
}

