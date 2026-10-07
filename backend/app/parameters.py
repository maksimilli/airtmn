"""Canonical electrical parameter definitions and unit conversions."""
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
def definition(label, unit, units=None, display_unit=None):
    return dict(label=label, unit=unit, display_unit=display_unit or unit, units=units or {unit: 1})

VOLTAGE = {'V': 1, 'mV': .001, 'kV': 1000}
CURRENT = {'A': 1, 'mA': .001, 'µA': 1e-6}
RESISTANCE = {'Ω': 1, 'mΩ': .001, 'kΩ': 1000, 'MΩ': 1e6}
FREQUENCY = {'Hz': 1, 'kHz': 1000, 'MHz': 1e6, 'GHz': 1e9}
DEFINITIONS.update({
    'VDS': definition('Напряжение сток–исток', 'V', VOLTAGE),
    'ID': definition('Ток стока', 'A', CURRENT),
    'VGS': definition('Напряжение затвор–исток', 'V', VOLTAGE),
    'RDS_ON': definition('Сопротивление открытого канала', 'Ω', RESISTANCE, 'mΩ'),
    'VGS_TH': definition('Пороговое напряжение затвора', 'V', VOLTAGE),
    'CISS': definition('Входная ёмкость', 'F', {'F':1,'µF':1e-6,'nF':1e-9,'pF':1e-12}, 'pF'),
    'VCEO': definition('Напряжение коллектор–эмиттер', 'V', VOLTAGE),
    'VCBO': definition('Напряжение коллектор–база', 'V', VOLTAGE),
    'VEBO': definition('Напряжение эмиттер–база', 'V', VOLTAGE),
    'IC': definition('Ток коллектора', 'A', CURRENT),
    'HFE': definition('Коэффициент усиления по току', '1', {'1':1}),
    'VCE_SAT': definition('Напряжение насыщения', 'V', VOLTAGE),
    'FT': definition('Граничная частота', 'Hz', FREQUENCY, 'MHz'),
    'R': definition('Сопротивление', 'Ω', RESISTANCE, 'kΩ'),
    'C': definition('Ёмкость', 'F', {'F':1,'mF':.001,'µF':1e-6,'nF':1e-9,'pF':1e-12}, 'µF'),
    'TOL': definition('Допуск', '%'),
    'VRATED': definition('Номинальное напряжение', 'V', VOLTAGE),
    'IRATED': definition('Номинальный ток', 'A', CURRENT),
    'ESR': definition('Эквивалентное последовательное сопротивление', 'Ω', RESISTANCE),
    'L': definition('Индуктивность', 'H', {'H':1,'mH':.001,'µH':1e-6,'nH':1e-9}, 'µH'),
    'ISAT': definition('Ток насыщения', 'A', CURRENT),
    'DCR': definition('Сопротивление постоянному току', 'Ω', RESISTANCE),
    'PINS': definition('Число контактов', '1'),
    'CONTACT_R': definition('Сопротивление контакта', 'Ω', RESISTANCE, 'mΩ'),
    'VCC': definition('Напряжение питания', 'V', VOLTAGE),
    'ICC': definition('Ток потребления', 'A', CURRENT, 'mA'),
    'FREQ': definition('Рабочая частота', 'Hz', FREQUENCY, 'MHz'),
    'VIN': definition('Входное напряжение', 'V', VOLTAGE),
    'VOUT': definition('Выходное напряжение', 'V', VOLTAGE),
    'IOUT': definition('Выходной ток', 'A', CURRENT),
    'POUT': definition('Выходная мощность', 'W', {'W':1,'mW':.001}),
    'EFF': definition('КПД', '%'),
})
KINDS = {'min', 'typ', 'max', 'unspecified'}
RATING_CODES = {'VRRM', 'VRMS', 'VDC', 'IF_AV', 'IFSM', 'PD', 'VDS', 'ID', 'VGS', 'VCEO', 'VCBO', 'VEBO', 'IC', 'VRATED', 'IRATED', 'ISAT', 'VIN', 'VCC'}
ALIASES = {'IF(AV)': 'IF_AV', 'P_TOT': 'PD', 'PTOT': 'PD', 'P_D':'PD', 'RDS(ON)':'RDS_ON',
           'VGS(TH)':'VGS_TH','VCE(SAT)':'VCE_SAT','V(BR)CEO':'VCEO','V(BR)DS':'VDS', 'H_FE':'HFE'}


def symbol_code(symbol):
    import re
    cleaned = re.sub(r'\s+', '', symbol or '').upper()
    return ALIASES.get(cleaned, cleaned) if cleaned else ''


def canonical_unit(unit):
    cleaned = (unit or '').strip().replace('Ω','Ω').replace('μ', 'µ').replace('uA', 'µA').replace('uF', 'µF').replace('us', 'µs').replace('uH','µH')
    return {'ohm':'Ω','Ohm':'Ω','Ohms':'Ω','ohms':'Ω','mohm':'mΩ','kohm':'kΩ','Mohm':'MΩ','-':'1','':'1','—':'1'}.get(cleaned,cleaned)


def normalize(code, value, unit):
    unit = canonical_unit(unit)
    definition = DEFINITIONS.get(code)
    if not definition or unit not in definition['units']:
        raise ValueError('Неизвестная характеристика или неподходящая единица измерения')
    return value * definition['units'][unit], definition['unit']
