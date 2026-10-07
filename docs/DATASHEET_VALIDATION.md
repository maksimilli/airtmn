# Проверка распознавания data1.zip

Проверены **47 PDF, 810 страниц**. Каждый исходный файл прошёл настоящий `POST /api/import`, затем сохранение карточки и повторное чтение из временной базы. Совпали **99 контрольных значений**, выбранных по исходным PDF. Проверка выполнялась с автоматическим OCR; файлы производителей не включены в репозиторий.

Это проверка конкретных чисел и работоспособности импорта, а не утверждение, что извлечена каждая строка каждого PDF. Сайт автоматически заполняет поддерживаемые характеристики; словарь содержит **58 типов параметров**. Часть документов содержит семейство моделей — перед сохранением нужно выбрать нужную. Число моделей в таблице включает общую запись семейства, если она есть.

## Что исправлено

- Чтение MIN/TYP/MAX без обязательной колонки SYMBOL, таблиц без линий и таблиц PARAMETER/SPECIFICATIONS.
- Каталоги с моделями в строках, объединённые ячейки и отдельные блоки заголовка/тела. Значения остаются привязаны к модели.
- Обозначения VR, IF, IFRM, VBR, VCL, IPP; ток пульсаций, шаг и число контактов, импеданс, параметры усилителей, трансформаторов и изоляторов.
- Повреждённые единицы в текстовом слое проходят OCR: потерянный знак µ не превращает микроамперы в амперы.
- Название самого компонента имеет приоритет перед резисторами и конденсаторами, упомянутыми в схемах. Внешние компоненты из схем DSP не становятся моделями DSP.
- Порог UVLO отличается от напряжения питания; ток земли — от выходного тока; напряжения EN/SS — от входного питания.

## Результаты по файлам

«Полей» — число значений выбранной модели, а не число всех строк в PDF. Контрольные числа ниже показаны в удобных единицах. Проверяется также тип min/typ/max там, где он задан в контрольном наборе.

