import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { parseDecimal } from './decimal';
import './style.css';

type Kind = 'min' | 'typ' | 'max' | 'unspecified';
type Param = { code: string; value: number | string; unit: string; kind: Kind; conditions: string; page?: number; evidence: string; source?: 'text' | 'ocr' | 'manual'; confidence?: number | null };
type Component = { id?: number; name: string; manufacturer: string; package: string; description: string; document_id?: string; parameters: Param[] };
type Definition = { code: string; label: string; unit: string; display_unit: string; units: Record<string, number> };
type Filter = { code: string; kind: Kind; unit: string; min: string; max: string; conditions: string };
const kinds: Record<Kind, string> = { min: 'Минимальное', typ: 'Типовое', max: 'Максимальное', unspecified: 'Не указано' };
const blank = (): Component => ({ name: '', manufacturer: '', package: '', description: '', parameters: [] });
const emptyFilter = (): Filter => ({ code: '', kind: 'max', unit: 'V', min: '', max: '', conditions: '' });
const symbol = (code: string) => code === 'IF_AV' ? 'IF(AV)' : code;
const round = (value: number) => Number(value.toPrecision(12));
const numberText = (value: number) => new Intl.NumberFormat('ru-RU', { maximumSignificantDigits: 12 }).format(value);

async function request(url: string, options?: RequestInit) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : data.detail?.map((error: { msg: string }) => error.msg).join('; ');
    throw new Error(message || 'Не удалось выполнить запрос');
  }
  return data;
}

