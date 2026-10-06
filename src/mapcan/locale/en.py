"""Английские переводы сообщений утилиты (ключ — исходная русская строка, см. :mod:`mapcan.i18n`)."""

EN: dict[str, str] = {
    # ------------------------------------------------------------------ CLI
    "ошибок: {errors}, предупреждений: {warnings}, замечаний: {infos}":
        "errors: {errors}, warnings: {warnings}, notes: {infos}",
    "mapcan — карта сигналов CAN в YAML → проверка, документация, код.":
        "mapcan — CAN signal map in YAML → validation, documentation, code.",
    "Экспорт документов и файлов для сторонних инструментов.": "Export documents and files for third-party tools.",
    "Генерация кода.": "Code generation.",
    "YAML-файл карты.": "Map YAML file.",
    "Язык документа (ru/en); по умолчанию из карты.": "Document language (ru/en); defaults to the map's language.",
    "Генерировать, даже если есть ошибки проверки.": "Generate even if validation reports errors.",
    "Проверить карту. Код возврата 1 при ошибках (и предупреждениях с --strict).":
        "Validate the map. Exit code 1 on errors (and on warnings with --strict).",
    "mapcan {version}: {path} → {url}  (Ctrl+C — остановить)": "mapcan {version}: {path} → {url}  (Ctrl+C to stop)",
    "Веб-редактор в браузере (для сервера и разработки; на рабочем месте удобнее `mapcan app`).":
        "Web editor in the browser (for servers and development; on a workstation `mapcan app` is handier).",
    "Редактор в отдельном окне (pywebview); повторный запуск открывает файл в уже запущенном окне.":
        "Editor in its own window (pywebview); running it again opens the file in the window already open.",
    "Показать или выбрать язык интерфейса утилиты (en, ru).": "Show or set the tool's interface language (en, ru).",
    "Сравнить две версии карты (кадры, сигналы, значения) и вывести changelog.":
        "Compare two versions of a map (frames, signals, values) and print a changelog.",
    "Список правил проверки.": "List validation rules.",
    "Вывести JSON Schema формата (для подсказок в IDE).": "Print the format's JSON Schema (for IDE hints).",
    "Список шаблонов PDF или копия встроенного шаблона для правки (своё оформление).":
        "List PDF templates or copy a built-in template to customize the layout.",
    "Excel: адресация, содержание, битовые карты, изменения.": "Excel: addressing, contents, bit maps, changes.",
    "PDF через Typst: титул, оглавление, битовые диаграммы, таблицы; шаблоны ГОСТ.":
        "PDF via Typst: title page, contents, bit diagrams, tables; GOST templates.",
    "Markdown для README/вики.": "Markdown for a README or wiki.",
    "Самодостаточная HTML-страница с поиском.": "Self-contained HTML page with search.",
    "DBC (по файлу на шину).": "DBC (one file per bus).",
    "C: #define ID, enum, маски, структуры, pack/unpack.": "C: #define IDs, enums, masks, structs, pack/unpack.",
    "Python-модуль с теми же структурами (для тестов и стендов).":
        "Python module with the same structures (for tests and test benches).",
    "Проверить карту и собрать все артефакты (для CI).": "Validate the map and build all artifacts (for CI).",
    "Генерация прервана: {summary}. Исправьте ошибки (mapcan validate) или используйте --force.":
        "Generation aborted: {summary}. Fix the errors (mapcan validate) or use --force.",
    "Показать версию.": "Show the version.",
    "Считать предупреждения ошибками.": "Treat warnings as errors.",
    "Формат вывода.": "Output format.",
    "Показывать замечания уровня info.": "Show info-level notes.",
    "Отключить правило (можно несколько раз).": "Disable a rule (may be repeated).",
    "Карта для открытия или рабочая папка. Без аргумента — стартовый экран.":
        "Map to open or a working folder. Without an argument, the start screen opens.",
    "Адрес для прослушивания.": "Address to listen on.",
    "Порт; по умолчанию 8765 или свободный.": "Port; 8765 or a free one by default.",
    "Только просмотр, без сохранения.": "View only, no saving.",
    "Не открывать браузер.": "Do not open a browser.",
    "Внимание: редактор доступен по сети ({host}) без аутентификации. "
    "Любой, кто откроет адрес, сможет открывать и менять файлы.":
        "Warning: the editor is reachable over the network ({host}) without authentication. "
        "Anyone who opens the address can open and change files.",
    "Открыть в браузере вместо окна приложения.": "Open in a browser instead of the app window.",
    "Новый язык: en или ru.": "New language: en or ru.",
    "Старая версия карты.": "Old version of the map.",
    "Новая версия карты.": "New version of the map.",
    "Файл JSON Schema.": "JSON Schema file.",
    "Куда сохранить копию шаблона.": "Where to save the template copy.",
    "Встроенный PDF-шаблон (см. --list).": "Built-in PDF template (see --list).",
    "Показать встроенные шаблоны PDF.": "Show built-in PDF templates.",
    "укажите -o/--output": "specify -o/--output",
    "YAML с оформлением.": "YAML file with styling.",
    "Встроенный шаблон (mapcan, gost-2.105, gost-19, gost-7.32) или путь к своему .typ.":
        "Built-in template (mapcan, gost-2.105, gost-19, gost-7.32) or a path to your own .typ.",
    "Каталог с дополнительными шрифтами.": "Folder with additional fonts.",
    "Свой Jinja2-шаблон.": "Custom Jinja2 template.",
    "Файл .dbc (одна шина) или каталог.": ".dbc file (single bus) or a folder.",
    "Только указанная шина.": "Only the given bus.",
    "Каталог для .h/.c.": "Folder for .h/.c files.",
    "Префикс имён (напр. ne_).": "Name prefix (e.g. ne_).",
    "Только указанные шины.": "Only the given buses.",
    "Каталог для модулей.": "Folder for the modules.",
    "Каталог результатов.": "Output folder.",
    "Шаблон PDF (можно несколько раз; по умолчанию mapcan).": "PDF template (may be repeated; mapcan by default).",
    "неизвестные форматы: {formats}": "unknown formats: {formats}",
    "Ошибка: {error}": "Error: {error}",
    "неизвестный язык: {language}": "unknown language: {language}",
    "{path}: карта не загружена": "{path}: the map could not be loaded",
    "нет шаблона {name!r}; доступны: {known}": "no template {name!r}; available: {known}",
    "Через запятую: ": "Comma-separated: ",

    # ------------------------------------------------------------------ экспорт
    "шина {name!r} не найдена": "bus {name!r} not found",
    "шаблон не найден: {template} (встроенные: {known})": "template not found: {template} (built-in: {known})",
    "mapcan — техническое оформление": "mapcan — technical style",
    "Цветные битовые диаграммы, колонтитулы, титульный лист в свободной форме.":
        "Colored bit diagrams, headers and footers, free-form title page.",
    "ЕСКД — ГОСТ 2.105 / 2.104": "ESKD — GOST 2.105 / 2.104",
    "Текстовый конструкторский документ: рамка, основная надпись (формы 2 и 2а), "
    "дополнительные графы, титульный лист, лист регистрации изменений.":
        "Design text document: frame, title block (forms 2 and 2a), additional columns, "
        "title page, change log sheet.",
    "ЕСПД — ГОСТ 19.104 / 19.106": "ESPD — GOST 19.104 / 19.106",
    "Программный документ: лист утверждения, титульный лист, аннотация, "
    "обозначение на каждой странице, лист регистрации изменений.":
        "Software document: approval sheet, title page, abstract, designation on every page, change log sheet.",
    "Отчёт — ГОСТ 7.32-2017": "Report — GOST 7.32-2017",
    "Отчёт: титульный лист, список исполнителей, реферат, содержание, "
    "нумерованные таблицы, приложение.":
        "Report: title page, list of contributors, abstract, contents, numbered tables, appendix.",
    "ошибка компиляции Typst ({name}): {error}": "Typst compilation error ({name}): {error}",
    "неизвестный параметр стиля: {key}": "unknown style parameter: {key}",

    # ------------------------------------------------------------------ окно приложения
    "Редактор карты сигналов mapcan.": "mapcan signal map editor.",
    "карта (.yaml) или рабочая папка": "map (.yaml) or working folder",
    "открыть в браузере вместо окна приложения": "open in a browser instead of the app window",
    "только просмотр": "view only",
    "Файл не найден:\n{path}": "File not found:\n{path}",
    "Не удалось открыть {path}:\n{error}": "Could not open {path}:\n{error}",
    "mapcan {version}: {url}  (Ctrl+C — остановить)": "mapcan {version}: {url}  (Ctrl+C to stop)",
    "сервер mapcan не запустился (порт занят?)": "the mapcan server did not start (is the port in use?)",
    "сервер mapcan не ответил за отведённое время": "the mapcan server did not respond in time",
    "В «{name}» есть несохранённые изменения.\n\nЗакрыть без сохранения?":
        "“{name}” has unsaved changes.\n\nClose without saving?",
    "mapcan: окно приложения недоступно ({error}), открываю браузер":
        "mapcan: the app window is unavailable ({error}), opening the browser",

    # ------------------------------------------------------------------ загрузка
    "ключ": "key",
    "значение": "value",
    "неизвестное поле {name!r}": "unknown field {name!r}",
    "{what} {value!r}: дробная часть отделена запятой, нужно {fixed!r}":
        "{what} {value!r}: decimal comma used, should be {fixed!r}",
    "{what} {value!r}: в префиксе 0x используется кириллическая «х»":
        "{what} {value!r}: the 0x prefix uses a Cyrillic “х”",
    "{what} {value!r} записано строкой; уберите кавычки": "{what} {value!r} is written as a string; remove the quotes",
    "отсутствует обязательное поле {name!r}": "missing required field {name!r}",
    "повторяющийся ключ: {problem}": "duplicate key: {problem}",
    "пустой файл": "empty file",
    "укажите либо start_bit, либо byte/bit, но не оба способа": "specify either start_bit or byte/bit, not both",
    "укажите либо bit_length, либо byte_length": "specify either bit_length or byte_length",
    "не задана позиция сигнала (start_bit или byte)": "signal position is not set (start_bit or byte)",
    "cycle_ms задан и на уровне кадра, и в transmission": "cycle_ms is set both on the frame and in transmission",
    "«{value}» — не имя пользователя GitHub": "“{value}” is not a GitHub username",

    # ------------------------------------------------------------------ правила проверки
    "Синтаксическая ошибка YAML, повторяющийся ключ": "YAML syntax error, duplicate key",
    "Нарушение структуры: тип, обязательное поле, недопустимое значение":
        "Structure violation: type, required field, invalid value",
    "Число записано через запятую (0,1 вместо 0.1)": "Number written with a decimal comma (0,1 instead of 0.1)",
    "Кириллическая «х» в шестнадцатеричном числе": "Cyrillic “х” in a hexadecimal number",
    "Число записано строкой в кавычках": "Number written as a quoted string",
    "Имя нельзя использовать как идентификатор C/Python": "Name cannot be used as a C/Python identifier",
    "Повтор имени устройства на шине": "Duplicate device name on the bus",
    "Повтор node_id на шине": "Duplicate node_id on the bus",
    "node_id CANopen вне диапазона 1..127": "CANopen node_id outside 1..127",
    "Повтор имени кадра на шине": "Duplicate frame name on the bus",
    "Невозможно определить CAN ID кадра": "Cannot determine the frame's CAN ID",
    "Повтор CAN ID на шине": "Duplicate CAN ID on the bus",
    "CAN ID не помещается в 11 бит (нужно extended: true)": "CAN ID does not fit in 11 bits (needs extended: true)",
    "Недопустимый DLC": "Invalid DLC",
    "Повтор имени сигнала/флага в кадре": "Duplicate signal/flag name in the frame",
    "Сигнал выходит за пределы DLC": "Signal extends beyond the DLC",
    "Пересечение сигналов по битам (с учётом мультиплексирования)": "Signals overlap in bits (multiplexing considered)",
    "Значение enum не помещается в разрядность поля": "Enum value does not fit in the field width",
    "Одинаковое имя у разных значений enum": "Same name for different enum values",
    "flags задан у сигнала не типа bitfield": "flags set on a signal that is not a bitfield",
    "Флаг выходит за пределы битового поля": "Flag extends beyond the bit field",
    "Пересечение флагов внутри битового поля": "Flags overlap inside the bit field",
    "Сигнал типа flag длиной больше 1 бита": "Flag signal longer than 1 bit",
    "Нулевой масштаб": "Zero factor",
    "min/max вне диапазона, представимого полем": "min/max outside the range the field can represent",
    "min больше max": "min is greater than max",
    "Мультиплексированный сигнал в кадре без селектора": "Multiplexed signal in a frame without a selector",
    "Больше одного селектора в кадре": "More than one selector in the frame",
    "Значение mux не помещается в селектор": "mux value does not fit in the selector",
    "Значения mux нет в таблице значений селектора": "mux value is not in the selector's value table",
    "Селектор сам мультиплексирован": "Selector is itself multiplexed",
    "Режим cyclic без cycle_ms": "cyclic mode without cycle_ms",
    "cycle_ms задан для нециклического кадра": "cycle_ms set for a non-cyclic frame",
    "Направление противоречит типу кадра CANopen": "Direction contradicts the CANopen frame type",
    "Тип кадра CANopen на шине не CANopen": "CANopen frame type on a non-CANopen bus",
    "Описание sdo у кадра не типа sdo_tx/sdo_rx": "sdo description on a frame that is not sdo_tx/sdo_rx",
    "Повтор SDO-обмена (команда, индекс, субиндекс)": "Duplicate SDO exchange (command, index, subindex)",
    "Имя не соответствует правилу стиля (lint)": "Name does not match the style rule (lint)",
    "Одно и то же имя значения записано по-разному": "The same value name is spelled differently",
    "Адрес J1939 вне 0..253 или повторяется на шине": "J1939 address outside 0..253 or repeated on the bus",
    "PDU1-PGN (PF < 240) с ненулевым младшим байтом": "PDU1 PGN (PF < 240) with a non-zero low byte",
    "destination задан для PDU2-PGN (PF ≥ 240) и не используется":
        "destination set for a PDU2 PGN (PF ≥ 240) and unused",
    "pgn/priority/destination/address на шине не J1939": "pgn/priority/destination/address on a non-J1939 bus",
    "Получатель кадра не описан на шине": "Frame receiver is not described on the bus",
    "Сигнал float должен быть 32 или 64 бита": "A float signal must be 32 or 64 bits",
    "Значение по умолчанию вне диапазона сигнала": "Default value outside the signal's range",
    "Значение invalid не помещается в разрядность сигнала": "invalid value does not fit in the signal width",
    "Файл логотипа не найден": "Logo file not found",
    "Неподдерживаемый формат логотипа": "Unsupported logo format",
    "Нет описания сигнала": "Signal has no description",
    "В кадре не описаны сигналы": "Frame has no signals",

    # ------------------------------------------------------------------ сообщения проверки
    "имя кадра": "frame name",
    "имя устройства": "device name",
    "имя значения": "value name",
    "имя флага": "flag name",
    "имя сигнала": "signal name",
    "флаг": "flag",
    "сигнал": "signal",
    "{what} {name!r}: допустимы латинские буквы, цифры и _":
        "{what} {name!r}: only Latin letters, digits and _ are allowed",
    "{what} {name!r} не в стиле {style}": "{what} {name!r} is not in {style} style",
    "{fields} у кадра на шине {protocol}": "{fields} on a frame on a {protocol} bus",
    "тип {type} на шине с протоколом {protocol}": "type {type} on a bus with protocol {protocol}",
    "кадр {type} обычно {expected} для устройства, указано {actual}":
        "a {type} frame is usually {expected} for the device, {actual} is set",
    "второй селектор {name!r}": "second selector {name!r}",
    "логотип {logo!r}: поддерживаются {formats}": "logo {logo!r}: supported formats are {formats}",
    "устройство {name!r} уже описано": "device {name!r} is already described",
    "кадр {name!r} уже описан на шине": "frame {name!r} is already described on the bus",
    "CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}":
        "CAN ID {can_id:#05x} of frame {name!r} matches frame {other!r}",
    "CAN ID {can_id:#x} > 0x7FF": "CAN ID {can_id:#x} > 0x7FF",
    "DLC {dlc} недопустим для CAN FD": "DLC {dlc} is not valid for CAN FD",
    "DLC {dlc} > 8 (для CAN FD укажите fd: true у шины)": "DLC {dlc} > 8 (for CAN FD set fd: true on the bus)",
    "получатель {name!r} не описан на шине {bus!r}": "receiver {name!r} is not described on bus {bus!r}",
    "PGN {pgn:#06x} — PDU1: младший байт должен быть 0 (адрес получателя задаётся destination)":
        "PGN {pgn:#06x} is PDU1: the low byte must be 0 (the destination address is set by destination)",
    "PGN {pgn:#06x} — PDU2 (широковещательный), destination не используется":
        "PGN {pgn:#06x} is PDU2 (broadcast), destination is not used",
    "для режима cyclic нужен cycle_ms": "cyclic mode needs cycle_ms",
    "cycle_ms задан для режима {mode}": "cycle_ms is set for mode {mode}",
    "sdo у кадра типа {type}": "sdo on a frame of type {type}",
    "кадр {name!r} без сигналов": "frame {name!r} has no signals",
    "селектор {name!r} не может иметь mux": "selector {name!r} cannot have mux",
    "сигнал {name!r} занимает байты {first}..{last}, а DLC = {dlc}":
        "signal {name!r} occupies bytes {first}..{last}, but DLC = {dlc}",
    "flags у сигнала типа {kind}": "flags on a signal of kind {kind}",
    "сигнал-флаг {name!r} длиной {bits} бит": "flag signal {name!r} is {bits} bits long",
    "сигнал {name!r}: float — 32 или 64 бита, задано {bits}":
        "signal {name!r}: float must be 32 or 64 bits, {bits} set",
    "сигнал {name!r} без описания": "signal {name!r} has no description",
    "имя {name!r} у значений {a} и {b}": "name {name!r} is used for values {a} and {b}",
    "флаг {name!r} (биты {first}..{last}) вне поля длиной {bits} бит":
        "flag {name!r} (bits {first}..{last}) is outside the {bits}-bit field",
    "файл логотипа не найден: {path}": "logo file not found: {path}",
    "address у устройства на шине {protocol}": "address on a device on a {protocol} bus",
    "адрес {address:#04x} уже занят устройством {other!r}":
        "address {address:#04x} is already used by device {other!r}",
    "адрес {address:#04x} вне 0..253 (254, 255 — служебные)":
        "address {address:#04x} outside 0..253 (254, 255 are reserved)",
    "node_id {node_id:#x} вне 1..127": "node_id {node_id:#x} outside 1..127",
    "node_id {node_id:#04x} уже занят устройством {other!r}":
        "node_id {node_id:#04x} is already used by device {other!r}",
    "нужен pgn (или id)": "pgn (or id) is required",
    "у устройства нет address": "the device has no address",
    "кадр {name!r}: {why}": "frame {name!r}: {why}",
    "кадр {name!r}: для типа {type} нужен явный id": "frame {name!r}: type {type} needs an explicit id",
    "кадр {name!r}: нет node_id у устройства для вычисления ID {type}":
        "frame {name!r}: the device has no node_id to compute the {type} ID",
    "обмен {name!r} повторяет {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})":
        "exchange {name!r} repeats {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})",
    "флаг {name!r} уже есть в кадре {frame!r} ({other})": "flag {name!r} already exists in frame {frame!r} ({other})",
    "сигнал {name!r} уже есть в кадре {frame!r} ({other})":
        "signal {name!r} already exists in frame {frame!r} ({other})",
    "значение {value} ({name}) не помещается в {bits} бит (знаковое: {lo}..{hi})":
        "value {value} ({name}) does not fit in {bits} bits (signed: {lo}..{hi})",
    "значение {value} ({name}) не помещается в {bits} бит (беззнаковое: {lo}..{hi})":
        "value {value} ({name}) does not fit in {bits} bits (unsigned: {lo}..{hi})",
    "invalid = {value} не помещается в {bits} бит ({lo}..{hi})":
        "invalid = {value} does not fit in {bits} bits ({lo}..{hi})",
    "initial = {value:g} → raw {raw} вне {lo}..{hi}": "initial = {value:g} → raw {raw} outside {lo}..{hi}",
    "initial = {value:g} вне min/max": "initial = {value:g} outside min/max",
    "у сигнала {name!r} задан mux, но в кадре нет multiplexer":
        "signal {name!r} has mux, but the frame has no multiplexer",
    "флаг {name!r} пересекается с {other!r} по биту {bit}": "flag {name!r} overlaps {other!r} at bit {bit}",
    "значение {value} не помещается во флаг {name!r}": "value {value} does not fit in flag {name!r}",
    "бит {bit}": "bit {bit}",
    "биты {first}..{last}": "bits {first}..{last}",
    "сигнал {name!r} пересекается с {other!r}: {bits} (байт {byte})":
        "signal {name!r} overlaps {other!r}: {bits} (byte {byte})",
    "значение {name!r} записано иначе, чем {main!r} в других местах":
        "value {name!r} is spelled differently from {main!r} elsewhere",
    "min {min} > max {max}": "min {min} > max {max}",
    "mux {value} не помещается в селектор {name!r}": "mux {value} does not fit in selector {name!r}",
    "mux {value} отсутствует в values селектора {name!r}":
        "mux {value} is missing from the values of selector {name!r}",
    "{key} = {value:g} вне представимого диапазона {lo:g}..{hi:g} {unit}":
        "{key} = {value:g} is outside the representable range {lo:g}..{hi:g} {unit}",

    # ------------------------------------------------------------------ веб-редактор
    "папка не найдена: {path}": "folder not found: {path}",
    "карта не открыта": "no map is open",
    "в «{name}» есть несохранённые изменения": "“{name}” has unsaved changes",
    "нет доступа к папке: {path}": "access to the folder is denied: {path}",
    "ошибка git": "git error",
    "редактор запущен в режиме только для чтения": "the editor is running in read-only mode",
    "неверный токен экземпляра": "invalid instance token",
    "неизвестный формат: {fmt}": "unknown format: {fmt}",
    "неизвестный шаблон PDF: {template}": "unknown PDF template: {template}",
    "карта содержит ошибки структуры — экспорт невозможен": "the map has structural errors, export is not possible",
    "логотип не задан или файл не найден": "no logo is set or the file was not found",
    "поддерживаются {formats}": "supported formats: {formats}",
    "файл больше {mb} МБ": "the file is larger than {mb} MB",
    "{label}: карта не загружается: {errors}": "{label}: the map does not load: {errors}",
    "текущая карта содержит ошибки структуры": "the current map has structural errors",
    "не удалось сохранить настройки: {error}": "could not save settings: {error}",
    "файл не найден: {path}": "file not found: {path}",
    "файл уже существует: {path}": "file already exists: {path}",
    "ошибка экспорта {fmt}: {error}": "{fmt} export error: {error}",
    "файл не в UTF-8": "the file is not UTF-8",
    "не удалось прочитать {name}: {error}": "could not read {name}: {error}",
    "не удалось создать {path}: {error}": "could not create {path}: {error}",
    "не удалось сохранить {path}: {error}": "could not save {path}: {error}",
    "не удалось сохранить логотип: {error}": "could not save the logo: {error}",
    "файл изменён на диске другой программой": "the file was changed on disk by another program",
    "в YAML синтаксическая ошибка — исправьте текст во вкладке YAML":
        "the YAML has a syntax error; fix the text in the YAML tab",

    # шаблоны новой карты (содержимое карты — на языке интерфейса)
    "CANopen: шина и одно устройство": "CANopen: a bus and one device",
    "SAE J1939: ECU с одним PGN": "SAE J1939: an ECU with one PGN",
    "CAN с явными ID: шина и одно устройство": "CAN with explicit IDs: a bus and one device",
    "Пустая: только шина": "Empty: just a bus",
    "неизвестный шаблон: {template}": "unknown template: {template}",
    "неизвестный пример: {name}": "unknown example: {name}",

    # примеры на стартовом экране
    "Минимальный": "Minimal",
    "SAE J1939": "SAE J1939",
    "Электромобиль": "Electric vehicle",
    "Карта сигналов mapcan (формат v1).": "mapcan signal map (format v1).",
    "Байты и биты нумеруются с 0; start_bit — позиция младшего бита; physical = raw * factor + offset.":
        "Bytes and bits are numbered from 0; start_bit is the position of the least significant bit; "
        "physical = raw * factor + offset.",
    "Создана карта.": "Map created.",
    "Шина 1": "Bus 1",
    "Устройство": "Device",
    "Состояние устройства": "Device state",
    "Статус": "Status",
    "Новая карта": "New map",
    "Шина J1939": "J1939 bus",
    "Блок управления": "Control unit",
    "Состояние блока": "Unit state",
    "Режим работы": "Operating mode",

    # операции редактора
    "пустой путь": "empty path",
    "путь не найден: {path}": "path not found: {path}",
    "родитель не словарь: {path}": "parent is not a mapping: {path}",
    "не список: {path}": "not a list: {path}",
    "перемещать можно только элементы списка: {path}": "only list items can be moved: {path}",
    "индекс вне списка": "index out of range",
    "индекс вне списка: {path}": "index out of range: {path}",
    "не словарь: {path}": "not a mapping: {path}",
    "ключ {key!r} уже существует": "key {key!r} already exists",
    "ключ не найден: {path}": "key not found: {path}",
    "не сигнал: {path}": "not a signal: {path}",
    "недопустимая позиция": "invalid position",
    "нельзя удалить: {path}": "cannot remove: {path}",
    "неизвестная операция: {op!r}": "unknown operation: {op!r}",
    "path должен быть списком": "path must be a list",
    "Интерфейс не собран: выполните <code>npm run build</code> в каталоге <code>web/</code>. "
    "API доступно на <a href='/api/docs'>/api/docs</a>.":
        "The interface is not built: run <code>npm run build</code> in <code>web/</code>. "
        "The API is available at <a href='/api/docs'>/api/docs</a>.",
}
