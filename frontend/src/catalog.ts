import { parseDecimal } from "./decimal.ts";
import type { Kind } from "./model.ts";

export type Filter = {
  id: string;
  code: string;
  kind: Kind | "";
  unit: string;
  min: string;
  max: string;
  conditions: string;
};
export const emptyFilter = (): Filter => ({
  id: crypto.randomUUID(),
  code: "",
  kind: "",
  unit: "V",
  min: "",
  max: "",
  conditions: "",
});
export function serializeFilters(filters: Filter[]) {
  return filters.map((f, i) => {
    if (!f.code)
      throw new Error(
        `Выберите характеристику в фильтре ${i + 1} или удалите его.`,
      );
    const min = f.min.trim() ? parseDecimal(f.min) : null;
    const max = f.max.trim() ? parseDecimal(f.max) : null;
    if ((min != null && min < 0) || (max != null && max < 0))
      throw new Error(
        `В фильтре ${i + 1} границы должны быть неотрицательными.`,
      );
    if (min != null && max != null && min > max)
      throw new Error(
        `В фильтре ${i + 1} значение «от» не должно превышать «до».`,
      );
    return {
      code: f.code,
      kind: f.kind || null,
      unit: f.unit,
      min,
      max,
      conditions: f.conditions.trim(),
    };
  });
}
export function readColumns(value: string | null): Record<string, string[]> {
  try {
    const parsed: unknown = JSON.parse(value || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(
          ([, codes]) =>
            Array.isArray(codes) &&
            codes.every((code) => typeof code === "string"),
        )
        .map(([category, codes]) => [
          category,
          [...new Set(codes as string[])],
        ]),
    );
  } catch {
    return {};
  }
}
