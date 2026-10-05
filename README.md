# canmap

Утилита для создания и редактирования **карт сигналов CAN** любых устройств и систем.
Карта хранится в одном YAML-файле. Этот файл — единственный источник правды, из него
получаются документация, код для прошивок и файлы для анализаторов шины.

Поддерживаются:

* **протоколы** — CANopen (ID вычисляются из функционального кода и `node_id`), SAE J1939
  (ID из PGN, приоритета и адреса), CAN 2.0A/B с явными 11/29-битными ID, CAN FD (DLC до 64);
* **сигналы** — целые (знаковые и беззнаковые, любой длины и позиции, little/big-endian),
  перечисления, флаги и битовые поля, физические величины (`factor`, `offset`, единица,
  диапазон), float32/float64, массивы байт, мультиплексирование, значения по умолчанию и
  «нет данных»;
* **кадры** — периодичность, направление, получатели, описание SDO-обменов CANopen.

| Результат | Команда |
|---|---|
| веб-редактор: создать или открыть карту, дерево, формы, битовая карта, проверка на лету | `canmap serve` |
| проверка карты с указанием файла и строки | `canmap validate my-map.yaml` |
| Excel: адресация, содержание, битовые карты, изменения | `canmap export xlsx my-map.yaml` |
| PDF: титул, оглавление, битовые диаграммы, таблицы; шаблоны ЕСКД, ЕСПД, ГОСТ 7.32 | `canmap export pdf my-map.yaml --template gost-2.105` |
| Markdown для README/вики, HTML-страница с поиском | `canmap export md my-map.yaml`, `canmap export html my-map.yaml` |
| DBC для CANalyzer, SavvyCAN, PCAN-View, Wireshark | `canmap export dbc my-map.yaml -o dbc/` |
| C: `#define` ID, `enum`, маски, структуры, `pack`/`unpack` | `canmap gen c my-map.yaml -o firmware/` |
| Python-модуль для тестов и стендов | `canmap gen py my-map.yaml -o tools/` |
| всё сразу (для CI) | `canmap build my-map.yaml -o build/` |
| сравнение двух версий карты, changelog | `canmap diff old.yaml my-map.yaml` |

## Быстрый старт

```sh
canmap serve
```

Откроется браузер. Выберите **«Новая карта…»** и шаблон: CANopen, J1939, CAN с явными ID или
пустая карта. Дальше устройства, кадры и сигналы добавляются в дереве. Сигналы удобно
рисовать мышью на битовой карте кадра. Ошибки видны сразу, файл сохраняется по Ctrl+S.

YAML можно писать и вручную — с подсказками в VS Code по JSON Schema
(см. [docs/format.md](docs/format.md)).

## Примеры

| Файл | Что показывает |
|---|---|
| [examples/minimal.yaml](examples/minimal.yaml) | Все виды сигналов в одном кадре CANopen: enum, битовое поле, величины, big-endian |
| [examples/j1939.yaml](examples/j1939.yaml) | SAE J1939: двигатель (EEC1, ET1), панель приборов, адресный запрос PDU1, «нет данных» 0xFF/0xFFFF |
| [examples/vehicle-can.yaml](examples/vehicle-can.yaml) | CAN с явными 11/29-битными ID: float32, мультиплексированные напряжения ячеек, получатели, CAN FD с DLC 64 и float64 |
| [examples/minimal.yaml](examples/minimal.yaml) | Реальная CANopen-карта системы питания: две шины, SDO, EMCY, мультиплексор |

## Установка

Нужен Python 3.11–3.13. Внешние программы не нужны: PDF собирается встроенным
компилятором Typst из pip-пакета `typst`, шрифты PT Sans и PT Serif (OFL) идут в комплекте.

**Для пользователей** (команда `canmap` доступна глобально, обновление одной командой):

```sh
uv tool install git+<адрес репозитория>     # или: pipx install git+<адрес>
uv tool upgrade canmap
```

