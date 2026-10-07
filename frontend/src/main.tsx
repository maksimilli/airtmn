import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { parseDecimal } from "./decimal";
import { emptyFilter, readColumns, serializeFilters } from "./catalog";
import type { Filter } from "./catalog";
import { ColumnPicker, FilterRow } from "./CatalogControls";
import { LoginPanel, UsersPanel } from "./AuthPanels";
import { Icon } from "./icons";
import { ApiError, blank, kinds, numberText, request, symbol } from "./model";
import type {
  Access,
  Category,
  Component,
  Definition,
  Document,
  Kind,
  Param,
  Stats,
} from "./model";
import "./style.css";

const routeNow = () => location.hash.slice(1) || "/overview";
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
function SourceBadge({ p }: { p: Param }) {
  const low =
    p.source === "ocr" && (p.confidence == null || p.confidence < 0.9);
  return (
    <span
      className={
        "badge " + (low ? "amber" : p.source === "manual" ? "neutral" : "green")
      }
      title="Сверьте значение с оригиналом. Оценка OCR не гарантирует правильность."
    >
      {p.source === "ocr"
        ? `OCR${p.confidence != null ? " " + Math.round(p.confidence * 100) + "%" : ""}${low ? " · проверьте" : ""}`
        : p.source === "text"
          ? "Из PDF"
          : p.evidence
            ? "Исправлено"
            : "Ручной ввод"}
    </span>
  );
}

