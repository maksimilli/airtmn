export type Kind = "min" | "typ" | "max" | "unspecified";
export type Param = {
  code: string;
  value: number | string;
  unit: string;
  kind: Kind;
  conditions: string;
  page?: number;
  evidence: string;
  source?: "text" | "ocr" | "manual";
  confidence?: number | null;
};
export type Component = {
  id?: number;
  name: string;
  category: string;
  manufacturer: string;
  package: string;
  description: string;
  document_id?: string;
  parameters: Param[];
};
export type Category = {
  code: string;
  label: string;
  singular: string;
  group: string;
  icon: string;
  codes: string[];
  columns: string[];
  count: number;
};
export type Definition = {
  code: string;
  label: string;
  unit: string;
  display_unit: string;
  units: Record<string, number>;
};
export type Document = {
  id: string;
  filename: string;
  pages: number;
  size: number;
  components_count: number;
};
export type Stats = {
  components: number;
  documents: number;
  manufacturers: number;
  parameters: number;
};
export const kinds: Record<Kind, string> = {
  min: "Минимальное",
  typ: "Типовое",
  max: "Максимальное",
  unspecified: "Не указано",
};
const symbols: Record<string, string> = {
  IF_AV: "IF(AV)",
  RDS_ON: "RDS(on)",
  VGS_TH: "VGS(th)",
  VCE_SAT: "VCE(sat)",
};
export const symbol = (code: string) => symbols[code] || code;
export const blank = (category: string): Component => ({
  name: "",
  category,
  manufacturer: "",
  package: "",
  description: "",
  parameters: [],
});
export const numberText = (value: number) =>
  new Intl.NumberFormat("ru-RU", { maximumSignificantDigits: 10 }).format(
    value,
  );
export type Access = {
  mode: "local" | "server";
  user: { id: number; username: string } | null;
  role: "visitor" | "viewer" | "admin";
  can_edit: boolean;
  can_delete: boolean;
  can_manage_users: boolean;
  csrf_token: string | null;
};
let csrfToken: string | null = null;
export class ApiError extends Error {
  constructor(
    message: string,
    public detail?: {
      code?: string;
      detected_category?: string;
      detected_label?: string;
    },
  ) {
    super(message);
  }
}
export async function request(url: string, options?: RequestInit) {
  const headers = new Headers(options?.headers);
  if (
    csrfToken &&
    url.startsWith("/api/") &&
    options?.method &&
    !["GET", "HEAD"].includes(options.method.toUpperCase())
  )
    headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 204) return null;
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      "Сервер вернул непонятный ответ. Перезапустите приложение.",
    );
  }
  if (response.status === 401 && csrfToken && url !== "/api/auth/login") {
    csrfToken = null;
    window.dispatchEvent(new Event("catalog-session-expired"));
  }
  if (!response.ok) {
    const d = data.detail;
    throw new ApiError(
      typeof d === "string"
        ? d
        : Array.isArray(d)
          ? d.map((e: { msg: string }) => e.msg).join("; ")
          : d?.message || "Не удалось выполнить запрос",
      d,
    );
  }
  if (url === "/api/auth/session") csrfToken = data.csrf_token;
  return data;
}
