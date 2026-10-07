/** Keep editing text untouched; normalize only when searching or saving. */
export function parseDecimal(text: string | number): number {
  if (typeof text === 'number') {
    if (!Number.isFinite(text) || text < 0) throw new Error('Введите конечное неотрицательное число');
    return text;
  }
  const normalized = String(text).trim().replace(',', '.');
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) {
    throw new Error('Введите неотрицательное число, например 0,5 или 0.5');
  }
  const value = Number(normalized);
  if (!Number.isFinite(value)) throw new Error('Значение слишком большое');
  return value;
}