| PDF | Выбранная модель | Полей | Моделей | Контрольные значения |
| --- | --- | ---: | ---: | --- |
| FCI_SFW8R-2STAE1LF_SFW24R-1STAE1LF.pdf | SFW4R-1/2STA_ -LF | 2 | 55 | PITCH: 1 mm; PINS: 4 |
| Murata — NTE Series | NTE0303MC | 4 | 16 | VIN: 3.3 V; VOUT: 3.3 V; IOUT: 0.303 A |
| Murata — BLM18 | BLM18RK121SN1D | 4 | 155 | Z typ: 120 Ω; IRATED: 0.2 A; DCR max: 0.25 Ω |
| NXP_74LVC138A.pdf | 74LVC138A | 5 | 1 | VCC min: 1.65 V |
| NXP_BAT54S_.pdf | BAT54S | 13 | 1 | VR max: 30 V; IF max: 0.2 A; VF max: 0.4 V |
| NXP_BAT54XY.pdf | BAT54XY | 14 | 1 | VR max: 30 V; IF max: 0.2 A; VF max: 0.4 V |
| Nicomatic_221VxxF23.pdf | 221VxxF23 | 1 | 1 | PITCH: 2 mm |
| Nicomatic_221YnnF22.pdf | 221YNNF22 | 1 | 1 | PITCH: 2 mm |
| Nicomatic_222SnnM11.pdf | 222SNNM11 | 1 | 1 | PITCH: 2 mm |
| Nicomatic_222VnnM21.pdf | 222VNNM21 | 1 | 1 | PITCH: 2 mm |
| Nicomatic_222YnnM12.pdf | 222YNNM12 | 1 | 1 | PITCH: 2 mm |
| Nicomatic_222YnnM12H.pdf | 222YNNM12H | 1 | 1 | PITCH: 2 mm |
| On_Semiconductor_nc7sz332p6x.PDF | NC7SZ332 | 14 | 1 | VCC min: 1.65 V; VCC max: 5.5 V |
| Panasonic_TPE.pdf | 10TPE47MAZB | 5 | 81 | VRATED: 10 V; C: 47 µF; ESR max: 0.035 Ω; IR max: 47 µA; IRIPPLE max: 1.4 A |
| Para Light_L-C150xx_170_191_192.pdf | L-C150GCT | 2 | 32 | VF typ: 2.1 V; VF max: 2.6 V |
| Pulse Electronic_hx5014nl.pdf | HX5014NL | 4 | 1 | L min: 350 µH; DCR max: 0.65 Ω; TURN_RATIO: 1; VISOL min: 1500 V |
| ST-Microelectronics_1.5ke.pdf | 1.5KE6V8A/CA | 10 | 30 | VR max: 5.8 V; VCL max: 10.5 V; IPP max: 143 A |
| ST-Microelectronics_L3GD20H.pdf | L3GD20H | 4 | 1 | VCC min: 2.2 V; VCC max: 3.6 V; ICC typ: 5 mA |
| ST-Microelectronics_ST8R00WPUR.pdf | ST8R00WPUR | 4 | 1 | VIN min: 4 V; VIN max: 6 V |
| Samtec_CLE-107-01-G-DV.pdf | CLE-107-01-G-DV | 2 | 1 | IRATED: 0.75 A; CONTACT_R max: 15 mΩ |
| Silicon Laboratories_Si8422BB-D-IS.pdf | SI8422BB-D-IS | 34 | 1 | UVLO typ: 2.3 V; VHYST typ: 0.075 V |
| Silicon Laboratories_Si8661.pdf | SI8661 | 34 | 1 | VCC min: 2.5 V; VCC max: 5.5 V |
| TDK_ACH32C-103-T.pdf | ACH32C-103-T001 | 2 | 25 | VRATED: 50 V; IRATED: 6 A |
| TE Connectivity_5173279-3.pdf | 5173279-3 | 1 | 1 | PINS: 50 |
| TE Connectivity_5173280-3.pdf | 5173280-3 | 2 | 1 | PINS: 50 |
| TE Connectivity_MCX ELBOW PCB SOCKET 50 OHMS.pdf | MCX ELBOW PCB SOCKET 50 OHMS | 1 | 1 | Z: 50 Ω |
| TE Connectivity_MCX RF 1-1337585-0.pdf | MCX RF 1-1337585-0 | 1 | 1 | Z: 50 Ω |
| Texas Instruments_LMZ23603TZ.pdf | LMZ23603TZ | 4 | 1 | VIN min: 6 V; VIN max: 36 V |
| Texas Instruments_LP2985.pdf | LP2985AIM5X-2.5 | 1 | 160 | VOUT: 2.5 V |
| Texas Instruments_OPA1632.pdf | OPA1632 | 8 | 1 | VCC min: 5 V; VCC max: 30 V; SR typ: 50 V/µs |
| Texas Instruments_SN65HVD251.pdf | SN65HVD251 | 8 | 1 | VCC min: 4.5 V; VCC max: 5.5 V |
| Texas Instruments_SN65HVD3083E.pdf | SN65HVD3083E | 6 | 1 | VCC min: 4.5 V |
| Texas Instruments_SN74LVC2G04.pdf | SN74LVC2G04 | 7 | 1 | VCC min: 1.65 V; VCC max: 5.5 V; ICC max: 0.01 mA |
| Texas Instruments_sn65hvd233.pdf | SN65HVD233 | 8 | 1 | ICC max: 0.6 mA |
| Texas Instruments_sn74lvc1g08.pdf | SN74LVC1G08 | 9 | 1 | VCC min: 1.65 V; VCC max: 5.5 V |
| Texas Instruments_sn74lvc1t45.pdf | SN74LVC1T45 | 7 | 1 | VIN max: 5.5 V |
| Texas Instruments_sn74lvc3g07.pdf | SN74LVC3G07 | 12 | 1 | VCC min: 1.65 V; VCC max: 5.5 V |
| Texas Instruments_tms320f28335.pdf | TMS320F28335 | 2 | 1 | VCC max: 3.465 V |
| Texas Instruments_tps3828-33.pdf | TPS3828-33 | 7 | 1 | VCC min: 1.1 V; VCC max: 5.5 V |
| Texas Instruments_tps386000.pdf | TPS386000 | 6 | 1 | VCC min: 1.8 V; VCC max: 6.5 V; ICC typ: 0.011 mA |
| Texas Instruments_tps51100.pdf | TPS51100 | 10 | 1 | VIN min: 4.75 V; VIN max: 5.25 V |
| Texas Instruments_tps62000-008.pdf | TPS6200X | 6 | 1 | VCC min: 2 V; VCC max: 5.5 V |
| Texas Instruments_tps7a7200.pdf | TPS7A7200 | 11 | 1 | VIN min: 1.425 V; VIN max: 6.5 V; IGND typ: 2.6 mA |
| Traco Electronic AG_TEN8.pdf | TEN 8-1210 | 5 | 21 | VIN min: 9 V; VIN max: 18 V; VOUT: 3.3 V; IOUT max: 2 A |
| Traco Electronic AG_tck-050.pdf | TCK-050 | 3 | 1 | L: 325 µH; DCR max: 0.035 Ω; IRATED max: 3.3 A |
| Traco Electronic AG_tme.pdf | TME 0303S | 4 | 15 | VIN: 3.3 V; VOUT: 3.3 V; IOUT max: 0.26 A |
| Traco Electronic AG_tmr3.pdf | TMR 3-0510 | 5 | 28 | VIN min: 4.5 V; VIN max: 9 V; VOUT: 3.3 V; IOUT max: 0.7 A |

