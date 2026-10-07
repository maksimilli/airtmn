"""Category-specific forms, search columns and compatible parameter codes."""
CATEGORIES = {
    'diode': dict(label='Диоды', singular='Диод', group='Полупроводники', icon='diode', codes=['VRRM','VRMS','VDC','IF_AV','IFSM','VF','IR','CJ','PD','TRR'], columns=['VRRM','IF_AV']),
    'mosfet': dict(label='Полевые транзисторы', singular='Полевой транзистор', group='Полупроводники', icon='transistor', codes=['VDS','ID','VGS','RDS_ON','VGS_TH','CISS','PD'], columns=['VDS','ID']),
    'bipolar': dict(label='Биполярные транзисторы', singular='Биполярный транзистор', group='Полупроводники', icon='transistor', codes=['VCEO','VCBO','VEBO','IC','HFE','VCE_SAT','FT','PD'], columns=['VCEO','IC']),
    'ic': dict(label='Микросхемы', singular='Микросхема', group='Полупроводники', icon='chip', codes=['VCC','ICC','FREQ','PD'], columns=['VCC','ICC']),
    'resistor': dict(label='Резисторы', singular='Резистор', group='Пассивные компоненты', icon='resistor', codes=['R','TOL','PD','VRATED'], columns=['R','PD']),
    'capacitor': dict(label='Конденсаторы', singular='Конденсатор', group='Пассивные компоненты', icon='capacitor', codes=['C','VRATED','TOL','ESR','IR'], columns=['C','VRATED']),
    'inductor': dict(label='Индуктивности', singular='Индуктивность', group='Пассивные компоненты', icon='inductor', codes=['L','IRATED','ISAT','DCR','TOL'], columns=['L','IRATED']),
    'connector': dict(label='Соединители и переключатели', singular='Соединитель', group='Другие компоненты', icon='connector', codes=['PINS','IRATED','VRATED','CONTACT_R'], columns=['PINS','IRATED']),
    'power': dict(label='Источники питания', singular='Источник питания', group='Другие компоненты', icon='power', codes=['VIN','VOUT','IOUT','POUT','EFF'], columns=['VOUT','IOUT']),
    'other': dict(label='Прочие компоненты', singular='Компонент', group='Другие компоненты', icon='box', codes=[], columns=['VRATED','IRATED']),
}


def category_codes(category):
    from app.parameters import DEFINITIONS
    return CATEGORIES[category]['codes'] or list(DEFINITIONS)
