"""Canonical diode parameter definitions and unit conversions."""
DEFINITIONS = {
    'VRRM': dict(label='Повторяющееся пиковое обратное напряжение', unit='V', display_unit='V', units={'V': 1, 'mV': .001}),
    'VRMS': dict(label='Действующее обратное напряжение', unit='V', display_unit='V', units={'V': 1, 'mV': .001}),
    'VDC': dict(label='Постоянное блокирующее напряжение', unit='V', display_unit='V', units={'V': 1, 'mV': .001}),
    'IF_AV': dict(label='Средний прямой ток', unit='A', display_unit='A', units={'A': 1, 'mA': .001, 'µA': .000001}),
    'IFSM': dict(label='Импульсный прямой ток', unit='A', display_unit='A', units={'A': 1, 'mA': .001}),
    'VF': dict(label='Прямое напряжение', unit='V', display_unit='V', units={'V': 1, 'mV': .001}),
    'IR': dict(label='Обратный ток', unit='A', display_unit='µA', units={'A': 1, 'mA': .001, 'µA': .000001}),
    'CJ': dict(label='Ёмкость перехода', unit='F', display_unit='pF', units={'F': 1, 'µF': .000001, 'nF': 1e-9, 'pF': 1e-12}),
    'PD': dict(label='Рассеиваемая мощность', unit='W', display_unit='W', units={'W': 1, 'mW': .001}),
    'TRR': dict(label='Время обратного восстановления', unit='s', display_unit='ns', units={'s': 1, 'ms': .001, 'µs': .000001, 'ns': 1e-9}),
}
KINDS = {'min', 'typ', 'max', 'unspecified'}
RATING_CODES = {'VRRM', 'VRMS', 'VDC', 'IF_AV', 'IFSM', 'PD'}


def symbol_code(symbol):
    import re
    cleaned = re.sub(r'\s+', '', symbol or '').upper()
    return {'IF(AV)': 'IF_AV', 'P_TOT': 'PD', 'PTOT': 'PD', 'P_D': 'PD'}.get(cleaned, cleaned) if cleaned else ''


def canonical_unit(unit):
    return (unit or '').strip().replace('μ', 'µ').replace('uA', 'µA').replace('uF', 'µF').replace('us', 'µs')


def normalize(code, value, unit):
    unit = canonical_unit(unit)
    definition = DEFINITIONS.get(code)
    if not definition or unit not in definition['units']:
        raise ValueError('Неизвестная характеристика или неподходящая единица измерения')
    return value * definition['units'][unit], definition['unit']