**Для разработки** (с [uv](https://docs.astral.sh/uv/), окружение по `uv.lock`):

```sh
uv sync
uv run canmap --help
uv run pytest
```

**Без uv**, обычным venv:

```sh
python -m venv .venv
.venv/Scripts/activate            # Linux: source .venv/bin/activate
pip install -e .
```

**Офлайн** (корпоративная сеть без PyPI): на машине с доступом собрать wheelhouse
и перенести каталог:

```sh
pip wheel . -w wheelhouse
pip install --no-index --find-links wheelhouse canmap
```

## Команды

```text
canmap serve       [FILE|DIR] [--port 8765] [--readonly] [--no-browser]
canmap validate    FILE [--strict] [--info] [--format json] [--disable КОД]
canmap export xlsx FILE [-o OUT] [--style style.yaml] [--lang en]
canmap export pdf  FILE [-o OUT] [--template canmap|gost-2.105|gost-19|gost-7.32|my.typ] [--font-path DIR]
canmap export md   FILE [-o OUT] [--template my.md.j2]
canmap export html FILE [-o OUT] [--template my.html.j2]
canmap export dbc  FILE [-o DIR|file.dbc] [--bus NAME]
canmap gen c       FILE [-o DIR] [--prefix my_] [--bus NAME]
canmap gen py      FILE [-o DIR] [--bus NAME]
canmap build       FILE [-o DIR] [--formats xlsx,pdf,md,html,dbc,c,py] [--pdf-template NAME]
canmap diff        OLD NEW [--format text|md|json]
canmap schema      [-o schema.json]
canmap template    --list | pdf [--name gost-2.105] -o FILE | md|html|xlsx-style -o FILE
canmap rules
```

Экспорт и генерация сначала проверяют карту и прерываются при ошибках
(`--force` — генерировать всё равно). `validate` возвращает код 1 при ошибках,
а с `--strict` — и при предупреждениях.

### Пример вывода проверки

```text
$ canmap validate tests/data/bad_map.yaml
tests/data/bad_map.yaml:21:25: error[number-comma]: значение '0,1': дробная часть отделена запятой, нужно 0.1
tests/data/bad_map.yaml:24:17: error[number-cyrillic-x]: значение '0х196': в префиксе 0x используется кириллическая «х»
tests/data/bad_map.yaml:33:22: error[invalid-identifier]: имя значения 'NO DATA': допустимы латинские буквы, цифры и _
tests/data/bad_map.yaml:62:36: error[duplicate-signal-name]: флаг 'dc_status' уже есть в кадре 'bup_state' (сигнал)
...
FAIL: ошибок: 12, предупреждений: 2, замечаний: 0
```

## Своё оформление

* **Excel** — `canmap template xlsx-style -o style.yaml`, правка шрифтов, цветов и набора
  колонок, затем `canmap export xlsx map.yaml --style style.yaml`.
* **PDF** — четыре встроенных шаблона: `canmap`, ЕСКД `gost-2.105` (рамка и основная
  надпись), ЕСПД `gost-19`, отчёт `gost-7.32`. Реквизиты (обозначение, литера, подписи,
  «Утверждаю», «Согласовано») и логотип предприятия задаются в `document`. Свой вариант:
  `canmap template pdf --name gost-2.105 -o corp.typ`, затем `--template corp.typ`.
  Подробнее — [docs/templates.md](docs/templates.md).
* **Markdown/HTML** — Jinja2-шаблоны, те же данные.

## Сгенерированный C-код

Для каждой шины создаются `<bus>.h` и `<bus>.c`. Без динамической памяти и libc
(только `stdint.h`, `stdbool.h`, `stddef.h`), компилируется с `-Wall -Wextra -Wconversion`
для x86 и Cortex-M. Для `examples/vehicle-can.yaml`:

```c
#include "powertrain.h"

vcu_command_t cmd = {0};
cmd.contactor_request = VCU_COMMAND_CONTACTOR_REQUEST_CLOSE;
cmd.torque_request = vcu_command_torque_request_from_phys(120.5f);   /* Н·м → raw */
uint8_t buf[8];
int dlc = vcu_command_pack(buf, sizeof buf, &cmd);                   /* → VCU_COMMAND_ID */

bms_status_t st;
if (bms_status_unpack(&st, rx_data, rx_len) == 0 && st.pack_voltage > 350.0f) { ... }
```

## Веб-редактор

```sh
canmap serve                  # стартовый экран: новая карта, открыть, недавние
canmap serve my-map.yaml      # сразу открыть карту
```

Файлы создаются, открываются и сохраняются из меню «Файл»; профиль автора (имя, GitHub)
подписывает записи истории изменений. В редакторе:
* дерево карты с поиском по имени, ID, PGN и описанию;
* формы свойств, которые подстраиваются под протокол шины;
* битовая карта кадра: протянуть мышью — новый сигнал, перетащить — сдвиг, за край — длина;
  пересечения подсвечиваются;
* таблицы значений и флагов, проверка на лету, вкладка YAML;
* предпросмотр и скачивание всех форматов;
* сравнение с версией из git и запись changelog в историю.

Файл сохраняется с комментариями и форматированием — в `git diff` только изменённые строки.
Подробнее — [docs/web.md](docs/web.md).

## CI

Пример для пользователей карты — [docs/ci-example.md](docs/ci-example.md): при изменении
YAML карта проверяется, а PDF, Excel, DBC и C-заголовки пересобираются и сохраняются
как артефакты. Docker-образ со всем необходимым: [Dockerfile](Dockerfile).

## Структура репозитория

```text
examples/                   примеры карт (CANopen, J1939, CAN/CAN FD, карта системы питания)
schema/canmap.schema.json   JSON Schema (canmap schema -o …)
docs/                       формат, шаблоны PDF, веб-редактор, CI
src/canmap/
  model.py                  модель данных (pydantic)
  loader.py                 загрузка YAML с позициями узлов
  protocols.py, canopen.py  вычисление CAN ID: CANopen, J1939, явные ID
  resolve.py                ссылки, раскладка SDO
  validate.py               правила проверки
  bits.py                   раскладка бит, pack/unpack
  docmodel.py               общее представление для документов
  export/                   xlsx, pdf (Typst), md/html (Jinja2), dbc
  codegen/                  C и Python
  diff.py                   сравнение версий карты, changelog
  web/                      веб-редактор: FastAPI, операции над YAML, собранный UI (static/)
  templates/                шаблоны документов (pdf/ — Typst)
  fonts/                    PT Sans, PT Serif (OFL)
web/                        исходники интерфейса (Vue 3 + TypeScript + Vite)
tests/                      тесты; data/ — фикстуры, golden/ — эталонные файлы
```

## Тесты

```sh
uv run pytest                     # или: .venv/Scripts/python -m pytest
UPDATE_GOLDEN=1 uv run pytest     # обновить эталонные файлы после намеренных изменений
```

Тесты используют собственные фикстуры из `tests/data/` и не зависят от примеров. Тесты C-кода
компилируют сгенерированные файлы `gcc` (и `arm-none-eabi-gcc`, если установлен) и
сравнивают `pack`/`unpack` побайтно с Python-модулем и cantools для всех примеров.

## Планы

Импорт существующих карт из DBC и Excel; работа с живой шиной (декодирование логов,
монитор, симулятор); плагины для не-CAN протоколов (Modbus, UART-пакеты).
