# Эталонная карта CANopen

_Протокол обмена демонстрационной системы питания_

| Версия | Дата |
|---|---|
| 1.0.0 | 2026-10-05 |

> Нумерация байт и бит начинается с 0. Бит 0 — младший бит байта 0; бит N находится в байте N div 8 на позиции N mod 8.

<!-- Сформировано mapcan. Не редактируйте вручную: источник — YAML-карта. -->

## Содержание документа

- [Шина 1](#bus1)
  - [IMD 0x21 — Монитор изоляции](#bus1-imd)
  - [CMU 0x22 — Модуль контроля ячеек](#bus1-cmu)
  - [PCU 0x23 — Блок преобразователя](#bus1-pcu)
  - [BYP 0x24 — Блок управления байпасом](#bus1-bypass)
  - [COOL 0x25 — Система охлаждения](#bus1-cooling)
- [Шина 2](#bus2)
  - [HOST — Контроллер верхнего уровня](#bus2-host)
  - [PSM — Модуль управления системой питания](#bus2-psm)
- [История изменений](#history)

<a id="bus1"></a>

## Шина 1

Внутренняя шина системы питания (CANopen, predefined connection set).

**Протокол:** CANopen · **Скорость:** 500 кбит/с · **Разъём:** X1

### Адресация

| Тип сообщения | Устройство | ID | Назначение |
|---|---|---|---|
| **SYNC** `0x080` | Вне карты | `0x080` | Синхронизация со всеми устройствами |
| **EMCY** `0x080` | CMU 0x22 | `0x0A2` | Изменение состояния |
| **TIME** `0x100` | Вне карты | `0x100` | Дата и время |
| **PDO TX 1** `0x180` | IMD 0x21 | `0x1A1` | Состояние изоляции |
| **PDO TX 1** `0x180` | CMU 0x22 | `0x1A2` | Состояние ячеек |
| **PDO TX 1** `0x180` | PCU 0x23 | `0x1A3` | Состояние преобразователя |
| **PDO RX 1** `0x200` | IMD 0x21 | `0x221` | Команды монитору изоляции |
| **PDO RX 1** `0x200` | CMU 0x22 | `0x222` | Объём передаваемых данных |
| **PDO RX 1** `0x200` | PCU 0x23 | `0x223` | Установка режима работы преобразователя |
| **PDO RX 1** `0x200` | BYP 0x24 | `0x224` | Установка режима работы байпаса |
| **PDO RX 1** `0x200` | COOL 0x25 | `0x225` | Установка скорости вентиляторов и положения заслонок |
| **PDO TX 2** `0x280` | IMD 0x21 | `0x2A1` | Данные по изоляции |
| **PDO TX 2** `0x280` | CMU 0x22 | `0x2A2` | Парсинг данных (по запросу) |
| **PDO TX 2** `0x280` | PCU 0x23 | `0x2A3` | Данные о работе |
| **PDO TX 2** `0x280` | BYP 0x24 | `0x2A4` | Текущий режим работы ключа и состояние ошибки |
| **PDO TX 2** `0x280` | COOL 0x25 | `0x2A5` | Скорость вентиляторов и положение заслонок |
| **SDO TX** `0x580` | IMD 0x21 | `0x5A1` | Обратная связь по принятой настройке |
| **SDO RX** `0x600` | IMD 0x21 | `0x621` | Настройка граничных значений |

<a id="bus1-broadcast"></a>

### Вне карты

#### `0x080` SYNC

Синхронизация со всеми устройствами

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `sync` | `0x080` | SYNC | 0 |  | по событию |

_Сигналы не описаны._

#### `0x100` TIME

Дата и время

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `time_stamp` | `0x100` | TIME | 6 |  | по событию |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">ms_after_midnight</td></tr>
<tr><th>1</th><td colspan="8" align="center">ms_after_midnight</td></tr>
<tr><th>2</th><td colspan="8" align="center">ms_after_midnight</td></tr>
<tr><th>3</th><td colspan="4" align="center">·</td><td colspan="4" align="center">ms_after_midnight</td></tr>
<tr><th>4</th><td colspan="8" align="center">days_since_1984</td></tr>
<tr><th>5</th><td colspan="8" align="center">days_since_1984</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0–3 | 0–27 | `ms_after_midnight` | Миллисекунды с начала суток | 28 бит<br>мс<br>little-endian |  |
| 4–5 | 32–47 | `days_since_1984` | Дни с 1 января 1984 г. | uint16<br>сут<br>little-endian |  |

<a id="bus1-imd"></a>

### IMD 0x21 — Монитор изоляции

Контроль сопротивления изоляции шины питания относительно корпуса.

**Принимает**

| ID | Кадр | Отправитель | Описание |
|---|---|---|---|
| `0x221` | `imd_command` | — | Команды монитору изоляции |
| `0x621` | `imd_sdo_request` | — | Настройка граничных значений |

#### `0x1A1` СОСТОЯНИЯ

Состояние изоляции

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `imd_state` | `0x1A1` (0x180 + node_id) | PDO TX 1 | 3 | TX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">insulation_status</td></tr>
<tr><th>1</th><td colspan="4" align="center">internal_error</td><td colspan="1" align="center">self_test_error</td><td colspan="1" align="center">anomaly_error</td><td colspan="1" align="center">timeout_error</td><td colspan="1" align="center">low_bus_voltage_error</td></tr>
<tr><th>2</th><td colspan="8" align="center">imd_state</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `insulation_status` | Статус изоляции | uint8 | 0 – NO_DATA (нет данных о сопротивлении изоляции)<br>1 – OK (сопротивление изоляции в норме)<br>2 – WARNING (низкое сопротивление изоляции: меньше WARNING_RESISTANCE, но больше ALARM_RESISTANCE)<br>3 – ALARM (аварийно-низкое сопротивление изоляции, меньше ALARM_RESISTANCE) |
| 1 | 8–15 | `internal_error` | Статус внутренней ошибки | битовое поле | бит 0 – LOW_BUS_VOLTAGE_ERROR (низкое напряжение шины)<br>бит 1 – TIMEOUT_ERROR (тайм-аут измерения)<br>бит 2 – ANOMALY_ERROR (аномальное состояние между шинами питания и корпусом — может указывать на периодический контакт шины с корпусом)<br>бит 3 – SELF_TEST_ERROR (ошибка самопроверки) |
| 2 | 16–23 | `imd_state` | Состояние работы | uint8 | 0 – NOT_WORKING (устройство не работает)<br>1 – WORKING (устройство работает)<br>2 – CRITICAL_FAULT (критический сбой в работе устройства) |

#### `0x2A1` ДАННЫЕ

Данные по изоляции

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `imd_data` | `0x2A1` (0x280 + node_id) | PDO TX 2 | 8 | TX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">resistance_calculated</td></tr>
<tr><th>1</th><td colspan="8" align="center">resistance_plus</td></tr>
<tr><th>2</th><td colspan="8" align="center">resistance_plus</td></tr>
<tr><th>3</th><td colspan="8" align="center">resistance_minus</td></tr>
<tr><th>4</th><td colspan="8" align="center">resistance_minus</td></tr>
<tr><th>5</th><td colspan="8" align="center">bus_voltage_calculated</td></tr>
<tr><th>6</th><td colspan="8" align="center">bus_voltage</td></tr>
<tr><th>7</th><td colspan="8" align="center">bus_voltage</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `resistance_calculated` | Флаг расчёта сопротивления изоляции | uint8 | 0 – NOT_CALCULATED (значения сопротивлений изоляции не рассчитаны)<br>1 – CALCULATED (значения сопротивлений изоляции рассчитаны) |
| 1–2 | 8–23 | `resistance_plus` | Изоляция между «плюсом» шины питания и корпусом | uint16<br>кОм<br>little-endian | диапазон: 0 … 10000 кОм |
| 3–4 | 24–39 | `resistance_minus` | Изоляция между «минусом» шины питания и корпусом | uint16<br>кОм<br>little-endian | диапазон: 0 … 10000 кОм |
| 5 | 40–47 | `bus_voltage_calculated` | Флаг расчёта напряжения шины питания | uint8 | 0 – NOT_CALCULATED (значение напряжения не рассчитано)<br>1 – CALCULATED (значение напряжения рассчитано) |
| 6–7 | 48–63 | `bus_voltage` | Напряжение шины питания | uint16<br>0.1 В/бит<br>little-endian |  |

#### `0x221` КОМАНДЫ

Команды монитору изоляции

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `imd_command` | `0x221` (0x200 + node_id) | PDO RX 1 | 2 | RX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">allow_work</td></tr>
<tr><th>1</th><td colspan="8" align="center">force_selftest</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `allow_work` | Команда разрешения работы устройства | uint8 | 0 – FORBID (запрет работы)<br>1 – ALLOW (разрешение работы) |
| 1 | 8–15 | `force_selftest` | Команда принудительной самодиагностики | uint8 | 0 – AUTO (запуск самодиагностики по внутреннему алгоритму)<br>1 – FORCE (принудительный запуск самодиагностики (если активно, выполняется только самодиагностика)) |

#### `0x621` НАСТРОЙКА

Настройка граничных значений

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `imd_sdo_request` | `0x621` (0x600 + node_id) | SDO RX | 8 | RX | по запросу |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">sdo_command</td></tr>
<tr><th>1</th><td colspan="8" align="center">sdo_index</td></tr>
<tr><th>2</th><td colspan="8" align="center">sdo_index</td></tr>
<tr><th>3</th><td colspan="8" align="center">sdo_subindex</td></tr>
<tr><th>4</th><td colspan="8" align="center">alarm_resistance | warning_resistance</td></tr>
<tr><th>5</th><td colspan="8" align="center">alarm_resistance | warning_resistance</td></tr>
<tr><th>6</th><td colspan="8" align="center">·</td></tr>
<tr><th>7</th><td colspan="8" align="center">·</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `sdo_command` | Команда SDO | uint8 | 0x2B – WRITE_2_BYTES |
| 1–2 | 8–23 | `sdo_index` | Индекс объекта | uint16<br>little-endian | 0x4010 – INDEX_4010 |
| 3 | 24–31 | `sdo_subindex` | Субиндекс объекта | uint8<br>селектор mux | 0x01 – SET_ALARM_RESISTANCE (Установка ALARM_RESISTANCE)<br>0x02 – SET_WARNING_RESISTANCE (Установка WARNING_RESISTANCE) |
| 4–5 | 32–47 | `alarm_resistance` | Порог аварийного сопротивления изоляции<br>_при sdo_subindex = 0x01 (SET_ALARM_RESISTANCE)_ | uint16<br>кОм<br>little-endian |  |
| 4–5 | 32–47 | `warning_resistance` | Порог предупредительного сопротивления изоляции<br>_при sdo_subindex = 0x02 (SET_WARNING_RESISTANCE)_ | uint16<br>кОм<br>little-endian |  |

**SDO-обмены**

| Сигнал | Команда | Индекс | Субиндекс | Описание | Значение |
|---|---|---|---|---|---|
| `set_alarm_resistance` | `0x2B` | `0x4010` | `0x01` | Установка ALARM_RESISTANCE | alarm_resistance: 16 биты, 1 кОм/бит |
| `set_warning_resistance` | `0x2B` | `0x4010` | `0x02` | Установка WARNING_RESISTANCE | warning_resistance: 16 биты, 1 кОм/бит |

#### `0x5A1` ОТВЕТ НА НАСТРОЙКУ

Обратная связь по принятой настройке

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `imd_sdo_response` | `0x5A1` (0x580 + node_id) | SDO TX | 8 | TX | по запросу |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">sdo_command</td></tr>
<tr><th>1</th><td colspan="8" align="center">sdo_index</td></tr>
<tr><th>2</th><td colspan="8" align="center">sdo_index</td></tr>
<tr><th>3</th><td colspan="8" align="center">sdo_subindex</td></tr>
<tr><th>4</th><td colspan="8" align="center">·</td></tr>
<tr><th>5</th><td colspan="8" align="center">·</td></tr>
<tr><th>6</th><td colspan="8" align="center">·</td></tr>
<tr><th>7</th><td colspan="8" align="center">·</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `sdo_command` | Команда SDO | uint8 | 0x60 – WRITE_OK |
| 1–2 | 8–23 | `sdo_index` | Индекс объекта | uint16<br>little-endian | 0x4010 – INDEX_4010 |
| 3 | 24–31 | `sdo_subindex` | Субиндекс объекта | uint8 | 0x01 – ACK_ALARM_RESISTANCE (Принят ALARM_RESISTANCE)<br>0x02 – ACK_WARNING_RESISTANCE (Принят WARNING_RESISTANCE) |

**SDO-обмены**

| Сигнал | Команда | Индекс | Субиндекс | Описание | Значение |
|---|---|---|---|---|---|
| `ack_alarm_resistance` | `0x60` | `0x4010` | `0x01` | Принят ALARM_RESISTANCE | — |
| `ack_warning_resistance` | `0x60` | `0x4010` | `0x02` | Принят WARNING_RESISTANCE | — |

<a id="bus1-cmu"></a>

### CMU 0x22 — Модуль контроля ячеек

**Принимает**

| ID | Кадр | Отправитель | Описание |
|---|---|---|---|
| `0x222` | `cmu_request` | — | Объём передаваемых данных |

#### `0x1A2` СОСТОЯНИЯ

Состояние ячеек

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cmu_state` | `0x1A2` (0x180 + node_id) | PDO TX 1 | 2 | TX | цикл 50 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">cmu_status</td></tr>
<tr><th>1</th><td colspan="1" align="center">systems_status</td><td colspan="1" align="center">temperature_sensor_lost</td><td colspan="1" align="center">cell_overcooling</td><td colspan="1" align="center">cell_overheat</td><td colspan="1" align="center">voltage_sensor_lost</td><td colspan="1" align="center">cell_disbalance</td><td colspan="1" align="center">cell_undervoltage</td><td colspan="1" align="center">cell_overvoltage</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `cmu_status` | Состояние работы устройства | uint8 | 0 – NO_DATA<br>1 – OK<br>2 – WARNING<br>3 – ALARM |
| 1 | 8–15 | `systems_status` | Код состояния систем | битовое поле | бит 0 – CELL_OVERVOLTAGE (высокое напряжение на ячейке)<br>бит 1 – CELL_UNDERVOLTAGE (низкое напряжение на ячейке)<br>бит 2 – CELL_DISBALANCE (разбалансировка ячеек)<br>бит 3 – VOLTAGE_SENSOR_LOST (нет связи с модулем измерения напряжения)<br>бит 4 – CELL_OVERHEAT (перегрев ячеек)<br>бит 5 – CELL_OVERCOOLING (переохлаждение ячеек)<br>бит 6 – TEMPERATURE_SENSOR_LOST (нет связи с датчиком температуры) |

#### `0x0A2` СОБЫТИЯ

Изменение состояния

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cmu_event` | `0x0A2` (0x080 + node_id) | EMCY | 3 | TX | по событию |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">event_type</td></tr>
<tr><th>1</th><td colspan="8" align="center">event_source</td></tr>
<tr><th>2</th><td colspan="8" align="center">event_object</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `event_type` | Код события | uint8 | 1 – CELL_OVERVOLTAGE (высокое напряжение на ячейке)<br>2 – CELL_UNDERVOLTAGE (низкое напряжение на ячейке)<br>3 – CELL_DISBALANCE (разбалансировка ячеек)<br>4 – VOLTAGE_SENSOR_LOST (нет связи с модулем измерения напряжения)<br>5 – CELL_OVERHEAT (перегрев ячеек)<br>6 – CELL_OVERCOOLING (переохлаждение ячеек)<br>7 – TEMPERATURE_SENSOR_LOST (нет связи с датчиком температуры) |
| 1 | 8–15 | `event_source` | Источник события | uint8 | 0 – VOLTAGE_MODULES (модули напряжения)<br>1 – TEMPERATURE_SENSORS (датчики температур) |
| 2 | 16–23 | `event_object` | Объект события — номер модуля или датчика | uint8 |  |

#### `0x2A2` ДАННЫЕ ПО НАПРЯЖЕНИЮ

Парсинг данных (по запросу)

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cmu_parse_data` | `0x2A2` (0x280 + node_id) | PDO TX 2 | 8 | TX | по запросу |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="7" align="center">parse_index</td><td colspan="1" align="center">parse_type</td></tr>
<tr><th>1</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>2</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>3</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>4</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>5</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>6</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
<tr><th>7</th><td colspan="8" align="center">voltage_data | temperature_data</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0 | `parse_type` | Тип парсинга (селектор мультиплексора) | 1 бит<br>селектор mux | 0 – VOLTAGES (парсинг напряжений)<br>1 – TEMPERATURES (парсинг температур) |
| 0 | 1–7 | `parse_index` | Номер кадра парсинга | 7 бит |  |
| 1–7 | 8–63 | `voltage_data` | Данные парсинга напряжений<br>_при parse_type = 0 (VOLTAGES)_ | 7 байт |  |
| 1–7 | 8–63 | `temperature_data` | Данные парсинга температур<br>_при parse_type = 1 (TEMPERATURES)_ | 7 байт |  |

#### `0x222` ЗАПРОСЫ

Объём передаваемых данных

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cmu_request` | `0x222` (0x200 + node_id) | PDO RX 1 | 2 | RX | по событию |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">data_request</td></tr>
<tr><th>1</th><td colspan="8" align="center">frame_request</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `data_request` | Запрос на отправку данных | uint8 | 0 – STATES (запрос на отправку состояний)<br>1 – FULL_PARSE (запрос на полный парсинг данных)<br>2 – REPEAT_VOLTAGE_FRAME (повтор определённого кадра парсинга напряжения)<br>3 – REPEAT_TEMPERATURE_FRAME (повтор определённого кадра парсинга температуры) |
| 1 | 8–15 | `frame_request` | Номер повторно запрашиваемого кадра | uint8 |  |

<a id="bus1-pcu"></a>

### PCU 0x23 — Блок преобразователя

**Принимает**

| ID | Кадр | Отправитель | Описание |
|---|---|---|---|
| `0x223` | `pcu_command` | — | Установка режима работы преобразователя |

#### `0x1A3` СОСТОЯНИЯ

Состояние преобразователя

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `pcu_state` | `0x1A3` (0x180 + node_id) | PDO TX 1 | 2 | TX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">dc_state</td></tr>
<tr><th>1</th><td colspan="3" align="center">error_code</td><td colspan="1" align="center">err_igbt_driver</td><td colspan="1" align="center">err_overcurrent</td><td colspan="1" align="center">err_undervoltage</td><td colspan="1" align="center">err_overvoltage</td><td colspan="1" align="center">err_none</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `dc_state` | Состояние работы | uint8 | 0 – STATE_INIT (исходное состояние преобразователя)<br>1 – STATE_PRECHARGE (предзаряд входного конденсатора)<br>2 – STATE_IDLE (ключи закрыты, входной конденсатор предзаряжен, ошибок нет; ожидается команда заряда/разряда)<br>3 – STATE_CHARGE (заряд батареи)<br>4 – STATE_DISCHARGE (разряд батареи)<br>5 – STATE_DIRECT_CHARGE (батарея напрямую подключена к источнику для заряда)<br>6 – STATE_DIRECT_DISCHARGE (батарея напрямую подключена к нагрузке) |
| 1 | 8–15 | `error_code` | Код ошибки преобразователя | битовое поле | бит 0 – ERR_NONE (ошибок не обнаружено)<br>бит 1 – ERR_OVERVOLTAGE (превышение напряжения)<br>бит 2 – ERR_UNDERVOLTAGE (недопустимо малое напряжение)<br>бит 3 – ERR_OVERCURRENT (превышение тока)<br>бит 4 – ERR_IGBT_DRIVER (ошибка драйверов силовых ключей) |

#### `0x2A3` ДАННЫЕ

Данные о работе

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `pcu_data` | `0x2A3` (0x280 + node_id) | PDO TX 2 | 8 | TX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">dc_output_voltage</td></tr>
<tr><th>1</th><td colspan="8" align="center">dc_output_voltage</td></tr>
<tr><th>2</th><td colspan="8" align="center">dc_input_voltage</td></tr>
<tr><th>3</th><td colspan="8" align="center">dc_input_voltage</td></tr>
<tr><th>4</th><td colspan="8" align="center">dc_output_current</td></tr>
<tr><th>5</th><td colspan="8" align="center">dc_output_current</td></tr>
<tr><th>6</th><td colspan="8" align="center">dc_input_current</td></tr>
<tr><th>7</th><td colspan="8" align="center">dc_input_current</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0–1 | 0–15 | `dc_output_voltage` | Выходное напряжение | uint16<br>10 В/бит<br>little-endian |  |
| 2–3 | 16–31 | `dc_input_voltage` | Входное напряжение | uint16<br>10 В/бит<br>little-endian |  |
| 4–5 | 32–47 | `dc_output_current` | Выходной ток | uint16<br>10 А/бит<br>little-endian |  |
| 6–7 | 48–63 | `dc_input_current` | Входной ток | uint16<br>10 А/бит<br>little-endian |  |

#### `0x223` КОМАНДЫ

Установка режима работы преобразователя

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `pcu_command` | `0x223` (0x200 + node_id) | PDO RX 1 | 2 | RX | цикл 50 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">requested_mode</td></tr>
<tr><th>1</th><td colspan="8" align="center">target_voltage</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `requested_mode` | Запрашиваемый режим работы | uint8 | 0 – STATE_INIT (исходное состояние преобразователя)<br>1 – STATE_PRECHARGE (предзаряд входного конденсатора)<br>2 – STATE_IDLE (ключи закрыты, входной конденсатор предзаряжен, ошибок нет; ожидается команда заряда/разряда)<br>3 – STATE_CHARGE (заряд батареи)<br>4 – STATE_DISCHARGE (разряд батареи)<br>5 – STATE_DIRECT_CHARGE (батарея напрямую подключена к источнику для заряда)<br>6 – STATE_DIRECT_DISCHARGE (батарея напрямую подключена к нагрузке) |
| 1 | 8–15 | `target_voltage` | Целевое значение напряжения<br>**Примечание:** Разрядность будет уточнена в следующей версии. | uint8<br>10 В/бит |  |

<a id="bus1-bypass"></a>

### BYP 0x24 — Блок управления байпасом

**Принимает**

| ID | Кадр | Отправитель | Описание |
|---|---|---|---|
| `0x224` | `bypass_command` | — | Установка режима работы байпаса |

#### `0x224` bypass_command

Установка режима работы байпаса

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `bypass_command` | `0x224` (0x200 + node_id) | PDO RX 1 | 8 | RX |  |

_Сигналы не описаны._

#### `0x2A4` bypass_state

Текущий режим работы ключа и состояние ошибки

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `bypass_state` | `0x2A4` (0x280 + node_id) | PDO TX 2 | 8 | TX |  |

_Сигналы не описаны._

<a id="bus1-cooling"></a>

### COOL 0x25 — Система охлаждения

**Принимает**

| ID | Кадр | Отправитель | Описание |
|---|---|---|---|
| `0x225` | `cooling_command` | — | Установка скорости вентиляторов и положения заслонок |

#### `0x225` cooling_command

Установка скорости вентиляторов и положения заслонок

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cooling_command` | `0x225` (0x200 + node_id) | PDO RX 1 | 8 | RX |  |

_Сигналы не описаны._

#### `0x2A5` cooling_state

Скорость вентиляторов и положение заслонок

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `cooling_state` | `0x2A5` (0x280 + node_id) | PDO TX 2 | 8 | TX |  |

_Сигналы не описаны._

<a id="bus2"></a>

## Шина 2

Шина обмена с контроллером верхнего уровня (произвольные ID).

**Протокол:** CAN · **Скорость:** 250 кбит/с · **Разъём:** X2

### Адресация

| Устройство | ID | Назначение | Направление | Передача |
|---|---|---|---|---|
| HOST | `0x001` | Режим питания и режим работы установки | TX | цикл 100 мс |
| PSM | `0x002` | Состояние системы питания | TX | цикл 250 мс |

<a id="bus2-host"></a>

### HOST — Контроллер верхнего уровня

#### `0x001` Данные верхнего уровня

Режим питания и режим работы установки

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `host_data` | `0x001` | CAN 11 бит | 5 | TX | цикл 100 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">power_mode</td></tr>
<tr><th>1</th><td colspan="8" align="center">site_location</td></tr>
<tr><th>2</th><td colspan="8" align="center">·</td></tr>
<tr><th>3</th><td colspan="8" align="center">run_mode</td></tr>
<tr><th>4</th><td colspan="8" align="center">load_setpoint</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `power_mode` | Режим системы питания | uint8 | 1 – BATTERY (питание от батареи)<br>2 – COMBINED (совместное питание)<br>3 – BATTERY_BOOST (питание от батареи с форсированием) |
| 1 | 8–15 | `site_location` | Место установки | uint8 | 1 – LAB (лаборатория)<br>2 – INDOOR (в помещении)<br>3 – OUTDOOR (на улице) |
| 3 | 24–31 | `run_mode` | Режим работы установки<br>**Примечание:** Байт 2 зарезервирован. | uint8 | 1 – RUN (работа)<br>2 – COAST (холостой режим)<br>3 – BRAKE (торможение)<br>4 – EMERGENCY_STOP (аварийный останов) |
| 4 | 32–39 | `load_setpoint` | Уставка нагрузки (0 — ноль, 255 — максимум) | uint8 | диапазон: 0 … 255 |

<a id="bus2-psm"></a>

### PSM — Модуль управления системой питания

#### `0x002` Состояние системы

Состояние системы питания

| Кадр | ID | Тип | Длина, байт | Направление | Передача |
|---|---|---|---|---|---|
| `system_state` | `0x002` | CAN 11 бит | 5 | TX | цикл 250 мс |

<table>
<tr><th>Байт</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><th>0</th><td colspan="8" align="center">system_status</td></tr>
<tr><th>1</th><td colspan="1" align="center">cmu_high_temp</td><td colspan="1" align="center">cmu_no_volt_data</td><td colspan="1" align="center">cmu_disbalance</td><td colspan="1" align="center">cmu_low_volt</td><td colspan="1" align="center">cmu_high_volt</td><td colspan="1" align="center">cmu_alarm</td><td colspan="1" align="center">cmu_warning</td><td colspan="1" align="center">cmu_no_data</td></tr>
<tr><th>2</th><td colspan="1" align="center">imd_timeout_error</td><td colspan="1" align="center">imd_low_bus_voltage_error</td><td colspan="1" align="center">imd_alarm</td><td colspan="1" align="center">imd_warning</td><td colspan="1" align="center">imd_no_data</td><td colspan="1" align="center">cmu_link_lost</td><td colspan="1" align="center">cmu_no_temp_data</td><td colspan="1" align="center">cmu_low_temp</td></tr>
<tr><th>3</th><td colspan="1" align="center">pcu_undervoltage</td><td colspan="1" align="center">pcu_overvoltage</td><td colspan="1" align="center">pcu_no_data</td><td colspan="1" align="center">imd_link_lost</td><td colspan="1" align="center">imd_critical_fault</td><td colspan="1" align="center">imd_not_working</td><td colspan="1" align="center">imd_self_test_error</td><td colspan="1" align="center">imd_anomaly_error</td></tr>
<tr><th>4</th><td colspan="3" align="center">subsystems_states</td><td colspan="1" align="center">host_link_lost</td><td colspan="1" align="center">run_mode_no_data</td><td colspan="1" align="center">pcu_link_lost</td><td colspan="1" align="center">pcu_igbt_driver_error</td><td colspan="1" align="center">pcu_overcurrent</td></tr>
</table>

| Байт | Биты | Сигнал | Описание | Кодирование | Значения |
|---|---|---|---|---|---|
| 0 | 0–7 | `system_status` | Статус всей системы | uint8 | 0 – SYS_NO_DATA<br>1 – SYS_OK<br>2 – SYS_WARNING<br>3 – SYS_ALARM |
| 1–4 | 8–39 | `subsystems_states` | Состояния подсистем | битовое поле<br>little-endian | бит 0 – CMU_NO_DATA<br>бит 1 – CMU_WARNING<br>бит 2 – CMU_ALARM<br>бит 3 – CMU_HIGH_VOLT<br>бит 4 – CMU_LOW_VOLT<br>бит 5 – CMU_DISBALANCE<br>бит 6 – CMU_NO_VOLT_DATA<br>бит 7 – CMU_HIGH_TEMP<br>бит 8 – CMU_LOW_TEMP<br>бит 9 – CMU_NO_TEMP_DATA<br>бит 10 – CMU_LINK_LOST<br>бит 11 – IMD_NO_DATA<br>бит 12 – IMD_WARNING<br>бит 13 – IMD_ALARM<br>бит 14 – IMD_LOW_BUS_VOLTAGE_ERROR<br>бит 15 – IMD_TIMEOUT_ERROR<br>бит 16 – IMD_ANOMALY_ERROR<br>бит 17 – IMD_SELF_TEST_ERROR<br>бит 18 – IMD_NOT_WORKING<br>бит 19 – IMD_CRITICAL_FAULT<br>бит 20 – IMD_LINK_LOST<br>бит 21 – PCU_NO_DATA<br>бит 22 – PCU_OVERVOLTAGE<br>бит 23 – PCU_UNDERVOLTAGE<br>бит 24 – PCU_OVERCURRENT<br>бит 25 – PCU_IGBT_DRIVER_ERROR<br>бит 26 – PCU_LINK_LOST<br>бит 27 – RUN_MODE_NO_DATA<br>бит 28 – HOST_LINK_LOST |

<a id="history"></a>

## История изменений

| Версия | Дата | Автор | Описание |
|---|---|---|---|
| 1.0.0 | 2026-10-05 |  | Карта описана в YAML (mapcan, формат v1).<br>0x1A3: байт 1 описан как битовое поле error_code.<br>0x2A2: описано мультиплексирование данных парсинга (напряжения / температуры).<br>Нумерация бит в битовых полях приведена к счёту с 0. |
| 0.1.0 |  |  | Первая версия карты. |
