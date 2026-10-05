# Формат карты сигналов (canmap, v1)

Карта — это YAML-файл. Из него генерируются все документы и код. JSON Schema формата
лежит в [`schema/canmap.schema.json`](../schema/canmap.schema.json): если в первой строке
файла указать

```yaml
# yaml-language-server: $schema=./schema/canmap.schema.json
```

VS Code с расширением *YAML* (Red Hat) будет подсказывать поля и подчёркивать ошибки.

## Соглашения

| Что | Правило |
|---|---|
| Нумерация байт | с 0 |
| Нумерация бит | `lsb0`: бит 0 — младший бит байта 0; бит `N` лежит в байте `N div 8` на позиции `N mod 8` |
| Позиция сигнала | `start_bit` — позиция **младшего** бита значения |
| Физическая величина | `physical = raw * factor + offset` |
| Числа | десятичные или `0x…`; дробная часть — через точку (`0.1`, не `0,1`) |
| Имена | латиница, цифры и `_` (идентификаторы C/Python). Стиль задаётся в `lint` |

Нумерация фиксируется полем `document.bit_numbering: lsb0` и выводится во всех документах.

## Структура файла

```yaml
canmap: 1                 # версия формата
document: {...}           # метаданные и история изменений
lint: {...}               # правила стиля (необязательно)
buses: [...]              # одна или несколько шин
```

### document

| Поле | Тип | Описание |
|---|---|---|
| `title` | текст | Название документа (обязательно) |
| `subtitle` | текст | Подзаголовок |
| `version` | строка | Версия карты |
| `date` | дата `YYYY-MM-DD` | Дата выпуска |
| `author`, `organization` | строка | |
| `language` | `ru` \| `en` | Язык документов (по умолчанию `ru`) |
| `bit_numbering` | `lsb0` | Явная фиксация нумерации бит |
| `history` | список | `{version, date, author, github, changes: [текст, ...]}`; `github` — имя пользователя GitHub автора |

**Текст** — строка или объект с переводами: `{ru: "Состояние", en: "State"}`.

### lint

```yaml
lint:
  signal_name: snake_case     # snake_case | UPPER_SNAKE | camelCase | PascalCase | any
  frame_name: snake_case
  device_name: snake_case
  value_name: UPPER_SNAKE
  disable: [missing-description]   # отключить правила по коду
```

### Шина (`buses[]`)

| Поле | Описание |
|---|---|
| `name` | Идентификатор шины (имя файлов DBC/C) |
| `title` | Название в документах («Шина 1») |
| `interface` | Интерфейс (`can0`, `PCAN_USBBUS1`…) |
| `bitrate` | Скорость, бит/с |
| `protocol` | `canopen` — ID вычисляются из функционального кода и `node_id`; `can` — ID задаются явно |
| `fd` | `true` для CAN FD (DLC до 64) |
| `frames` | Широковещательные кадры без владельца (`nmt`, `sync`, `time`) |
| `devices` | Устройства |

### Устройство (`devices[]`)

| Поле | Описание |
|---|---|
| `name` | Идентификатор (`imd`) |
| `short` | Короткое обозначение для таблиц (`BMS`) |
| `title` | Полное название |
| `node_id` | Адрес CANopen (1..127) |
| `description` | Описание |
| `frames` | Кадры, которыми обменивается устройство |

### Кадр (`frames[]`)

| Поле | Описание |
|---|---|
| `name` | Идентификатор кадра (уникален на шине) |
| `title` | Короткий заголовок («СОСТОЯНИЯ») |
| `description` | Назначение кадра |
| `type` | `nmt`, `sync`, `emcy`, `time`, `pdo_tx1..4`, `pdo_rx1..4`, `sdo_tx`, `sdo_rx`, `heartbeat`, `raw` |
| `id` | Явный CAN ID (обязателен для `raw` и шин `can`; для CANopen переопределяет вычисленный) |
| `extended` | 29-битный ID |
| `dlc` | Длина данных (по умолчанию 8) |
| `direction` | `tx` / `rx` относительно устройства. По умолчанию из типа: `pdo_tx*`, `sdo_tx`, `emcy`, `heartbeat` — `tx`; `pdo_rx*`, `sdo_rx`, `nmt` — `rx` |
| `cycle_ms` | Сокращение для `transmission: {mode: cyclic, cycle_ms: …}` |
| `transmission` | `{mode: cyclic \| event \| on_request, cycle_ms}` |
| `signals` | Сигналы |
| `sdo` | Описание SDO-обменов (для `sdo_tx`/`sdo_rx`) |
| `comment` | Примечание |

Вычисление ID для CANopen:

| Тип | ID |
|---|---|
| `nmt` | `0x000` |
| `sync` | `0x080` |
| `emcy` | `0x080 + node_id` |
| `time` | `0x100` |
| `pdo_tx1` / `pdo_rx1` | `0x180` / `0x200` `+ node_id` |
| `pdo_tx2` / `pdo_rx2` | `0x280` / `0x300` `+ node_id` |
| `pdo_tx3` / `pdo_rx3` | `0x380` / `0x400` `+ node_id` |
| `pdo_tx4` / `pdo_rx4` | `0x480` / `0x500` `+ node_id` |
| `sdo_tx` / `sdo_rx` | `0x580` / `0x600` `+ node_id` |
| `heartbeat` | `0x700 + node_id` |

### Сигнал (`signals[]`)

