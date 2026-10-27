export function syncAction(local: string, cloud: string | null, base: string | null, localEmpty: boolean) {
  if (cloud === null) return "push";
  if (local === cloud) return "same";
  if (base === cloud) return "push";
  if (base === local || (base === null && localEmpty)) return "pull";
  return "conflict";
}

export function stableJSON(value: unknown): string {
  return JSON.stringify(value, (_, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
}
