import { useMutation, useQueryClient } from "@tanstack/react-query";
import { importOsiiPackage } from "../api/packages";

export function usePackageImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: importOsiiPackage,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["collections"] });
      void client.invalidateQueries({ queryKey: ["objects"] });
      void client.invalidateQueries({ queryKey: ["folders"] });
    },
  });
}
