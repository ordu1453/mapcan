# <img src="web/public/favicon.svg" width="32" height="32" alt=""> mapcan

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
| веб-редактор: создать или открыть карту, дерево, формы, битовая карта, проверка на лету | `mapcan serve` |
| проверка карты с указанием файла и строки | `mapcan validate my-map.yaml` |
| Excel: адресация, содержание, битовые карты, изменения | `mapcan export xlsx my-map.yaml` |
| PDF: титул, оглавление, битовые диаграммы, таблицы; шаблоны ЕСКД, ЕСПД, ГОСТ 7.32 | `mapcan export pdf my-map.yaml --template gost-2.105` |
| Markdown для README/вики, HTML-страница с поиском | `mapcan export md my-map.yaml`, `mapcan export html my-map.yaml` |
| DBC для CANalyzer, SavvyCAN, PCAN-View, Wireshark | `mapcan export dbc my-map.yaml -o dbc/` |
| C: `#define` ID, `enum`, маски, структуры, `pack`/`unpack` | `mapcan gen c my-map.yaml -o firmware/` |
| Python-модуль для тестов и стендов | `mapcan gen py my-map.yaml -o tools/` |
| всё сразу (для CI) | `mapcan build my-map.yaml -o build/` |
| сравнение двух версий карты, changelog | `mapcan diff old.yaml my-map.yaml` |

## Быстрый старт