## Что ещё проверено

- 42 автоматических теста сервера и 3 теста обработки чисел интерфейса — прошли.
- TypeScript и сборка интерфейса — прошли; внешний вид не менялся.
- Прежний пользовательский Vishay 1n4001.pdf: 7 моделей × 12 характеристик, цифровой разбор сохранён.
- В Chromium: выбор 8TPE100MAZB из 81 модели Panasonic, автоматические поля 8 V / 100 µF / 80 µA / 0.035 Ω / 1.4 A, сохранение и восстановление после перезагрузки.
- В Chromium: BAT54XY в разделе резисторов блокируется до записи PDF; число документов и карточек остаётся прежним.

## Как повторить проверку

Распакуйте исходный data1.zip. Из корня репозитория с установленными зависимостями:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/verify_datasheets.py /путь/к/даташитам --output /tmp/datasheet-report.json
```

PowerShell на Windows (путь к виртуальной среде выберите тот, который создал START_WINDOWS.bat):

```powershell
$env:PYTHONPATH="backend"
.\.venv-windows-312\Scripts\python.exe backend\scriptserify_datasheets.py "C:\путь\к\даташитам" --output datasheet-report.json
```

SHA-256 каждого исходного файла указан в `backend/tests/data1_expected.json`: проверка работает и после переименования PDF. Значения в манифесте заданы заранее, а не формируются из текущего результата парсера. Скрипт создаёт отдельную временную базу и не использует папку data пользователя. Отсутствующий исходный файл или несовпадение контрольного числа завершает проверку с ошибкой.

## Практические ограничения

Гарантии распознавания любого PDF нет. В этой версии не извлекаются все графики, температурные диапазоны, формулы и специфические параметры вне словаря. Нечитаемый скан, повреждённый шрифт или нестандартная таблица могут дать пропуски. Для неполного чертежа нельзя восстановить отсутствующий электрический номинал.

У даташита ST 1.5KE подписи MIN/MAX для VBR противоречат числам: минимум оказывается больше максимума. Парсер сохраняет подписи оригинала и выводит предупреждение; проверенные VCL и IPP соответствуют своим колонкам и длительности импульса. Общая строка A/CA не разделена на две вымышленные модели: ёмкость двунаправленного варианта требует учёта примечания производителя.

Базовые ограничения остаются: PDF до 20 МБ и 200 страниц, автоматический OCR до 10 страниц. Предупреждения перечисляют пропуски. Полный запуск пакета на настоящей Windows здесь не выполнялся; используется прежний проверенный механизм запуска с Python 3.12.