| Поле | Описание |
|---|---|
| `name` | Идентификатор (уникален в кадре вместе с именами флагов) |
| `description` | Описание |
| `kind` | `enum`, `flag`, `bitfield`, `metric`, `raw`, `bytes`. Если не задан: есть `values` → `enum`, есть `flags` → `bitfield`, есть `factor`/`offset`/`unit` → `metric`, иначе `raw` |
| `start_bit` + `bit_length` | Каноническая позиция |
| `byte` [+ `bit`] [+ `byte_length` \| `bit_length`] | Сокращённая запись (см. ниже) |
| `byte_order` | `little_endian` (по умолчанию) или `big_endian` |
| `signed` | Знаковое значение (дополнительный код) |
| `values` | Таблица значений: `{0: NO_DATA, 1: {name: OK, description: "в норме"}}` |
| `value_format` | `dec` \| `hex` — как показывать значения в документах |
| `flags` | Флаги битового поля: `{bit, bit_length: 1, name, description, values}`; `bit` — смещение от младшего бита поля |
| `factor`, `offset`, `unit`, `min`, `max` | Физическое преобразование и диапазон (в физических единицах) |
| `multiplexer` | `true` — сигнал-селектор мультиплексора |
| `mux` | Значение (или список) селектора, при котором сигнал присутствует |
| `comment` | Примечание |

#### Сокращённая запись позиции

| Запись | Эквивалент |
|---|---|
| `byte: 2` | `start_bit: 16, bit_length: 8` |
| `byte: 1, byte_length: 2` | `start_bit: 8, bit_length: 16` |
| `byte: 1, bit: 3` | `start_bit: 11, bit_length: 1` |
| `byte: 2, bit: 4, bit_length: 4` | `start_bit: 20, bit_length: 4` |
| `byte: 1, byte_length: 2, byte_order: big_endian` | `start_bit: 16, bit_length: 16` — старший байт в байте 1 |

Одновременно указывать `start_bit` и `byte`/`bit` нельзя.

#### Big-endian

Для `big_endian` (Motorola) `start_bit` — тоже позиция младшего бита. От него значение идёт к старшим
битам байта, а затем продолжается с бита 0 *предыдущего* байта. При записи `byte:` указывается первый
(старший) байт поля — так, как его обычно читают в таблице.

#### Мультиплексирование

```yaml
signals:
  - name: parse_type
    byte: 0
    bit: 0
    multiplexer: true
    values: {0: VOLTAGES, 1: TEMPERATURES}
  - {name: voltage_data,     byte: 1, byte_length: 7, kind: bytes, mux: 0}
  - {name: temperature_data, byte: 1, byte_length: 7, kind: bytes, mux: 1}
```

Сигналы с разными `mux` могут занимать одни и те же биты — это не считается пересечением.
Сигнал без `mux` присутствует при любом значении селектора.

### SDO (`sdo[]`)

Для кадров `sdo_rx`/`sdo_tx` вместо `signals` можно описать обмены (expedited SDO):

```yaml
- name: imd_sdo_request
  type: sdo_rx
  sdo:
    - name: set_alarm_resistance
      description: Установка ALARM_RESISTANCE
      command: 0x2B          # CCS: запись 2 байт
      index: 0x4010
      subindex: 0x01
      value: {name: alarm_resistance, bit_length: 16, unit: кОм}
```

canmap построит раскладку кадра сам: байт 0 — команда, байты 1–2 — индекс (little-endian),
байт 3 — субиндекс (селектор мультиплексора, если индекс один), байты 4–7 — значение.

## Ссылки YAML

Повторяющиеся таблицы значений удобно описывать якорями:

```yaml
values: &dc_states
  0: STATE_INIT
  1: STATE_PRECHARGE
...
values: *dc_states
```

## Правила проверки

Полный список — `canmap rules`. Уровни: **error** (генерация прерывается, код возврата 1),
**warning** (код 1 только с `--strict`), **info** (показывается с `--info`).

| Код | Уровень | Что проверяется |
|---|---|---|
| `yaml` | error | синтаксис YAML, повторяющиеся ключи |
| `schema` | error | структура: типы, обязательные поля, неизвестные поля, допустимые значения |
| `number-comma` | error | `0,1` вместо `0.1` |
| `number-cyrillic-x` | error | кириллическая «х» в `0х196` |
| `number-quoted` | warning | число в кавычках (`"0x196"`) |
| `invalid-identifier` | error | имя нельзя использовать в коде (`NO DATA`) |
| `name-style` | warning | имя не в стиле из `lint` |
| `name-inconsistent` | warning | одно и то же значение записано по-разному (`NO DATA` / `NO_DATA`) |
| `duplicate-signal-name` | error | повтор имени сигнала или флага в кадре |
| `duplicate-enum-name` | warning | одно имя у разных значений enum |
| `duplicate-can-id` | error | повтор CAN ID на шине |
| `duplicate-frame-name`, `duplicate-device-name`, `duplicate-node-id` | error | повторы на шине |
| `node-id-range`, `can-id-range`, `dlc-range` | error | выход за допустимые диапазоны |
| `frame-id-missing` | error | ID нельзя вычислить (нет `node_id` или `id`) |
| `signal-out-of-frame` | error | сигнал выходит за DLC |
| `bit-overlap` | error | пересечение сигналов по битам (с учётом `mux`) |
| `enum-overflow` | error | значение не помещается в разрядность поля |
| `flag-out-of-field`, `flag-overlap`, `flags-kind`, `flag-length` | error/warning | битовые поля |
| `metric-factor`, `metric-range`, `min-max` | error/warning | физическое преобразование |
| `mux-no-selector`, `mux-multiple-selectors`, `mux-value-overflow`, `mux-value-unknown`, `mux-selector-muxed` | error/warning | мультиплексирование |
| `cycle-missing`, `cycle-unexpected` | error/warning | режим передачи |
| `direction-mismatch`, `frame-type-protocol` | warning | согласованность типа кадра |
| `sdo-frame-type`, `sdo-duplicate` | warning/error | описание SDO |
| `missing-description`, `empty-frame` | info | полнота описания |
