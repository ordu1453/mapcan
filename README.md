# canmap

YAML-карта сигналов CAN как единственный источник правды. Из одного файла
[`canmap.yaml`](canmap.yaml) получаются:

| Результат | Команда |
|---|---|
| проверка карты с указанием файла и строки | `canmap validate canmap.yaml` |
| Excel: адресация, содержание, битовые карты, изменения | `canmap export xlsx canmap.yaml` |
| PDF: титул, оглавление, битовые диаграммы, таблицы | `canmap export pdf canmap.yaml` |
| Markdown для README/вики | `canmap export md canmap.yaml` |
| HTML-страница с поиском | `canmap export html canmap.yaml` |
| DBC для CANalyzer, SavvyCAN, PCAN-View, Wireshark | `canmap export dbc canmap.yaml -o dbc/` |
| C: `#define` ID, `enum`, маски, структуры, `pack`/`unpack` | `canmap gen c canmap.yaml -o firmware/` |
| Python-модуль для тестов и стендов | `canmap gen py canmap.yaml -o tools/` |
| всё сразу (для CI) | `canmap build canmap.yaml -o build/` |
| веб-редактор: файлы, дерево, формы, битовая карта, проверка на лету | `canmap serve [canmap.yaml]` |
| сравнение двух версий карты, changelog | `canmap diff old.yaml canmap.yaml` |

Формат файла описан в [docs/format.md](docs/format.md), минимальный пример —
[examples/minimal.yaml](examples/minimal.yaml).

## Установка

Нужен Python 3.11–3.13. Внешние программы не нужны: PDF собирается встроенным
компилятором Typst из pip-пакета `typst`, шрифты PT Sans (OFL) идут в комплекте.

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

**Для пользователей** (команда `canmap` доступна глобально, обновление одной командой):

```sh
uv tool install git+<адрес репозитория>     # или: pipx install git+<адрес>
uv tool upgrade canmap
```

**Офлайн** (корпоративная сеть без PyPI): на машине с доступом собрать wheelhouse
и перенести каталог:

```sh
pip wheel . -w wheelhouse
pip install --no-index --find-links wheelhouse canmap
```

## Команды

```text
canmap validate FILE [--strict] [--info] [--format json] [--disable КОД]
canmap export xlsx FILE [-o OUT] [--style style.yaml] [--lang en]
canmap export pdf  FILE [-o OUT] [--template my.typ] [--font-path DIR]
canmap export md   FILE [-o OUT] [--template my.md.j2]
canmap export html FILE [-o OUT] [--template my.html.j2]
canmap export dbc  FILE [-o DIR|file.dbc] [--bus NAME]
canmap gen c       FILE [-o DIR] [--prefix ne_] [--bus NAME]
canmap gen py      FILE [-o DIR] [--bus NAME]
canmap build       FILE [-o DIR] [--formats xlsx,pdf,md,html,dbc,c,py]
canmap schema      [-o schema.json]
canmap template    pdf|md|html|xlsx-style -o FILE
canmap serve       [FILE|DIR] [--port 8765] [--readonly] [--no-browser]
canmap diff        OLD NEW [--format text|md|json]
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
* **PDF** — `canmap template pdf -o corp.typ`, правка шаблона Typst (рамки по ГОСТ,
  логотип, колонтитулы), затем `--template corp.typ`. Данные карты доступны шаблону
  как `json(bytes(sys.inputs.data))`; структура данных — в
  [src/canmap/docmodel.py](src/canmap/docmodel.py). Свои шрифты — `--font-path DIR`.
* **Markdown/HTML** — Jinja2-шаблоны, те же данные.

## Сгенерированный C-код

Для каждой шины создаются `<bus>.h` и `<bus>.c`. Без динамической памяти и libc
(только `stdint.h`, `stdbool.h`, `stddef.h`), компилируется с `-Wall -Wextra -Wconversion`
для x86 и Cortex-M.

```c
#include "bus1.h"

imd_data_t msg = {0};
msg.bus_voltage = imd_data_bus_voltage_from_phys(400.5f);   /* В → raw */
uint8_t buf[8];
int dlc = imd_data_pack(buf, sizeof buf, &msg);              /* → IMD_DATA_ID, dlc */

imd_state_t st;
if (imd_state_unpack(&st, rx_data, rx_len) == 0 &&
    st.insulation_status == IMD_STATE_INSULATION_STATUS_ALARM) { ... }
if (st.internal_error & IMD_STATE_INTERNAL_ERROR_TIMEOUT_ERROR_MASK) { ... }
```

## Веб-редактор

```sh
canmap serve canmap.yaml      # или просто `canmap serve` — создать/открыть карту из браузера
```

Откроется браузер с редактором. Файлы создаются, открываются и сохраняются из меню «Файл»;
профиль автора (имя, GitHub) подписывает записи истории изменений. В редакторе: дерево карты с поиском (имя, `0x196`, описание), формы
свойств, битовая карта кадра (протянуть мышью — новый сигнал, перетащить — сдвиг, за край —
длина; пересечения подсвечиваются), таблицы значений и флагов, проверка на лету, вкладка
YAML, предпросмотр и скачивание всех форматов, сравнение с версией из git и запись
changelog в историю. Файл сохраняется с комментариями и форматированием — в `git diff`
только изменённые строки. Подробнее — [docs/web.md](docs/web.md).

## CI

Пример для пользователей карты — [docs/ci-example.md](docs/ci-example.md): при изменении
YAML карта проверяется, а PDF, Excel, DBC и C-заголовки пересобираются и сохраняются
как артефакты. Docker-образ со всем необходимым: [Dockerfile](Dockerfile).

## Структура репозитория

```text
canmap.yaml                 эталонная карта (шины 1 и 2)
schema/canmap.schema.json   JSON Schema (canmap schema -o …)
examples/                   примеры карт
docs/                       формат, CI
src/canmap/
  model.py                  модель данных (pydantic)
  loader.py                 загрузка YAML с позициями узлов
  resolve.py                вычисление ID, раскладка SDO
  validate.py               правила проверки
  bits.py                   раскладка бит, pack/unpack
  docmodel.py               общее представление для документов
  export/                   xlsx, pdf (Typst), md/html (Jinja2), dbc
  codegen/                  C и Python
  diff.py                   сравнение версий карты, changelog
  web/                      веб-редактор: FastAPI, операции над YAML, собранный UI (static/)
  templates/                шаблоны документов
  fonts/                    PT Sans (OFL)
web/                        исходники интерфейса (Vue 3 + TypeScript + Vite)
tests/                      тесты, эталонные (golden) файлы
legacy/                     исходная карта в старом формате
```

## Тесты

```sh
uv run pytest                     # или: .venv/Scripts/python -m pytest
UPDATE_GOLDEN=1 uv run pytest     # обновить эталонные файлы после намеренных изменений
```

Тесты C-кода компилируют сгенерированные файлы `gcc` (и `arm-none-eabi-gcc`, если
установлен) и сравнивают результат `pack`/`unpack` побайтно с Python-модулем и cantools.

## Состояние

Готовы этапы 1–6 плана ([canmap_tasks.md](canmap_tasks.md)): формат, проверка,
Excel, PDF/Markdown/HTML, C/Python/DBC, веб-редактор. Не реализованы: импорт DBC/Excel
(этап 7), работа с живой шиной (этап 8), плагины протоколов (этап 9).
