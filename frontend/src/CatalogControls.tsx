import { useState } from "react";
import type { Definition, Kind } from "./model";
import { kinds, symbol } from "./model";
import { emptyFilter } from "./catalog";
import type { Filter } from "./catalog";
import { Icon } from "./icons";

export function FilterRow({
  filter,
  index,
  definitions,
  onChange,
  onRemove,
}: {
  filter: Filter;
  index: number;
  definitions: Definition[];
  onChange: (filter: Filter) => void;
  onRemove: () => void;
}) {
  const definition = definitions.find((d) => d.code === filter.code);
  const update = (changes: Partial<Filter>) =>
    onChange({ ...filter, ...changes });
  return (
    <fieldset className="parameter-filter">
      <legend>Условие {index + 1}</legend>
      <div className="filter-row-heading">
        <span>
          {filter.code
            ? definition?.label
            : "Выберите характеристику для поиска"}
        </span>
        <button
          type="button"
          className="text-button remove-filter"
          onClick={onRemove}
          aria-label={`Удалить условие ${index + 1}`}
        >
          Удалить
        </button>
      </div>
      <div className="filter-fields">
        <label>
          Характеристика
          <select
            value={filter.code}
            aria-label={`Характеристика ${index + 1}`}
            required
            onChange={(e) => {
              const d = definitions.find((d) => d.code === e.target.value);
              onChange({
                ...emptyFilter(),
                id: filter.id,
                code: e.target.value,
                unit: d?.display_unit || "V",
              });
            }}
          >
            <option value="">Выберите…</option>
            {definitions.map((d) => (
              <option key={d.code} value={d.code}>
                {d.label} ({symbol(d.code)})
              </option>
            ))}
          </select>
        </label>
        <label>
          От
          <input
            aria-label={`От ${index + 1}`}
            inputMode="decimal"
            placeholder="Без ограничения"
            disabled={!filter.code}
            value={filter.min}
            onChange={(e) => update({ min: e.target.value })}
          />
        </label>
        <label>
          До
          <input
            aria-label={`До ${index + 1}`}
            inputMode="decimal"
            placeholder="Без ограничения"
            disabled={!filter.code}
            value={filter.max}
            onChange={(e) => update({ max: e.target.value })}
          />
        </label>
        <label>
          Единица
          <select
            aria-label={`Единица ${index + 1}`}
            value={filter.unit}
            disabled={!filter.code}
            onChange={(e) => update({ unit: e.target.value, min: "", max: "" })}
          >
            {!definition && <option value="V">—</option>}
            {Object.keys(definition?.units || {}).map((u) => (
              <option key={u} value={u}>
                {u === "1" ? "Безразмерная" : u}
              </option>
            ))}
          </select>
        </label>
      </div>
      {filter.code && (
        <details className="filter-extras">
          <summary>Тип значения и условия измерения</summary>
          <div className="filter-extra-fields">
            <label>
              Тип значения
              <select
                value={filter.kind}
                aria-label={`Тип значения ${index + 1}`}
                onChange={(e) => update({ kind: e.target.value as Kind | "" })}
              >
                <option value="">Любой тип</option>
                {Object.entries(kinds).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Условия содержат
              <input
                placeholder="Например, TA = 25 C"
                aria-label={`Условия ${index + 1}`}
                value={filter.conditions}
                onChange={(e) => update({ conditions: e.target.value })}
              />
            </label>
          </div>
          <p className="filter-note">
            Границы, тип и условия должны совпасть у одного значения
            характеристики.
          </p>
        </details>
      )}
    </fieldset>
  );
}

export function ColumnPicker({
  definitions,
  columns,
  onChange,
  onReset,
}: {
  definitions: Definition[];
  columns: string[];
  onChange: (codes: string[]) => void;
  onReset: () => void;
}) {
  const [search, setSearch] = useState("");
  const matching = definitions.filter((d) =>
    `${d.label} ${d.code} ${symbol(d.code)}`
      .toLocaleLowerCase("ru")
      .includes(search.trim().toLocaleLowerCase("ru")),
  );
  return (
    <details className="column-picker">
      <summary className="button secondary">
        <Icon name="settings" size={16} />
        Столбцы таблицы
        <span className="badge neutral">{columns.length}</span>
      </summary>
      <div className="column-options">
        <div className="panel-heading">
          <div>
            <h3>Какие характеристики показывать?</h3>
            <p>Выбор запоминается для этого раздела в вашем браузере.</p>
          </div>
          <button className="text-button" onClick={onReset}>
            Вернуть стандартные
          </button>
        </div>
        <label className="column-search">
          Найти характеристику
          <input
            placeholder="Название или обозначение, например IR"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {!matching.length && (
          <p role="status">Характеристики не найдены. Измените запрос.</p>
        )}
        <div className="column-checks">
          {matching.map((d) => (
            <label key={d.code}>
              <input
                type="checkbox"
                checked={columns.includes(d.code)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...columns, d.code]
                      : columns.filter((c) => c !== d.code),
                  )
                }
              />
              <span>
                {d.label}
                <small>
                  {symbol(d.code)} ·{" "}
                  {d.display_unit === "1" ? "безразмерная" : d.display_unit}
                </small>
              </span>
            </label>
          ))}
        </div>
      </div>
    </details>
  );
}