function App() {
  const [access, setAccess] = useState<Access | null>(null);
  const canEdit = Boolean(access?.can_edit);
  const [route, setRoute] = useState(routeNow),
    [categories, setCategories] = useState<Category[]>([]),
    [definitions, setDefinitions] = useState<Definition[]>([]);
  const [allItems, setAllItems] = useState<Component[]>([]),
    [items, setItems] = useState<Component[]>([]),
    [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState<Stats>({
    components: 0,
    documents: 0,
    manufacturers: 0,
    parameters: 0,
  });
  const [ocrAvailable, setOcrAvailable] = useState<boolean | null>(null),
    [ocrMode, setOcrMode] = useState("auto");
  const [q, setQ] = useState(""),
    [manufacturer, setManufacturer] = useState(""),
    [packageName, setPackageName] = useState(""),
    [filters, setFilters] = useState<Filter[]>([]);
  const [columnPreferences, setColumnPreferences] = useState<
    Record<string, string[]>
  >(() => {
    try {
      return readColumns(localStorage.getItem("catalog.columns.v1"));
    } catch {
      return {};
    }
  });
  const [columnStorageError, setColumnStorageError] = useState(false);
  const [draft, setDraft] = useState<Component | null>(null),
    [selected, setSelected] = useState<Component | null>(null),
    [variants, setVariants] = useState<Component[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]),
    [preview, setPreview] = useState(""),
    [filename, setFilename] = useState(""),
    [pageCount, setPageCount] = useState(0),
    [pdfPage, setPdfPage] = useState(1),
    [previewTab, setPreviewTab] = useState("pdf");
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [dirty, setDirty] = useState(false),
    [menu, setMenu] = useState(false),
    [documentSearch, setDocumentSearch] = useState("");
  const [compareIds, setCompareIds] = useState<number[]>([]),
    [compareCategory, setCompareCategory] = useState("");
  const [mismatch, setMismatch] = useState<{
      category: string;
      label: string;
      file: File;
    } | null>(null),
    [dragging, setDragging] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false),
    [appliedSearch, setAppliedSearch] = useState("");
  const searchSignature = JSON.stringify([
    q,
    manufacturer,
    packageName,
    filters.map(({ id, ...filter }) => filter),
  ]);
  const inputRef = useRef<HTMLInputElement>(null),
    listRequest = useRef(0);
  const parts = route.split("/"),
    page = parts[1] || "overview",
    routeCategory = ["catalog", "import", "new"].includes(page)
      ? parts[2]
      : null;
  const categoryCode =
      routeCategory || draft?.category || selected?.category || "diode",
    category = categories.find((c) => c.code === categoryCode);
  const definition = (code: string) => definitions.find((d) => d.code === code);
  const visibleColumns = (
    columnPreferences[categoryCode] ??
    category?.columns ??
    []
  ).filter((code) => !category?.codes.length || category.codes.includes(code));
  function changeColumns(codes?: string[]) {
    const next = { ...columnPreferences };
    if (codes) next[categoryCode] = codes;
    else delete next[categoryCode];
    setColumnPreferences(next);
    try {
      localStorage.setItem("catalog.columns.v1", JSON.stringify(next));
      setColumnStorageError(false);
    } catch {
      setColumnStorageError(true);
    }
  }

  const fieldsFor = (code: string) => {
    const c = categories.find((c) => c.code === code);
    return c?.codes.length
      ? c.codes
          .map((code) => definitions.find((d) => d.code === code)!)
          .filter(Boolean)
      : definitions;
  };
  const valueText = (p: Param) => {
    const d = definition(p.code);
    return d
      ? `${numberText((Number(p.value) * d.units[p.unit]) / d.units[d.display_unit])}${d.display_unit === "1" ? "" : " " + d.display_unit}`
      : `${p.value} ${p.unit}`;
  };
  const editable = (c: Component) => ({
    ...c,
    parameters: c.parameters.map((p) => {
      const d = definition(p.code);
      return d
        ? {
            ...p,
            value: Number(
              (
                (Number(p.value) * d.units[p.unit]) /
                d.units[d.display_unit]
              ).toPrecision(12),
            ),
            unit: d.display_unit,
          }
        : { ...p };
    }),
  });
  function navigate(path: string, force = false) {
    if (
      !force &&
      dirty &&
      !window.confirm("Есть несохранённые изменения. Покинуть страницу?")
    )
      return;
    setDirty(false);
    setError("");
    setNotice("");
    setMismatch(null);
    setMenu(false);
    location.hash = path;
    setRoute(path);
    window.scrollTo({ top: 0 });
  }
  async function refresh() {
    const [cats, defs, comps, docs, counts, status, session] =
      await Promise.all([
        request("/api/categories"),
        request("/api/parameter-definitions?category=other"),
        request("/api/components"),
        request("/api/documents"),
        request("/api/stats"),
        request("/api/ocr/status"),
        request("/api/auth/session"),
      ]);
    setCategories(cats);
    setDefinitions(defs);
    setAllItems(comps);
    setDocuments(docs);
    setStats(counts);
    setOcrAvailable(status.available);
    setAccess(session);
  }
  useEffect(() => {
    void refresh()
      .catch((e) => setError(errorText(e)))
      .finally(() => setLoading(false));
    const changed = () => setRoute(routeNow());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    const expired = () => {
      void request("/api/auth/session")
        .then(setAccess)
        .catch((e) => setError(errorText(e)));
      setNotice("Сеанс закончился. Войдите снова для редактирования.");
    };
    window.addEventListener("catalog-session-expired", expired);
    return () => window.removeEventListener("catalog-session-expired", expired);
  }, []);
  async function logout() {
    if (dirty && !window.confirm("Есть несохранённые изменения. Выйти?"))
      return;
    try {
      await request("/api/auth/logout", { method: "POST" });
      setDirty(false);
      await refresh();
      navigate("/overview", true);
    } catch (e) {
      setError(errorText(e));
    }
  }
  useEffect(() => {
    const prevent = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  async function load(code: string, reset = false) {
    const current = ++listRequest.current;
    setSearchLoading(true);
    try {
      const query = new URLSearchParams({ category: code });
      if (!reset) {
        query.set("q", q);
        query.set("manufacturer", manufacturer);
        query.set("package", packageName);
        if (filters.length)
          query.set("filters", JSON.stringify(serializeFilters(filters)));
      }
      const found = await request("/api/components?" + query);
      if (current === listRequest.current) {
        setItems(found);
        setAppliedSearch(
          reset ? JSON.stringify(["", "", "", []]) : searchSignature,
        );
        setError("");
      }
    } catch (e) {
      if (current === listRequest.current) setError(errorText(e));
    } finally {
      if (current === listRequest.current) setSearchLoading(false);
    }
  }
  useEffect(() => {
    setError("");
    setNotice("");
    setMismatch(null);
    if (page === "catalog") {
      setDraft(null);
      setSelected(null);
      setItems([]);
      setQ("");
      setManufacturer("");
      setPackageName("");
      setFilters([]);
      setFiltersOpen(false);
      void load(parts[2] || "diode", true);
    }
    if (["overview", "documents", "compare"].includes(page)) {
      setDraft(null);
      setSelected(null);
    }
    if (page === "new" && definitions.length && canEdit) {
      setDraft(blank(parts[2] || "diode"));
      setSelected(null);
      setVariants([]);
      setWarnings([]);
      setFilename("");
      setPreview("");
    }
    if (page === "import") {
      setSelected(null);
      setDraft(null);
      setVariants([]);
      setWarnings([]);
      setPreview("");
      setFilename("");
    }
    if (
      (page === "component" || (page === "edit" && canEdit)) &&
      definitions.length
    ) {
      let active = true;
      setSelected(null);
      setDraft(null);
      void request("/api/components/" + parts[2])
        .then((c) => {
          if (!active) return;
          setSelected(c);
          if (page === "edit") {
            setDraft(editable(c));
            setVariants([]);
            setWarnings([]);
            setFilename(
              documents.find((d) => d.id === c.document_id)?.filename || "",
            );
            setPageCount(
              documents.find((d) => d.id === c.document_id)?.pages || 0,
            );
            setPreview("");
          }
        })
        .catch((e) => {
          if (active) setError(errorText(e));
        });
      return () => {
        active = false;
      };
    }
  }, [route, definitions.length, canEdit]);
  function changeDraft(patch: Partial<Component>) {
    if (draft) {
      setDraft({ ...draft, ...patch });
      setDirty(true);
    }
  }
  function edit(index: number, patch: Partial<Param>) {
    if (!draft) return;
    const manual =
      ["value", "code", "kind", "conditions"].some((k) => k in patch) &&
      !("source" in patch);
    changeDraft({
      parameters: draft.parameters.map((p, i) =>
        i === index
          ? {
              ...p,
              ...patch,
              ...(manual
                ? { source: "manual" as const, confidence: null }
                : {}),
            }
          : p,
      ),
    });
  }
  function changeUnit(index: number, p: Param, unit: string) {
    const d = definition(p.code);
    try {
      edit(index, {
        unit,
        value: d
          ? Number(
              (
                (parseDecimal(p.value) * d.units[p.unit]) /
                d.units[unit]
              ).toPrecision(12),
            )
          : p.value,
        source: p.source,
        confidence: p.confidence,
      });
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function upload(file: File, target = categoryCode, approved = false) {
    if (
      !approved &&
      dirty &&
      !window.confirm("Заменить несохранённый результат новым PDF?")
    )
      return;
    if (file.size > 20 * 1024 * 1024) {
      setError("PDF должен быть не больше 20 МБ.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    setMismatch(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("category", target);
      body.append("ocr_mode", ocrMode);
      const result = await request("/api/import", { method: "POST", body });
      setDraft(
        editable({
          ...blank(target),
          name: result.name,
          manufacturer: result.manufacturer,
          package: result.package,
          document_id: result.document_id,
          parameters: result.parameters,
        }),
      );
      setVariants(
        (result.variants || []).map((v: Component) => ({
          ...v,
          category: target,
        })),
      );
      setWarnings([
        ...result.warnings,
        ...(result.duplicate
          ? ["Этот PDF уже есть в библиотеке документов."]
          : []),
      ]);
      setPreview(result.text_preview);
      setFilename(result.filename);
      setPageCount(result.page_count);
      setPdfPage(1);
      setPreviewTab("pdf");
      setDirty(true);
      await refresh();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError && e.detail?.code === "category_mismatch")
        setMismatch({
          category: e.detail.detected_category!,
          label: e.detail.detected_label!,
          file,
        });
    } finally {
      setBusy(false);
    }
  }
  async function moveImport() {
    if (!mismatch) return;
    const { file, category } = mismatch;
    const next = "/import/" + category;
    setDirty(false);
    location.hash = next;
    setRoute(next);
    await upload(file, category, true);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const result = await request(
        "/api/components" + (draft.id ? "/" + draft.id : ""),
        {
          method: draft.id ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...draft,
            parameters: draft.parameters.map((p) => ({
              ...p,
              value: parseDecimal(p.value),
            })),
          }),
        },
      );
      setDirty(false);
      await refresh();
      navigate("/component/" + result.id, true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(c: Component) {
    if (
      !window.confirm(
        `Удалить ${c.name} из каталога? Исходный PDF останется в документах.`,
      )
    )
      return;
    setBusy(true);
    try {
      await request("/api/components/" + c.id, { method: "DELETE" });
      await refresh();
      navigate("/catalog/" + c.category, true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  function toggleCompare(c: Component) {
    const ids = compareCategory === c.category ? compareIds : [];
    if (!ids.includes(c.id!) && ids.length === 4) {
      setError("Можно сравнить до четырёх компонентов одного раздела.");
      return;
    }
    setCompareCategory(c.category);
    setCompareIds(
      ids.includes(c.id!) ? ids.filter((id) => id !== c.id) : [...ids, c.id!],
    );
  }
  const compared = allItems.filter((c) => compareIds.includes(c.id!)),
    documentLink = (id: string, n = 1) => "/api/documents/" + id + "#page=" + n;
  const title =
    page === "overview"
      ? "Каталог компонентов"
      : page === "catalog"
        ? category?.label
        : page === "documents"
          ? "Документы"
          : page === "import"
            ? "Добавить компонент из PDF"
            : page === "new"
              ? "Новый компонент"
              : page === "edit"
                ? "Редактирование"
                : page === "component"
                  ? selected?.name
                  : page === "compare"
                    ? "Сравнение компонентов"
                    : page === "login"
                      ? "Вход"
                      : page === "users"
                        ? "Администраторы"
                        : "Страница не найдена";

  function ComponentTable({
    rows,
    compact = false,
  }: {
    rows: Component[];
    compact?: boolean;
  }) {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {!compact && (
                <th
                  className="check-cell"
                  title="Отметьте до четырёх компонентов для сравнения"
                >
                  Сравнить
                </th>
              )}
              <th>Компонент</th>
              <th>Производитель / корпус</th>
              {!compact &&
                visibleColumns.map((code) => (
                  <th key={code} title={definition(code)?.label}>
                    <span>{definition(code)?.label || code}</span>
                    <small>
                      {symbol(code)} ·{" "}
                      {definition(code)?.display_unit === "1"
                        ? "безразмерная"
                        : definition(code)?.display_unit}
                    </small>
                  </th>
                ))}
              <th>Документ</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                {!compact && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={"Сравнить " + c.name}
                      checked={compareIds.includes(c.id!)}
                      onChange={() => toggleCompare(c)}
                    />
                  </td>
                )}
                <td>
                  <button
                    className="text-button component-name"
                    onClick={() => navigate("/component/" + c.id)}
                  >
                    {c.name}
                  </button>
                  <small>
                    {categories.find((cat) => cat.code === c.category)?.label}
                  </small>
                </td>
                <td>
                  {c.manufacturer || "Не указан"}
                  <small>{c.package || "Корпус не указан"}</small>
                </td>
                {!compact &&
                  visibleColumns.map((code) => {
                    const values = c.parameters.filter((p) => p.code === code);
                    return (
                      <td key={code}>
                        {values.length ? (
                          values.slice(0, 2).map((p, i) => (
                            <div
                              key={i}
                              className="cell-value"
                              title={p.conditions}
                            >
                              {valueText(p)}{" "}
                              <span className="kind-label">
                                {p.kind === "unspecified" ? "" : p.kind}
                              </span>
                            </div>
                          ))
                        ) : (
                          <span className="muted">—</span>
                        )}
                        {values.length > 2 && (
                          <small>Ещё {values.length - 2} знач.</small>
                        )}
                      </td>
                    );
                  })}
                <td>
                  {c.document_id ? (
                    <a
                      className="document-link"
                      href={documentLink(c.document_id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Icon name="document" size={16} />
                      PDF
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={"Открыть " + c.name}
                    title="Открыть карточку"
                    onClick={() => navigate("/component/" + c.id)}
                  >
                    <Icon name="arrow" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const editor = draft && (
    <div
      id="component-editor"
      className={"editor-layout" + (draft.document_id ? " with-preview" : "")}
    >
      <form className="panel editor" onSubmit={save}>
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              {draft.id
                ? "КАРТОЧКА КОМПОНЕНТА"
                : draft.document_id
                  ? "ШАГ 2 · ПРОВЕРКА ДАННЫХ"
                  : "ДОБАВЛЕНИЕ В КАТАЛОГ"}
            </span>
            <h2>{draft.id ? draft.name : "Характеристики компонента"}</h2>
          </div>
          <span className="badge blue">
            {categories.find((c) => c.code === draft.category)?.label}
          </span>
        </div>
        {draft.document_id && (
          <div className="import-summary">
            <Icon name="check" />
            <div>
              <b>
                {draft.parameters.length
                  ? `Автоматически заполнено: ${draft.parameters.length} значений`
                  : "Параметры не найдены"}
              </b>
              <small>
                {filename} · {pageCount || "—"} стр. · {variants.length || 1}{" "}
                моделей
              </small>
            </div>
          </div>
        )}
        {warnings.length > 0 && (
          <details className="import-notes" open={!draft.parameters.length}>
            <summary>
              <Icon name="warning" size={16} />
              Замечания к импорту ({warnings.length})
            </summary>
            {warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </details>
        )}
        {variants.length > 1 && (
          <label className="model-select">
            Модель из документа
            <select
              aria-label="Модель из документа"
              value={draft.name}
              onChange={(e) => {
                const v = variants.find((v) => v.name === e.target.value);
                if (v) {
                  setDraft(editable({ ...v, document_id: draft.document_id }));
                  setDirty(true);
                }
              }}
            >
              {!variants.some((v) => v.name === draft.name) && (
                <option value={draft.name}>
                  {draft.name || "Выберите модель"}
                </option>
              )}
              {variants.map((v) => (
                <option key={v.name} value={v.name}>
                  {v.name}
                </option>
              ))}
            </select>
            <small>Характеристики относятся к выбранной модели.</small>
          </label>
        )}
        <div className="form-grid">
          <label>
            Обозначение *
            <input
              required
              maxLength={200}
              value={draft.name}
              onChange={(e) => changeDraft({ name: e.target.value })}
              placeholder="Например, 1N4007"
            />
          </label>
          <label>
            Производитель
            <input
              value={draft.manufacturer}
              onChange={(e) => changeDraft({ manufacturer: e.target.value })}
              placeholder="Название производителя"
            />
          </label>
          <label>
            Корпус
            <input
              value={draft.package}
              onChange={(e) => changeDraft({ package: e.target.value })}
              placeholder="Например, DO-41"
            />
          </label>
          <label>
            Категория
            <input
              value={
                categories.find((c) => c.code === draft.category)?.label ||
                draft.category
              }
              readOnly
            />
          </label>
          <label className="wide">
            Описание
            <textarea
              rows={2}
              value={draft.description}
              onChange={(e) => changeDraft({ description: e.target.value })}
              placeholder="Назначение и особенности компонента"
            />
          </label>
        </div>
        <div className="section-heading parameter-heading">
          <div>
            <h3>Электрические характеристики</h3>
            <p>
              Запятая и точка поддерживаются. Укажите тип и условия измерения.
            </p>
          </div>
          <span className="badge neutral">{draft.parameters.length}</span>
        </div>
        {draft.parameters.map((p, i) => (
          <div
            className={
              "parameter" +
              (p.source === "ocr" &&
              (p.confidence == null || p.confidence < 0.9)
                ? " uncertain"
                : "")
            }
            key={i}
          >
            <div className="parameter-top">
              <span className="parameter-number">
                {String(i + 1).padStart(2, "0")}
              </span>
              <SourceBadge p={p} />
              <button
                className="icon-button danger"
                type="button"
                aria-label={"Удалить параметр " + (i + 1)}
                onClick={() =>
                  changeDraft({
                    parameters: draft.parameters.filter((_, j) => j !== i),
                  })
                }
              >
                <Icon name="trash" size={17} />
              </button>
            </div>
            <div className="parameter-grid">
              <label className="parameter-label">
                Параметр
                <select
                  aria-label="Параметр"
                  value={p.code}
                  onChange={(e) => {
                    const d = definition(e.target.value);
                    if (d)
                      edit(i, {
                        code: d.code,
                        value: "",
                        unit: d.display_unit,
                        kind: "unspecified",
                        conditions: "",
                        page: undefined,
                        evidence: "",
                      });
                  }}
                >
                  {fieldsFor(draft.category).map((d) => (
                    <option key={d.code} value={d.code}>
                      {symbol(d.code)} — {d.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Значение
                <input
                  aria-label="Значение"
                  required
                  inputMode="decimal"
                  value={p.value}
                  onChange={(e) => edit(i, { value: e.target.value })}
                  placeholder="0,5"
                />
              </label>
              <label>
                Единица
                <select
                  aria-label="Единица параметра"
                  value={p.unit}
                  onChange={(e) => changeUnit(i, p, e.target.value)}
                >
                  {Object.keys(definition(p.code)?.units || {}).map((u) => (
                    <option key={u} value={u}>
                      {u === "1" ? "Безразмерная" : u}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Тип
                <select
                  aria-label="Тип значения параметра"
                  value={p.kind}
                  onChange={(e) => edit(i, { kind: e.target.value as Kind })}
                >
                  {Object.entries(kinds).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="wide">
                Условия измерения
                <input
                  aria-label="Условия измерения"
                  value={p.conditions}
                  onChange={(e) => edit(i, { conditions: e.target.value })}
                  placeholder="Температура, напряжение, ток, длительность импульса…"
                />
              </label>
            </div>
            {p.evidence && (
              <details className="evidence">
                <summary>
                  Фрагмент PDF{p.page ? " · страница " + p.page : ""}
                </summary>
                <p>{p.evidence}</p>
                {draft.document_id && p.page && (
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => {
                      setPdfPage(p.page!);
                      setPreviewTab("pdf");
                    }}
                  >
                    Показать страницу {p.page}
                  </button>
                )}
              </details>
            )}
          </div>
        ))}
        {!draft.parameters.length && (
          <div className="empty small-empty">
            <Icon name="settings" size={30} />
            <h3>Добавьте характеристики</h3>
            <p>
              Для этого PDF значения не найдены. Сверьте оригинал и добавьте
              нужные параметры.
            </p>
          </div>
        )}
        <button
          className="button secondary add-parameter"
          type="button"
          onClick={() => {
            const d = fieldsFor(draft.category)[0];
            if (d)
              changeDraft({
                parameters: [
                  ...draft.parameters,
                  {
                    code: d.code,
                    value: "",
                    unit: d.display_unit,
                    kind: "unspecified",
                    conditions: "",
                    evidence: "",
                    source: "manual",
                  },
                ],
              });
          }}
        >
          <Icon name="plus" size={17} />
          Добавить характеристику
        </button>
        <div className="editor-footer">
          <span className="muted">
            {dirty ? "Есть несохранённые изменения" : "Изменений нет"}
          </span>
          <div className="actions">
            <button
              className="button secondary"
              type="button"
              disabled={busy}
              onClick={() =>
                navigate(
                  draft.id
                    ? "/component/" + draft.id
                    : "/catalog/" + draft.category,
                )
              }
            >
              Отмена
            </button>
            <button className="button primary" disabled={busy} type="submit">
              <Icon name="check" size={17} />
              {busy
                ? "Сохранение…"
                : draft.id
                  ? "Сохранить изменения"
                  : "Сохранить проверенный компонент"}
            </button>
          </div>
        </div>
      </form>
      {draft.document_id && (
        <aside className="panel pdf-preview" aria-label="Предпросмотр PDF">
          <div className="preview-heading">
            <div>
              <Icon name="document" />
              <b>Исходный документ</b>
            </div>
            <a
              href={documentLink(draft.document_id, pdfPage)}
              target="_blank"
              rel="noreferrer"
            >
              Открыть ↗
            </a>
          </div>
          <div className="preview-tabs">
            <button
              type="button"
              className={previewTab === "pdf" ? "active" : ""}
              onClick={() => setPreviewTab("pdf")}
            >
              PDF
            </button>
            <button
              type="button"
              className={previewTab === "text" ? "active" : ""}
              disabled={!preview}
              onClick={() => setPreviewTab("text")}
            >
              Извлечённый текст
            </button>
            {previewTab === "pdf" && (
              <label>
                Страница
                <input
                  type="number"
                  aria-label="Страница PDF"
                  min={1}
                  max={pageCount || undefined}
                  value={pdfPage}
                  onChange={(e) =>
                    setPdfPage(
                      Math.min(
                        pageCount || 200,
                        Math.max(1, Number(e.target.value)),
                      ),
                    )
                  }
                />
              </label>
            )}
          </div>
          {previewTab === "pdf" ? (
            <div className="pdf-canvas">
              <img
                key={pdfPage}
                alt={"Страница " + pdfPage + " исходного Datasheet"}
                src={
                  "/api/documents/" + draft.document_id + "/pages/" + pdfPage
                }
              />
            </div>
          ) : (
            <pre>{preview}</pre>
          )}
          <p className="preview-tip">
            Сверьте значения, единицы и условия. Если PDF не отображается,
            нажмите «Открыть».
          </p>
        </aside>
      )}
    </div>
  );

  return (
    <div className="app-shell">
      {menu && (
        <button
          className="menu-shade"
          aria-label="Закрыть меню"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={"sidebar" + (menu ? " mobile-open" : "")}>
        <button className="brand" onClick={() => navigate("/overview")}>
          <span className="brand-mark">
            <Icon name="chip" size={25} />
          </span>
          <span>
            Элемент<small>БИБЛИОТЕКА КОМПОНЕНТОВ</small>
          </span>
        </button>
        <nav aria-label="Основная навигация">
          <button
            className={"nav-link " + (page === "overview" ? "active" : "")}
            onClick={() => navigate("/overview")}
          >
            <Icon name="grid" />
            Главная
          </button>
          <div className="nav-caption">КАТАЛОГ</div>
          {[...new Set(categories.map((c) => c.group))].map((group) => (
            <div key={group} className="nav-group">
              <div className="group-name">{group}</div>
              {categories
                .filter((c) => c.group === group)
                .map((c) => (
                  <button
                    key={c.code}
                    className={
                      "nav-link category-link " +
                      ([
                        "catalog",
                        "import",
                        "new",
                        "component",
                        "edit",
                      ].includes(page) && categoryCode === c.code
                        ? "active"
                        : "")
                    }
                    onClick={() => navigate("/catalog/" + c.code)}
                  >
                    <Icon name={c.icon} size={18} />
                    <span>{c.label}</span>
                    <span className="nav-count">{c.count}</span>
                  </button>
                ))}
            </div>
          ))}
          <div className="nav-caption">ИНСТРУМЕНТЫ</div>
          <button
            className={"nav-link " + (page === "documents" ? "active" : "")}
            onClick={() => navigate("/documents")}
          >
            <Icon name="folder" />
            Документы<span className="nav-count">{stats.documents}</span>
          </button>
          <button
            className={"nav-link " + (page === "compare" ? "active" : "")}
            onClick={() => navigate("/compare")}
          >
            <Icon name="compare" />
            Сравнение
            {compareIds.length > 0 && (
              <span className="nav-count">{compareIds.length}</span>
            )}
          </button>
          {access?.can_manage_users && (
            <button
              className={"nav-link " + (page === "users" ? "active" : "")}
              onClick={() => navigate("/users")}
            >
              <Icon name="settings" />
              Администраторы
            </button>
          )}
        </nav>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              aria-label="Открыть меню"
              onClick={() => setMenu(true)}
            >
              <Icon name="menu" />
            </button>
            <span className="breadcrumb">
              Библиотека <span>/</span> <b>{title || "Загрузка…"}</b>
            </span>
          </div>
          {access?.mode === "server" && (
            <div className="account-actions">
              {access.user ? (
                <>
                  <span>{access.user.username}</span>
                  <button
                    className="button secondary"
                    onClick={() => void logout()}
                  >
                    Выйти
                  </button>
                </>
              ) : (
                <button
                  className="button secondary"
                  onClick={() => navigate("/login")}
                >
                  Войти
                </button>
              )}
            </div>
          )}
        </header>
        <main>
          <div className="page-heading">
            <div>
              <h1>{title || "Загрузка…"}</h1>
              {page === "overview" && (
                <p>
                  {canEdit
                    ? "Откройте категорию для поиска или загрузите PDF, чтобы добавить компонент."
                    : "Выберите категорию и найдите нужный компонент."}
                </p>
              )}
              {page === "import" && (
                <p>
                  Загрузите даташит, проверьте характеристики и сохраните
                  карточку.
                </p>
              )}
            </div>
            {page === "catalog" && canEdit && (
              <div className="actions">
                <button
                  className="button secondary"
                  disabled={loading}
                  onClick={() => navigate("/new/" + categoryCode)}
                >
                  <Icon name="plus" size={17} />
                  Добавить вручную
                </button>
                <button
                  className="button primary"
                  disabled={loading}
                  onClick={() => navigate("/import/" + categoryCode)}
                >
                  <Icon name="upload" size={17} />
                  Загрузить PDF
                </button>
              </div>
            )}
          </div>
          {error && (
            <div role="alert" className="alert error">
              <Icon name="warning" />
              <div>
                <b>
                  {mismatch
                    ? "Этот PDF относится к другому разделу"
                    : "Не удалось выполнить действие"}
                </b>
                <p>{error}</p>
                {mismatch && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void moveImport()}
                  >
                    Загрузить в раздел «{mismatch.label}»
                    <Icon name="arrow" size={16} />
                  </button>
                )}
                {!categories.length && !loading && (
                  <button
                    className="button secondary"
                    onClick={() =>
                      void refresh().catch((e) => setError(errorText(e)))
                    }
                  >
                    Повторить подключение
                  </button>
                )}
              </div>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              <Icon name="check" />
              {notice}
            </div>
          )}
          {loading && (
            <div className="panel loading-state">
              <span className="spinner" />
              Загрузка библиотеки…
            </div>
          )}
          {!loading && page === "overview" && (
            <div className="category-grid" aria-label="Категории компонентов">
              {categories.map((c) => (
                <article key={c.code} className="panel category-tile">
                  <button
                    className="category-open"
                    onClick={() => navigate("/catalog/" + c.code)}
                    aria-label={"Открыть категорию «" + c.label + "»"}
                  >
                    <span className="tile-icon">
                      <Icon name={c.icon} size={24} />
                    </span>
                    <span>
                      <h2>{c.label}</h2>
                      <small>Компонентов: {c.count}</small>
                    </span>
                    <Icon name="arrow" size={18} />
                  </button>
                  {canEdit && (
                    <button
                      className="category-add"
                      onClick={() => navigate("/import/" + c.code)}
                      aria-label={"Загрузить PDF в категорию «" + c.label + "»"}
                    >
                      <Icon name="plus" size={16} />
                      Загрузить PDF
                    </button>
                  )}
                </article>
              ))}
            </div>
          )}
          {!loading && page === "catalog" && category && (
            <>
              <section className="panel search-panel">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void load(categoryCode);
                  }}
                >
                  <div className="search-row">
                    <label className="search-input">
                      <Icon name="search" />
                      <input
                        aria-label="Поиск по названию"
                        placeholder="Поиск по обозначению компонента…"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                      />
                    </label>
                    <button
                      className="button primary"
                      type="submit"
                      disabled={searchLoading}
                    >
                      {searchLoading ? "Поиск…" : "Найти"}
                    </button>
                    <button
                      className="button secondary"
                      type="button"
                      aria-expanded={filtersOpen}
                      aria-controls="catalog-filters"
                      onClick={() => setFiltersOpen(!filtersOpen)}
                    >
                      <Icon name="settings" size={16} />
                      Фильтры
                      {(filters.length > 0 || manufacturer || packageName) && (
                        <span className="badge neutral">
                          {filters.length +
                            Number(Boolean(manufacturer)) +
                            Number(Boolean(packageName))}
                        </span>
                      )}
                    </button>
                    <button
                      className="button secondary"
                      type="button"
                      onClick={() => {
                        setQ("");
                        setManufacturer("");
                        setPackageName("");
                        setFilters([]);
                        void load(categoryCode, true);
                      }}
                    >
                      Сбросить
                    </button>
                  </div>
                  {filtersOpen && (
                    <div id="catalog-filters">
                      <div className="basic-filters">
                        <label>
                          Производитель
                          <input
                            placeholder="Любой производитель"
                            value={manufacturer}
                            onChange={(e) => setManufacturer(e.target.value)}
                          />
                        </label>
                        <label>
                          Корпус
                          <input
                            placeholder="Например, SOT-23"
                            value={packageName}
                            onChange={(e) => setPackageName(e.target.value)}
                          />
                        </label>
                      </div>
                      <div className="filters-heading">
                        <div>
                          <h3>Фильтры по характеристикам</h3>
                          <p>
                            {filters.length
                              ? "Все условия выполняются одновременно."
                              : "Выберите характеристики и задайте границы."}
                          </p>
                        </div>
                        <button
                          type="button"
                          className="button secondary"
                          disabled={filters.length >= 20}
                          onClick={() =>
                            setFilters([...filters, emptyFilter()])
                          }
                        >
                          <Icon name="plus" size={16} />
                          Добавить фильтр
                        </button>
                      </div>
                      {filters.map((filter, index) => (
                        <FilterRow
                          key={filter.id}
                          filter={filter}
                          index={index}
                          definitions={fieldsFor(categoryCode)}
                          onChange={(updated) =>
                            setFilters(
                              filters.map((f) =>
                                f.id === filter.id ? updated : f,
                              ),
                            )
                          }
                          onRemove={() =>
                            setFilters(
                              filters.filter((f) => f.id !== filter.id),
                            )
                          }
                        />
                      ))}
                      {filters.length > 0 && (
                        <div className="filter-apply">
                          <span className="muted">
                            Условия: {filters.length} · десятичные числа: 0,5
                            или 0.5
                          </span>
                          <button
                            className="button primary"
                            type="submit"
                            disabled={searchLoading}
                          >
                            {searchLoading ? "Поиск…" : "Применить фильтры"}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </form>
              </section>
              <section
                className="panel catalog-panel"
                aria-busy={searchLoading}
              >
                {appliedSearch && appliedSearch !== searchSignature && (
                  <p className="search-pending" role="status">
                    Условия изменены. Нажмите «Найти» или «Применить фильтры»,
                    чтобы обновить результаты.
                  </p>
                )}
                <div className="panel-heading">
                  <div>
                    <h2>Результаты поиска</h2>
                    <span className="muted" role="status">
                      Найдено: {items.length}
                    </span>
                  </div>
                </div>
                <div className="table-controls">
                  <ColumnPicker
                    definitions={fieldsFor(categoryCode)}
                    columns={visibleColumns}
                    onChange={changeColumns}
                    onReset={() => changeColumns()}
                  />
                </div>
                {columnStorageError && (
                  <p role="status" className="storage-note">
                    Браузер запретил сохранение настроек. Выбор столбцов
                    действует до закрытия страницы.
                  </p>
                )}
                {items.length ? (
                  <ComponentTable rows={items} />
                ) : (
                  <div className="empty">
                    <Icon name={category.icon} size={40} />
                    <h3>
                      {category.count
                        ? "По вашим условиям ничего не найдено"
                        : "В этом разделе пока нет компонентов"}
                    </h3>
                    <p>
                      {canEdit
                        ? "Измените поиск или добавьте компонент."
                        : "Измените условия поиска или выберите другую категорию."}
                    </p>
                    {canEdit && (
                      <div className="actions">
                        <button
                          className="button secondary"
                          onClick={() => navigate("/new/" + categoryCode)}
                        >
                          Добавить вручную
                        </button>
                        <button
                          className="button primary"
                          onClick={() => navigate("/import/" + categoryCode)}
                        >
                          <Icon name="upload" size={17} />
                          Загрузить PDF
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </section>
              {compared.length > 0 && (
                <div className="compare-bar">
                  <Icon name="compare" />
                  <span>
                    Выбрано: <b>{compared.length} / 4</b>
                  </span>
                  <button
                    className="text-button"
                    onClick={() => setCompareIds([])}
                  >
                    Очистить
                  </button>
                  <button
                    className="button primary"
                    onClick={() => navigate("/compare")}
                  >
                    Сравнить
                    <Icon name="arrow" size={16} />
                  </button>
                </div>
              )}
            </>
          )}
          {!loading && canEdit && page === "import" && (
            <>
              <div className="import-steps">
                <span className="active">
                  <b>1</b>Загрузка PDF
                </span>
                <span className={draft ? "active" : ""}>
                  <b>2</b>Проверка параметров
                </span>
                <span>
                  <b>3</b>Сохранение
                </span>
              </div>
              <section className="panel upload-panel">
                <div className="upload-settings">
                  <label>
                    Категория компонента
                    <select
                      aria-label="Категория импорта"
                      disabled={busy}
                      value={categoryCode}
                      onChange={(e) => navigate("/import/" + e.target.value)}
                    >
                      {categories.map((c) => (
                        <option value={c.code} key={c.code}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <details className="ocr-options">
                    <summary>Настройки распознавания</summary>
                    <label>
                      Распознавание сканов
                      <select
                        aria-label="Распознавание сканов"
                        disabled={busy}
                        value={ocrMode}
                        onChange={(e) => setOcrMode(e.target.value)}
                      >
                        <option value="auto">Автоматически</option>
                        <option value="off">Только текст PDF</option>
                        <option value="always">OCR всех страниц</option>
                      </select>
                    </label>
                    <div className="ocr-status">
                      <span
                        className={
                          "status-dot " + (ocrAvailable ? "" : "warning-dot")
                        }
                      />
                      {ocrAvailable
                        ? "Распознавание сканов готово"
                        : "OCR недоступен"}
                      <small>Обычные PDF читаются напрямую</small>
                    </div>
                  </details>
                </div>
                <div
                  className={
                    "drop-zone" +
                    (dragging ? " dragging" : "") +
                    (busy ? " processing" : "")
                  }
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (!busy) setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragging(false);
                    const f = e.dataTransfer.files[0];
                    if (f && !busy) void upload(f);
                  }}
                >
                  <span className="upload-icon">
                    {busy ? (
                      <span className="spinner" />
                    ) : (
                      <Icon name="upload" size={29} />
                    )}
                  </span>
                  <h2>
                    {busy ? "Извлекаем характеристики…" : "Перетащите PDF сюда"}
                  </h2>
                  <p>
                    {busy
                      ? "Дождитесь результата. Скан может обрабатываться около минуты."
                      : "PDF до 20 МБ · до 200 страниц · OCR до 10 страниц"}
                  </p>
                  <button
                    className="button primary"
                    disabled={busy || !definitions.length}
                    onClick={() => inputRef.current?.click()}
                  >
                    {busy
                      ? "Обработка…"
                      : draft
                        ? "Выбрать другой PDF"
                        : "Выбрать PDF"}
                  </button>
                  <input
                    ref={inputRef}
                    className="file-input"
                    type="file"
                    accept="application/pdf,.pdf"
                    aria-label="Файл Datasheet"
                    disabled={busy}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void upload(f);
                      e.target.value = "";
                    }}
                  />
                </div>
                <div className="upload-note">
                  <Icon name="check" size={16} />
                  Тип компонента проверяется при загрузке. PDF другого раздела
                  будет заблокирован.
                </div>
              </section>
              {draft && (
                <div className="next-step-notice" role="status">
                  <Icon name="check" size={18} />
                  <div>
                    <b>PDF обработан. Теперь проверьте карточку.</b>
                    <p>
                      Сверьте модель и характеристики с документом, затем
                      нажмите «Сохранить проверенный компонент».
                    </p>
                  </div>
                  <button
                    className="button primary"
                    onClick={() =>
                      document
                        .getElementById("component-editor")
                        ?.scrollIntoView({ behavior: "smooth", block: "start" })
                    }
                  >
                    Перейти к проверке
                  </button>
                </div>
              )}
              {editor}
            </>
          )}
          {!loading && canEdit && (page === "new" || page === "edit") && editor}
          {!loading && page === "component" && selected && (
            <>
              <div className="detail-actions">
                <button
                  className="text-button"
                  onClick={() => navigate("/catalog/" + selected.category)}
                >
                  <Icon name="back" size={17} />
                  Вернуться в раздел
                </button>
                {canEdit && (
                  <div className="actions">
                    {canEdit && (
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() => navigate("/edit/" + selected.id)}
                      >
                        <Icon name="edit" size={17} />
                        Редактировать
                      </button>
                    )}
                    {access?.can_delete && (
                      <button
                        className="icon-button danger"
                        disabled={busy}
                        aria-label="Удалить компонент"
                        onClick={() => void remove(selected)}
                      >
                        <Icon name="trash" />
                      </button>
                    )}
                  </div>
                )}
              </div>
              <section className="panel component-summary">
                <span className="summary-icon">
                  <Icon
                    name={
                      categories.find((c) => c.code === selected.category)
                        ?.icon || "chip"
                    }
                    size={40}
                  />
                </span>
                <div>
                  <span className="badge blue">
                    {
                      categories.find((c) => c.code === selected.category)
                        ?.label
                    }
                  </span>
                  <h2>{selected.name}</h2>
                  <p>{selected.description || "Описание не указано"}</p>
                </div>
                <dl>
                  <div>
                    <dt>Производитель</dt>
                    <dd>{selected.manufacturer || "Не указан"}</dd>
                  </div>
                  <div>
                    <dt>Корпус</dt>
                    <dd>{selected.package || "Не указан"}</dd>
                  </div>
                  <div>
                    <dt>Характеристики</dt>
                    <dd>{selected.parameters.length} значений</dd>
                  </div>
                </dl>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Электрические характеристики</h2>
                  <span className="badge neutral">
                    {selected.parameters.length}
                  </span>
                </div>
                {selected.parameters.length ? (
                  <div className="table-wrap">
                    <table className="spec-table">
                      <thead>
                        <tr>
                          <th>Параметр</th>
                          <th>Значение</th>
                          <th>Тип</th>
                          <th>Условия измерения</th>
                          <th>Источник</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.parameters.map((p, i) => (
                          <tr key={i}>
                            <td>
                              <b>{symbol(p.code)}</b>
                              <small>{definition(p.code)?.label}</small>
                            </td>
                            <td className="spec-value">{valueText(p)}</td>
                            <td>
                              <span className="badge neutral">
                                {kinds[p.kind]}
                              </span>
                            </td>
                            <td className="conditions-cell">
                              {p.conditions || "Не указаны"}
                            </td>
                            <td>
                              <SourceBadge p={p} />
                              {p.page && selected.document_id && (
                                <a
                                  className="source-page"
                                  href={documentLink(
                                    selected.document_id,
                                    p.page,
                                  )}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Страница {p.page} ↗
                                </a>
                              )}
                              {p.evidence && (
                                <details className="evidence">
                                  <summary>Исходный фрагмент</summary>
                                  <p>{p.evidence}</p>
                                </details>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty small-empty">
                    <h3>Характеристики ещё не заполнены</h3>
                    {canEdit && (
                      <button
                        className="button secondary"
                        onClick={() => navigate("/edit/" + selected.id)}
                      >
                        Добавить характеристики
                      </button>
                    )}
                  </div>
                )}
              </section>
              <section className="panel attached-document">
                <span className="tile-icon">
                  <Icon name="document" size={25} />
                </span>
                <div>
                  <h3>Исходный Datasheet</h3>
                  <p>
                    {documents.find((d) => d.id === selected.document_id)
                      ?.filename || "Документ не прикреплён"}
                  </p>
                </div>
                {selected.document_id ? (
                  <a
                    className="button secondary"
                    href={documentLink(selected.document_id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть PDF
                    <Icon name="arrow" size={16} />
                  </a>
                ) : (
                  canEdit && (
                    <button
                      className="button secondary"
                      onClick={() => navigate("/import/" + selected.category)}
                    >
                      Импортировать PDF
                    </button>
                  )
                )}
              </section>
            </>
          )}
          {!loading && page === "documents" && (
            <>
              <section className="panel document-toolbar">
                <label className="search-input">
                  <Icon name="search" />
                  <input
                    aria-label="Поиск документов"
                    placeholder="Поиск по имени PDF…"
                    value={documentSearch}
                    onChange={(e) => setDocumentSearch(e.target.value)}
                  />
                </label>
                {canEdit && (
                  <button
                    className="button primary"
                    onClick={() => navigate("/overview")}
                  >
                    <Icon name="upload" size={17} />
                    Загрузить PDF
                  </button>
                )}
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Библиотека документов</h2>
                  <span className="badge neutral">{documents.length}</span>
                </div>
                {documents.filter((d) =>
                  d.filename
                    .toLowerCase()
                    .includes(documentSearch.toLowerCase()),
                ).length ? (
                  <div className="document-list">
                    {documents
                      .filter((d) =>
                        d.filename
                          .toLowerCase()
                          .includes(documentSearch.toLowerCase()),
                      )
                      .map((d) => (
                        <article key={d.id} className="document-row">
                          <span className="pdf-icon">PDF</span>
                          <div className="document-meta">
                            <h3>{d.filename}</h3>
                            <p>
                              {d.pages || "—"} стр. ·{" "}
                              {d.size
                                ? numberText(d.size / 1024) + " КБ"
                                : "Размер не указан"}{" "}
                              · {d.components_count} компонентов
                            </p>
                            <div className="document-components">
                              {allItems
                                .filter((c) => c.document_id === d.id)
                                .map((c) => (
                                  <button
                                    className="text-button"
                                    key={c.id}
                                    onClick={() =>
                                      navigate("/component/" + c.id)
                                    }
                                  >
                                    {c.name}
                                  </button>
                                ))}
                            </div>
                          </div>
                          <a
                            className="button secondary"
                            href={documentLink(d.id)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Открыть
                            <Icon name="arrow" size={16} />
                          </a>
                        </article>
                      ))}
                  </div>
                ) : (
                  <div className="empty">
                    <Icon name="folder" size={38} />
                    <h3>
                      {documentSearch
                        ? "Документы не найдены"
                        : "Здесь появятся ваши Datasheet"}
                    </h3>
                    <p>PDF сохраняется после успешного импорта.</p>
                  </div>
                )}
              </section>
            </>
          )}
          {!loading && page === "compare" && (
            <>
              {compared.length ? (
                <>
                  <div className="compare-note">
                    <Icon name="warning" size={18} />
                    <span>
                      Строки учитывают тип и условия измерения. «—» означает
                      отсутствие значения.
                    </span>
                    <button
                      className="text-button"
                      onClick={() => setCompareIds([])}
                    >
                      Очистить
                    </button>
                  </div>
                  <section className="panel table-wrap">
                    <table className="comparison">
                      <thead>
                        <tr>
                          <th>Характеристика</th>
                          {compared.map((c) => (
                            <th key={c.id}>
                              <button
                                className="text-button component-name"
                                onClick={() => navigate("/component/" + c.id)}
                              >
                                {c.name}
                              </button>
                              <small>
                                {c.manufacturer || "Производитель не указан"}
                              </small>
                              <button
                                className="text-button remove-compare"
                                onClick={() =>
                                  setCompareIds(
                                    compareIds.filter((id) => id !== c.id),
                                  )
                                }
                              >
                                Убрать
                              </button>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <th>Корпус</th>
                          {compared.map((c) => (
                            <td key={c.id}>{c.package || "—"}</td>
                          ))}
                        </tr>
                        {Array.from(
                          new Set(
                            compared.flatMap((c) =>
                              c.parameters.map((p) =>
                                JSON.stringify([p.code, p.kind, p.conditions]),
                              ),
                            ),
                          ),
                        ).map((key) => {
                          const [code, kind, conditions] = JSON.parse(key);
                          return (
                            <tr key={key}>
                              <th>
                                {symbol(code)}{" "}
                                <span className="kind-label">
                                  {kind === "unspecified" ? "" : kind}
                                </span>
                                <small>{definition(code)?.label}</small>
                                {conditions && <small>{conditions}</small>}
                              </th>
                              {compared.map((c) => (
                                <td key={c.id}>
                                  {c.parameters
                                    .filter(
                                      (p) =>
                                        p.code === code &&
                                        p.kind === kind &&
                                        p.conditions === conditions,
                                    )
                                    .map((p, i) => (
                                      <div key={i}>{valueText(p)}</div>
                                    ))}
                                  {!c.parameters.some(
                                    (p) =>
                                      p.code === code &&
                                      p.kind === kind &&
                                      p.conditions === conditions,
                                  ) && "—"}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                        <tr>
                          <th>Datasheet</th>
                          {compared.map((c) => (
                            <td key={c.id}>
                              {c.document_id ? (
                                <a
                                  href={documentLink(c.document_id)}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Открыть PDF ↗
                                </a>
                              ) : (
                                "—"
                              )}
                            </td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </section>
                </>
              ) : (
                <div className="panel empty">
                  <Icon name="compare" size={42} />
                  <h3>Выберите компоненты для сравнения</h3>
                  <p>
                    В таблице раздела отметьте до четырёх компонентов одного
                    типа.
                  </p>
                  <button
                    className="button primary"
                    onClick={() =>
                      navigate("/catalog/" + (compareCategory || "diode"))
                    }
                  >
                    Открыть каталог
                    <Icon name="arrow" size={16} />
                  </button>
                </div>
              )}
            </>
          )}
          {!loading && page === "login" && access?.mode === "server" && (
            <LoginPanel
              onDone={async () => {
                await refresh();
                navigate("/overview", true);
              }}
            />
          )}
          {!loading && page === "users" && access?.can_manage_users && (
            <UsersPanel />
          )}
          {!loading &&
            ((["import", "new", "edit"].includes(page) && !canEdit) ||
              (page === "users" && !access?.can_manage_users)) && (
              <div className="panel empty">
                <h2>Доступ только для администратора</h2>
                <p>Каталог доступен для просмотра без входа.</p>
                <button
                  className="button primary"
                  onClick={() => navigate("/login")}
                >
                  Войти
                </button>
              </div>
            )}
          {!loading &&
            (![
              "overview",
              "catalog",
              "import",
              "new",
              "component",
              "edit",
              "documents",
              "compare",
              "login",
              "users",
            ].includes(page) ||
              (page === "catalog" && !category)) && (
              <div className="panel empty">
                <h3>Страница не найдена</h3>
                <button
                  className="button primary"
                  onClick={() => navigate("/overview")}
                >
                  Открыть библиотеку
                </button>
              </div>
            )}
        </main>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