function App() {
  const [items, setItems] = useState<Component[]>([]);
  const [definitions, setDefinitions] = useState<Definition[]>([]);
  const [q, setQ] = useState('');
  const [voltage, setVoltage] = useState('');
  const [current, setCurrent] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [packageName, setPackageName] = useState('');
  const [filter, setFilter] = useState<Filter>(emptyFilter());
  const [draft, setDraft] = useState<Component | null>(null);
  const [selected, setSelected] = useState<Component | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [preview, setPreview] = useState('');
  const [ocrMode, setOcrMode] = useState<'auto' | 'always' | 'off'>('auto');
  const [ocrAvailable, setOcrAvailable] = useState<boolean | null>(null);
  const [variants, setVariants] = useState<Component[]>([]);
  const definition = (code: string) => definitions.find(item => item.code === code);

  const editable = (component: Component): Component => ({ ...component, parameters: component.parameters.map(p => {
    const d = definition(p.code);
    return d ? { ...p, value: round(Number(p.value) * d.units[p.unit] / d.units[d.display_unit]), unit: d.display_unit } : { ...p };
  }) });
  const displayValue = (p: Param) => {
    const d = definition(p.code);
    return d ? `${numberText(Number(p.value) * d.units[p.unit] / d.units[d.display_unit])} ${d.display_unit}` : `${p.value} ${p.unit}`;
  };

  async function load(reset = false) {
    try {
      const query = new URLSearchParams(reset ? {} : { q, manufacturer, package: packageName });
      if (!reset) {
        if (voltage.trim()) query.set('min_voltage', String(parseDecimal(voltage)));
        if (current.trim()) query.set('min_current', String(parseDecimal(current)));
        if (filter.code) {
          query.set('parameter_code', filter.code);
          query.set('parameter_kind', filter.kind);
          query.set('parameter_unit', filter.unit);
          if (filter.min.trim()) query.set('parameter_min', String(parseDecimal(filter.min)));
          if (filter.max.trim()) query.set('parameter_max', String(parseDecimal(filter.max)));
          if (filter.conditions.trim()) query.set('conditions', filter.conditions.trim());
        }
      }
      setItems(await request('/api/components?' + query));
      setError('');
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => {
    void request('/api/parameter-definitions').then(setDefinitions).catch(e => setError(String(e)));
    void request('/api/ocr/status').then(data => setOcrAvailable(data.available)).catch(() => setOcrAvailable(false));
    void load();
  }, []);

  function begin(component: Component) {
    setDraft(editable(component));
    setVariants([]);
    setWarnings([]);
    setPreview('');
    setError('');
    setNotice('');
  }
  async function openCard(id: number) {
    try { setSelected(await request('/api/components/' + id)); setDraft(null); setError(''); }
    catch (e) { setError(String(e)); }
  }
  async function upload(file: File) {
    setBusy(true); setError(''); setNotice('');
    try {
      const body = new FormData(); body.append('file', file); body.append('ocr_mode', ocrMode);
      const result = await request('/api/import', { method: 'POST', body });
      setSelected(null);
      setDraft(editable({ ...blank(), name: result.name, manufacturer: result.manufacturer, package: result.package, document_id: result.document_id, parameters: result.parameters }));
      setVariants(result.variants || []);
      setWarnings([...result.warnings, ...(result.duplicate ? ['Этот документ уже загружался.'] : [])]);
      setPreview(result.text_preview);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  function edit(index: number, patch: Partial<Param>) {
    const manuallyChanged = ['value', 'code', 'kind', 'conditions'].some(key => key in patch) && !('source' in patch);
    if (draft) setDraft({ ...draft, parameters: draft.parameters.map((p, i) => i === index ? { ...p, ...patch, ...(manuallyChanged ? { source: 'manual' as const, confidence: null } : {}) } : p) });
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!draft) return;
    setBusy(true); setError('');
    try {
      const result = await request('/api/components' + (draft.id ? '/' + draft.id : ''), {
        method: draft.id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...draft, parameters: draft.parameters.map(p => ({ ...p, value: parseDecimal(p.value) })) }),
      });
      setDraft(null);
      setSelected(await request('/api/components/' + result.id));
      await load();
      setNotice('Компонент сохранён');
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  function changeUnit(index: number, p: Param, unit: string) {
    const d = definition(p.code);
    let value = p.value;
    try { if (d) value = round(parseDecimal(value) * d.units[p.unit] / d.units[unit]); }
    catch { /* Keep incomplete editing text until the user finishes typing. */ }
    edit(index, { unit, value, source: p.source, confidence: p.confidence });
  }

  return <>
    <header><strong>Электронные компоненты</strong><span>Каталог и импорт Datasheet</span></header>
    <div className="layout">
      <aside><h3>Библиотека</h3><p>Электронные компоненты</p><p>↳ Дискретные компоненты</p><b>↳ Диоды</b><small>Каталог диодов с характеристиками, условиями измерения и исходными документами.</small></aside>
      <main>
        <div className="heading"><div><h1>Диоды</h1><p>Характеристики, документация и поиск компонентов</p></div><button disabled={busy || !definitions.length} onClick={() => { setSelected(null); begin(blank()); }}>+ Добавить вручную</button></div>
        <form className="toolbar" onSubmit={e => { e.preventDefault(); void load(); }}>
          <input placeholder="Название компонента" aria-label="Поиск по названию" value={q} onChange={e => setQ(e.target.value)} />
          <input type="text" inputMode="decimal" placeholder="VRRM от, В" value={voltage} onChange={e => setVoltage(e.target.value)} />
          <input type="text" inputMode="decimal" placeholder="IF(AV) от, А" value={current} onChange={e => setCurrent(e.target.value)} />
          <button type="submit">Найти</button>
          <button type="button" className="secondary" onClick={() => { setQ(''); setVoltage(''); setCurrent(''); setManufacturer(''); setPackageName(''); setFilter(emptyFilter()); void load(true); }}>Сбросить фильтры</button>
          <label className="upload">{busy ? 'Обработка…' : 'Загрузить PDF'}<input disabled={busy || !definitions.length} type="file" accept="application/pdf" onChange={e => { if (e.target.files?.[0]) void upload(e.target.files[0]); e.target.value = ''; }} /></label>
          <div className="ocr-settings"><label>Распознавание сканов<select aria-label="Распознавание сканов" disabled={busy} value={ocrMode} onChange={e => setOcrMode(e.target.value as 'auto' | 'always' | 'off')}><option value="auto">Автоматически</option><option value="always">OCR всех страниц</option><option value="off">Без OCR</option></select></label><small>{ocrAvailable === null ? 'Проверка OCR…' : ocrAvailable ? 'OCR готов. Скан может обрабатываться около минуты.' : 'OCR недоступен. Перезапустите START_WINDOWS.bat для установки зависимостей.'}</small></div>
          <details className="advanced"><summary>Дополнительные фильтры</summary><div className="filter-grid">
            <label>Производитель<input value={manufacturer} onChange={e => setManufacturer(e.target.value)} /></label>
            <label>Корпус<input value={packageName} onChange={e => setPackageName(e.target.value)} /></label>
            <label>Характеристика<select aria-label="Характеристика" value={filter.code} onChange={e => { const d = definition(e.target.value); setFilter({ ...emptyFilter(), code: e.target.value, unit: d?.display_unit || 'V' }); }}><option value="">Не выбрана</option>{definitions.map(d => <option key={d.code} value={d.code}>{symbol(d.code)} — {d.label}</option>)}</select></label>
            {filter.code && <>
              <label>Тип значения<select aria-label="Тип значения" value={filter.kind} onChange={e => setFilter({ ...filter, kind: e.target.value as Kind })}>{Object.entries(kinds).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}</select></label>
              <label>Единица<select aria-label="Единица фильтра" value={filter.unit} onChange={e => setFilter({ ...filter, unit: e.target.value, min: '', max: '' })}>{Object.keys(definition(filter.code)?.units || {}).map(unit => <option key={unit}>{unit}</option>)}</select></label>
              <label>От<input inputMode="decimal" value={filter.min} onChange={e => setFilter({ ...filter, min: e.target.value })} /></label>
              <label>До<input inputMode="decimal" value={filter.max} onChange={e => setFilter({ ...filter, max: e.target.value })} /></label>
              <label>Условия содержат<input placeholder="Например, 25 °C" value={filter.conditions} onChange={e => setFilter({ ...filter, conditions: e.target.value })} /></label>
              <small className="filter-note">Фильтр проверяет одно значение с выбранным типом и условиями. При сравнении компонентов учитывайте температуру и режим измерения.</small>
            </>}
          </div></details>
        </form>
        {error && <p role="alert" className="error">{error}</p>}
        {notice && <p role="status" className="success">{notice}</p>}
        <section className="table"><table><thead><tr><th>Название</th><th>Производитель</th><th>Корпус</th><th>VRRM</th><th>IF(AV)</th><th>Документ</th></tr></thead>
          <tbody>{items.map(c => <tr key={c.id}><td><button className="link" onClick={() => void openCard(c.id!)}>{c.name}</button></td><td>{c.manufacturer || '—'}</td><td>{c.package || '—'}</td>{['VRRM', 'IF_AV'].map(code => <td key={code}>{c.parameters.filter(p => p.code === code && p.kind === 'max').map((p, i) => <div title={p.conditions} key={i}>{displayValue(p)}<small>{p.conditions}</small></div>)}</td>)}<td>{c.document_id ? <a href={'/api/documents/' + c.document_id} target="_blank" rel="noreferrer">Datasheet ↗</a> : '—'}</td></tr>)}</tbody></table>
          {!items.length && <div className="empty">Компоненты не найдены. Добавьте компонент или измените фильтры.</div>}
        </section>
        {selected && !draft && <section className="card" aria-label="Карточка компонента">
          <div className="heading"><div><small>Карточка компонента</small><h2>{selected.name}</h2></div><div className="actions"><button disabled={busy} onClick={() => begin(selected)}>Редактировать</button><button className="secondary" onClick={() => setSelected(null)}>Закрыть карточку</button></div></div>
          <dl className="metadata"><div><dt>Производитель</dt><dd>{selected.manufacturer || '—'}</dd></div><div><dt>Корпус</dt><dd>{selected.package || '—'}</dd></div><div><dt>Описание</dt><dd>{selected.description || '—'}</dd></div></dl>
          {selected.document_id && <a target="_blank" rel="noreferrer" href={'/api/documents/' + selected.document_id}>Открыть исходный Datasheet ↗</a>}
          <h3>Характеристики</h3><div className="table"><table><thead><tr><th>Параметр</th><th>Значение</th><th>Тип</th><th>Условия измерения</th><th>Источник</th></tr></thead><tbody>{selected.parameters.map((p, i) => <tr key={i}><td><b>{symbol(p.code)}</b><small>{definition(p.code)?.label}</small></td><td>{displayValue(p)}</td><td>{kinds[p.kind]}</td><td>{p.conditions || 'Не указаны'}</td><td><SourceBadge parameter={p} />{p.page && selected.document_id ? <a target="_blank" rel="noreferrer" href={'/api/documents/' + selected.document_id + '#page=' + p.page}>Страница {p.page} ↗</a> : 'Ручной ввод'}{p.evidence && <details><summary>Исходный фрагмент</summary><p>{p.evidence}</p></details>}</td></tr>)}</tbody></table>{!selected.parameters.length && <p className="empty">Характеристики ещё не заполнены.</p>}</div>
        </section>}
        {draft && <section className="editor">
          <h2>{draft.id ? 'Редактирование ' + draft.name : draft.document_id ? 'Проверка импорта' : 'Новый компонент'}</h2>
          {warnings.map((warning, i) => <p className="warning" key={i}>{warning}</p>)}
          <form onSubmit={e => void save(e)}>
            {variants.length > 1 && <label>Модель из документа<select aria-label="Модель из документа" value={draft.name} onChange={e => { const model = variants.find(v => v.name === e.target.value); if (model) setDraft(editable({ ...model, document_id: draft.document_id })); }}>{!variants.some(v => v.name === draft.name) && <option value={draft.name}>{draft.name || 'Выберите модель'}</option>}{variants.map(v => <option key={v.name} value={v.name}>{v.name}</option>)}</select></label>}
            <div className="fields">{(['name', 'manufacturer', 'package', 'description'] as const).map((key, i) => <label key={key}>{['Обозначение *', 'Производитель', 'Корпус', 'Описание'][i]}<input required={key === 'name'} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>)}</div>
            <h3>Характеристики</h3><p>Запятая и точка поддерживаются. Выбирайте тип значения и сохраняйте условия из Datasheet.</p>
            {draft.parameters.map((p, i) => <div className={'parameter' + (p.source === 'ocr' && (p.confidence == null || p.confidence < .9) ? ' uncertain' : '')} key={i}>
              <label>Параметр<select aria-label="Параметр" value={p.code} onChange={e => { const d = definition(e.target.value); if (d) edit(i, { code: d.code, unit: d.display_unit, value: '', conditions: '', evidence: '', page: undefined, kind: 'max' }); }}>{definitions.map(d => <option key={d.code} value={d.code}>{symbol(d.code)} — {d.label}</option>)}</select></label>
              <label>Значение<input aria-label="Значение" required inputMode="decimal" placeholder="0,5" value={p.value} onChange={e => edit(i, { value: e.target.value })} /></label>
              <label>Единица<select aria-label="Единица параметра" value={p.unit} onChange={e => changeUnit(i, p, e.target.value)}>{Object.keys(definition(p.code)?.units || {}).map(unit => <option key={unit}>{unit}</option>)}</select></label>
              <label>Тип значения<select aria-label="Тип значения параметра" value={p.kind} onChange={e => edit(i, { kind: e.target.value as Kind })}>{Object.entries(kinds).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}</select></label>
              <label className="conditions">Условия измерения<input placeholder="Ток, температура, длительность импульса…" value={p.conditions} onChange={e => edit(i, { conditions: e.target.value })} /></label>
              <button className="secondary" type="button" onClick={() => setDraft({ ...draft, parameters: draft.parameters.filter((_, j) => j !== i) })}>Удалить параметр</button>
              <SourceBadge parameter={p} />{p.evidence && <small className="source">Исходный текст, страница {p.page}: {p.evidence}</small>}
            </div>)}
            <button className="secondary" type="button" onClick={() => setDraft({ ...draft, parameters: [...draft.parameters, { code: 'VRRM', value: '', unit: 'V', kind: 'max', conditions: '', evidence: '' }] })}>+ Характеристика</button>
            {preview && <details className="text-preview"><summary>Извлечённый текст документа</summary><pre>{preview}</pre></details>}
            <div className="actions"><button disabled={busy} type="submit">{draft.id ? 'Сохранить изменения' : 'Сохранить проверенный компонент'}</button><button className="secondary" type="button" onClick={() => setDraft(null)}>Отмена</button></div>
          </form>
        </section>}
      </main>
    </div>
  </>;
}
function SourceBadge({ parameter }: { parameter: Param }) {
  if (parameter.source === 'ocr') return <span className={'source-badge' + (parameter.confidence == null || parameter.confidence < .9 ? ' low' : '')} title="Оценка движка OCR не гарантирует правильность. Проверьте по исходному PDF.">OCR{parameter.confidence != null ? ' ' + Math.round(parameter.confidence * 100) + '%' : ''}{parameter.confidence == null || parameter.confidence < .9 ? ' · проверьте' : ''}</span>;
  if (parameter.source === 'manual' && parameter.evidence) return <span className="source-badge">Исправлено вручную</span>;
  return null;
}
createRoot(document.getElementById('root')!).render(<App />);