```sh
mapcan serve
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

## Установка

**Windows, без Python.** Скачайте `mapcan-X.Y.Z-setup.exe` со страницы
[Releases](https://github.com/ordu1453/MapCAN/releases/latest) и запустите — права администратора
не нужны. Установщик добавит mapcan в меню «Пуск» и на рабочий стол, в «Открыть с помощью» для
`.yaml` и (по желанию) команду `mapcan` в PATH. Редактор открывается в собственном окне; повторный
запуск или двойной щелчок по карте открывает её в уже запущенном окне. О новой версии редактор
сообщит плашкой вверху — обновление ставится поверх. Без установки: `mapcan-X.Y.Z-windows-x64.zip`,
запуск — `mapcan-app.exe`.

Windows может предупредить о неизвестном издателе (SmartScreen): установщик не подписан
сертификатом. «Подробнее → Выполнить в любом случае».

**С Python 3.12** (Windows, Linux, macOS). Внешние программы не нужны: PDF собирается
встроенным компилятором Typst из pip-пакета `typst`, шрифты PT Sans и PT Serif (OFL) идут в комплекте.

```sh
uv tool install "mapcan[desktop] @ git+https://github.com/ordu1453/MapCAN"   # или: pipx install …
uv tool upgrade mapcan
mapcan app                     # редактор в отдельном окне (без [desktop] — в браузере)
```

**Переход с canmap.** Раньше утилита называлась canmap. Установщик для Windows ставится
поверх старой версии сам; через uv/pipx — `uv tool uninstall canmap`, затем установка заново
командой выше. Карты с ключом `canmap: 1` открываются без правки, настройки из `~/.canmap`
переносятся в `~/.mapcan`, шаблон PDF `canmap` понимается как `mapcan`.

**Для разработки** (с [uv](https://docs.astral.sh/uv/), окружение по `uv.lock`):

```sh
uv sync
uv run mapcan --help
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
pip install --no-index --find-links wheelhouse mapcan
```

## Команды

```text
mapcan app         [FILE|DIR] [--browser] [--readonly]
mapcan serve       [FILE|DIR] [--host 127.0.0.1] [--port 8765] [--readonly] [--no-browser]
mapcan validate    FILE [--strict] [--info] [--format json] [--disable КОД]
mapcan export xlsx FILE [-o OUT] [--style style.yaml] [--lang en]
mapcan export pdf  FILE [-o OUT] [--template mapcan|gost-2.105|gost-19|gost-7.32|my.typ] [--font-path DIR]
mapcan export md   FILE [-o OUT] [--template my.md.j2]
mapcan export html FILE [-o OUT] [--template my.html.j2]
mapcan export dbc  FILE [-o DIR|file.dbc] [--bus NAME]
mapcan gen c       FILE [-o DIR] [--prefix my_] [--bus NAME]
mapcan gen py      FILE [-o DIR] [--bus NAME]
mapcan build       FILE [-o DIR] [--formats xlsx,pdf,md,html,dbc,c,py] [--pdf-template NAME]
mapcan diff        OLD NEW [--format text|md|json]
mapcan schema      [-o schema.json]
mapcan template    --list | pdf [--name gost-2.105] -o FILE | md|html|xlsx-style -o FILE
mapcan rules
mapcan language    [en|ru]
```

Язык интерфейса (сообщения проверки, CLI, редактор) — английский по умолчанию; выбирается
при первом запуске редактора, переключателем на его верхней панели или `mapcan language ru`.
Переменная окружения `MAPCAN_LANG=ru|en` важнее сохранённого выбора. Язык документов задаётся
отдельно — полем `document.language` карты.

Экспорт и генерация сначала проверяют карту и прерываются при ошибках
(`--force` — генерировать всё равно). `validate` возвращает код 1 при ошибках,
а с `--strict` — и при предупреждениях.

### Пример вывода проверки

```text
$ mapcan validate tests/data/invalid_map.yaml
tests/data/invalid_map.yaml:21:25: error[number-comma]: значение '0,1': дробная часть отделена запятой, нужно 0.1
tests/data/invalid_map.yaml:24:17: error[number-cyrillic-x]: значение '0х196': в префиксе 0x используется кириллическая «х»
tests/data/invalid_map.yaml:33:22: error[invalid-identifier]: имя значения 'NO DATA': допустимы латинские буквы, цифры и _
tests/data/invalid_map.yaml:62:36: error[duplicate-signal-name]: флаг 'dc_status' уже есть в кадре 'pcu_state' (сигнал)
...
FAIL: ошибок: 12, предупреждений: 2, замечаний: 0
```

## Своё оформление

* **Excel** — `mapcan template xlsx-style -o style.yaml`, правка шрифтов, цветов и набора
  колонок, затем `mapcan export xlsx map.yaml --style style.yaml`.
* **PDF** — четыре встроенных шаблона: `mapcan`, ЕСКД `gost-2.105` (рамка и основная
  надпись), ЕСПД `gost-19`, отчёт `gost-7.32`. Реквизиты (обозначение, литера, подписи,
  «Утверждаю», «Согласовано») и логотип предприятия задаются в `document`. Свой вариант:
  `mapcan template pdf --name gost-2.105 -o corp.typ`, затем `--template corp.typ`.
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
mapcan app                    # отдельное окно: стартовый экран — новая карта, открыть, недавние
mapcan app my-map.yaml        # сразу открыть карту
mapcan serve my-map.yaml      # то же в браузере (сервер, разработка)
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
как артефакты. Docker-образ со всем необходимым: [Dockerfile](Dockerfile),
готовый — `ghcr.io/ordu1453/mapcan:<версия>`.

### Выпуск версии

1. Поднять версию в `pyproject.toml`, `src/mapcan/__init__.py` и `web/package.json`
   (`uv lock`, `npm run build` в `web/`), закоммитить.
2. Поставить и запушить тег: `git tag -a vX.Y.Z -m "mapcan X.Y.Z: …" && git push origin main vX.Y.Z`.

[release.yml](.github/workflows/release.yml) прогонит тесты, проверит, что тег совпадает с версией,
соберёт установщик и zip для Windows (PyInstaller + Inno Setup), wheel и Docker-образ и опубликует
GitHub Release; текст аннотации тега станет описанием релиза. Ручной запуск workflow
(Actions → release → Run workflow) — пробная сборка без публикации.

Локальная сборка Windows-версии:

```sh
uv sync --extra desktop --group package
uv run pyinstaller packaging/mapcan.spec --noconfirm        # → dist/mapcan/
iscc /DAppVersion=X.Y.Z packaging/mapcan.iss                # → dist/mapcan-X.Y.Z-setup.exe
```

## Структура репозитория

```text
examples/                   примеры карт (CANopen, J1939, CAN/CAN FD)
schema/mapcan.schema.json   JSON Schema (mapcan schema -o …)
docs/                       формат, шаблоны PDF, веб-редактор, CI
src/mapcan/
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
  launcher.py               mapcan app: окно, один экземпляр, выбор порта
  updates.py                проверка новой версии на GitHub Releases
  web/                      веб-редактор: FastAPI, операции над YAML, собранный UI (static/)
  templates/                шаблоны документов (pdf/ — Typst)
  fonts/                    PT Sans, PT Serif (OFL)
web/                        исходники интерфейса (Vue 3 + TypeScript + Vite)
packaging/                  сборка для Windows: PyInstaller (mapcan.spec), установщик (mapcan.iss), иконка
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
