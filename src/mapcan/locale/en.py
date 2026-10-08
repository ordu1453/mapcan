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
        "Browser-based editor (for servers and development; on a desktop, `mapcan app` is more convenient).",
    "Редактор в отдельном окне (pywebview); повторный запуск открывает файл в уже запущенном окне.":
        "Editor in its own window (pywebview); running it again opens the file in the existing window.",
    "Сравнить две версии карты (кадры, сигналы, значения) и вывести changelog.":
        "Compare two versions of a map (frames, signals, values) and print a changelog.",
    "Список правил проверки.": "List validation rules.",
    "Вывести JSON Schema формата (для подсказок в IDE).": "Print the format's JSON Schema (for IDE hints).",
    "Список шаблонов PDF или копия встроенного шаблона для правки (своё оформление).":
        "List PDF templates or copy a built-in template to customize the layout.",
    "Excel: адресация, содержание, битовые карты, изменения.": "Excel: addressing, contents, bit maps, changes.",
    "PDF через Typst: титул, оглавление, битовые диаграммы, таблицы; шаблон ЕСКД.":
        "PDF via Typst: title page, contents, bit diagrams, tables; ESKD template.",
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
        "Map to open, or a working folder. Without an argument, the start screen is shown.",
    "Адрес для прослушивания.": "Address to listen on.",
    "Порт; по умолчанию 8765 или свободный.": "Port; defaults to 8765 or any free port.",
    "Только просмотр, без сохранения.": "View only, no saving.",
    "Не открывать браузер.": "Do not open a browser.",
    "Внимание: редактор доступен по сети ({host}) без аутентификации. "
    "Любой, кто откроет адрес, сможет открывать и менять файлы.":
        "Warning: the editor is reachable over the network ({host}) without authentication. "
        "Anyone who opens the address can open and change files.",
    "Открыть в браузере вместо окна приложения.": "Open in a browser instead of the app window.",
    "Старая версия карты.": "Old version of the map.",
    "Новая версия карты.": "New version of the map.",
    "Файл JSON Schema.": "JSON Schema file.",
    "Куда сохранить копию шаблона.": "Where to save the template copy.",
    "Встроенный PDF-шаблон (см. --list).": "Built-in PDF template (see --list).",
    "Показать встроенные шаблоны PDF.": "Show built-in PDF templates.",
    "укажите -o/--output": "specify -o/--output",
    "YAML с оформлением.": "YAML file with styling.",
    "Встроенный шаблон (mapcan, gost-2.105) или путь к своему .typ.":
        "Built-in template (mapcan, gost-2.105) or a path to your own .typ.",
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
    "mapcan — стандартное оформление": "mapcan — Standard layout",
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
    "В «{name}» есть несохранённые изменения.\n\nСохранить перед закрытием?":
        "“{name}” has unsaved changes.\n\nSave before closing?",
    "Не удалось сохранить {path}:\n{error}": "Could not save {path}:\n{error}",
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
    "не задана длина сигнала: bit_length или byte_length": "signal length is not set: bit_length or byte_length",
    "укажите либо bit_length, либо byte_length": "specify either bit_length or byte_length",
    "не задана позиция сигнала (start_bit или byte)": "signal position is not set (start_bit or byte)",
    "«{value}» — не имя пользователя GitHub": "“{value}” is not a GitHub username",

    # ------------------------------------------------------------------ правила проверки
    "Синтаксическая ошибка YAML, повторяющийся ключ": "YAML syntax error, duplicate key",
    "Нарушение структуры: тип, обязательное поле, недопустимое значение":
        "Schema violation: wrong type, missing required field or invalid value",
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
    "Пересечение сигналов по битам (с учётом мультиплексирования)": "Overlapping signals (multiplexing-aware)",
    "Значение enum не помещается в разрядность поля": "Enum value does not fit in the field width",
    "Одинаковое имя у разных значений enum": "Same name for different enum values",
    "Поле не применимо к кодированию сигнала": "Field does not apply to the signal encoding",
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
    "cycle_ms задан вместе с trigger": "cycle_ms is set together with trigger",
    "Направление противоречит типу кадра CANopen": "Direction conflicts with the CANopen frame type",
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
    "Получатель кадра не описан на шине": "Frame receiver is not defined on the bus",
    "Отправитель кадра не описан на шине": "Frame sender is not defined on the bus",
    "sender противоречит направлению кадра или совпадает с получателем":
        "sender conflicts with the frame direction or matches a receiver",
    "RX-кадр повторяет кадр другого устройства (описывайте кадр у отправителя)":
        "RX frame duplicates another device's frame (describe the frame at its sender)",
    "RX-кадр без отправителя": "RX frame without a sender",
    "Сигнал float должен быть 32 или 64 бита": "A float signal must be 32 or 64 bits",
    "Значение по умолчанию вне диапазона сигнала": "Default value outside the signal's range",
    "Значение invalid не помещается в разрядность сигнала": "invalid value does not fit in the signal width",
    "Файл логотипа не найден": "Logo file not found",
    "Неподдерживаемый формат логотипа": "Unsupported logo format",
    "Нет описания сигнала": "Signal has no description",
    "Нет полного названия шины или устройства": "Bus or device has no full name",
    "Код знакового числа не выражается в DBC или задан у беззнакового сигнала":
        "Signed number code cannot be expressed in DBC or is set on an unsigned signal",
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
    "{fields} у кадра на шине {protocol}": "{fields} set on a frame on a {protocol} bus",
    "тип {type} на шине с протоколом {protocol}": "type {type} on a bus with protocol {protocol}",
    "кадр {type} обычно {expected} для устройства, указано {actual}":
        "a {type} frame is usually {expected} for the device, but {actual} is set",
    "второй селектор {name!r}": "second selector {name!r}",
    "логотип {logo!r}: поддерживаются {formats}": "logo {logo!r}: supported formats are {formats}",
    "устройство {name!r} уже описано": "device {name!r} is already defined",
    "кадр {name!r} уже описан на шине": "frame {name!r} is already defined on the bus",
    "CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}":
        "CAN ID {can_id:#05x} of frame {name!r} matches frame {other!r}",
    "CAN ID {can_id:#x} > 0x7FF": "CAN ID {can_id:#x} > 0x7FF",
    "DLC {dlc} недопустим для CAN FD": "DLC {dlc} is not valid for CAN FD",
    "DLC {dlc} > 8 (для CAN FD укажите fd: true у шины)": "DLC {dlc} > 8 (for CAN FD set fd: true on the bus)",
    "получатель {name!r} не описан на шине {bus!r}": "receiver {name!r} is not defined on bus {bus!r}",
    "отправитель {name!r} не описан на шине {bus!r}": "sender {name!r} is not defined on bus {bus!r}",
    "кадр {name!r} передаёт само устройство {device!r} (TX), "
    "sender {sender!r} противоречит направлению":
        "frame {name!r} is transmitted by device {device!r} itself (TX); "
        "sender {sender!r} conflicts with the direction",
    "устройство {device!r} принимает кадр {name!r} (RX) и не может быть его отправителем":
        "device {device!r} receives frame {name!r} (RX) and cannot be its sender",
    "отправитель {name!r} указан среди получателей кадра": "sender {name!r} is listed among the frame receivers",
    "RX-кадр {name!r} без отправителя: если он описан на шине, укажите sender "
    "или перенесите кадр к отправителю и добавьте {device!r} в receivers":
        "RX frame {name!r} has no sender: if the sender is on the bus, set sender or move the frame to the sender "
        "and add {device!r} to receivers",
    "RX-кадр {name!r} устройства {device!r} повторяет кадр {other!r} отправителя {sender!r} "
    "(CAN ID {can_id:#05x}): опишите кадр один раз у отправителя и добавьте {device!r} в receivers":
        "RX frame {name!r} of device {device!r} duplicates frame {other!r} of sender {sender!r} "
        "(CAN ID {can_id:#05x}): describe the frame once at the sender and add {device!r} to receivers",
    "PGN {pgn:#06x} — PDU1: младший байт должен быть 0 (адрес получателя задаётся destination)":
        "PGN {pgn:#06x} is PDU1: the low byte must be 0 (the destination address is set by destination)",
    "PGN {pgn:#06x} — PDU2 (широковещательный), destination не используется":
        "PGN {pgn:#06x} is PDU2 (broadcast), destination is not used",
    "cycle_ms задан у кадра с trigger: {trigger}": "cycle_ms is set on a frame with trigger: {trigger}",
    "sdo у кадра типа {type}": "sdo set on a frame of type {type}",
    "кадр {name!r} без сигналов": "frame {name!r} has no signals",
    "неизвестное поле {name!r}: если это элемент списка, после «-» нужен пробел":
        "unknown field {name!r}: if this is meant to be a list item, add a space after '-'",
    "ожидается список: если {name!r} — его элемент, после «-» нужен пробел":
        "a list is expected: if {name!r} is meant to be a list item, add a space after '-'",
    "после «-» нужен пробел: элемент списка записывается как «- {item}»":
        "missing space after '-': write the list item as '- {item}'",
    "символ табуляции: отступы в YAML делаются только пробелами":
        "tab character: YAML indentation must use spaces only",
    "элемент списка «-» не на своём месте: здесь ожидался ключ блока, начатого в строке {start}; "
    "проверьте отступ":
        "unexpected list item '-': a key of the block that starts on line {start} was expected here; "
        "check the indentation",
    "неверный отступ: строка не выровнена по блоку, начатому в строке {start}":
        "bad indentation: this line does not line up with the block that starts on line {start}",
    "лишнее «:» — возьмите значение, содержащее «: », в кавычки или проверьте, что у предыдущей строки "
    "есть «:» после ключа":
        "unexpected ':': quote a value that contains ': ', or check that the previous line has ':' "
        "after its key",
    "кавычка, открытая в строке {start}, не закрыта": "the quote opened on line {start} is never closed",
    "«[», открытая в строке {start}, не закрыта или элементы не разделены запятой":
        "the '[' opened on line {start} is not closed, or its items are not separated by commas",
    "«{{», открытая в строке {start}, не закрыта или элементы не разделены запятой":
        "the '{{' opened on line {start} is not closed, or its items are not separated by commas",
    "DLC служебного кадра CANopen не соответствует CiA 301": "DLC of a CANopen service frame does not match CiA 301",
    "Нестандартная скорость шины": "Non-standard bus bit rate",
    "Расчётная загрузка шины циклическими кадрами выше 70 %": "Estimated bus load from cyclic frames above 70%",
    "Имя совпадает с ключевым словом C/Python или членом сгенерированного класса":
        "Name is a C/Python keyword or a member of the generated class",
    "Имена совпадают в сгенерированном коде (различаются только регистром или совпадают со свойством _phys)":
        "Names collide in generated code (differ only in case, or clash with a _phys property)",
    "Значение invalid попадает в рабочий диапазон min..max": "invalid value falls inside the min..max range",
    "Физическая величина без единицы измерения": "Physical quantity without a unit",
    "У кадра нет получателей на шине": "Frame has no receivers on the bus",
    "Повтор короткого обозначения устройства на шине": "Duplicate device short label on the bus",
    "Версия документа не совпадает с последней записью истории":
        "Document version differs from the latest revision history entry",
    "версия документа {version!r}, а последняя запись истории — {latest!r}":
        "document version is {version!r}, but the latest revision history entry is {latest!r}",
    "скорость {bitrate} бит/с не входит в стандартный ряд (125000, 250000, 500000, 1000000…)":
        "bit rate {bitrate} bit/s is not a standard value (125000, 250000, 500000, 1000000…)",
    "обозначение {short!r} уже у устройства {other!r}": "short label {short!r} is already used by device {other!r}",
    "кадр {name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут":
        "frame {name!r} differs from {other!r} only in case: their C macros will collide",
    "расчётная загрузка шины {bus!r} — {load:.0f} % (циклических кадров: {count}, {bitrate} бит/с), "
    "рекомендуется не больше {limit} %":
        "estimated load of bus {bus!r} is {load:.0f}% (cyclic frames: {count}, {bitrate} bit/s); "
        "keep it at or below {limit}%",
    "кадр {type} по CiA 301 имеет DLC {expected}, указано {dlc}":
        "a {type} frame has DLC {expected} under CiA 301, but {dlc} is set",
    "кадр {name!r} никто не принимает: укажите получателей в receivers":
        "nobody receives frame {name!r}: list the receiving devices in receivers",
    "имя сигнала {name!r} — ключевое слово C/Python: сгенерированный код не скомпилируется":
        "signal name {name!r} is a C/Python keyword: the generated code will not compile",
    "имя сигнала {name!r} совпадает с членом класса кадра в Python-модуле ({members})":
        "signal name {name!r} clashes with a frame class member in the Python module ({members})",
    "сигнал {name!r} совпадает со свойством физического значения сигнала {other!r} в Python-модуле":
        "signal {name!r} clashes with the physical value property of signal {other!r} in the Python module",
    "{name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут":
        "{name!r} differs from {other!r} only in case: their C macros will collide",
    "имя значения {name!r} — ключевое слово Python: сгенерированный модуль не загрузится":
        "value name {name!r} is a Python keyword: the generated module will not import",
    "значение {name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут":
        "value {name!r} differs from {other!r} only in case: their C macros will collide",
    "у физической величины {name!r} не указана единица (unit)": "physical quantity {name!r} has no unit",
    "invalid = {value} соответствует {phys:g} в пределах min..max: "
    "приёмник не отличит «нет данных» от реального значения":
        "invalid = {value} maps to {phys:g}, inside min..max: a receiver cannot tell "
        "\"not available\" from a real value",
    "селектор {name!r} не может иметь mux": "selector {name!r} cannot have mux",
    "сигнал {name!r} занимает байты {first}..{last}, а DLC = {dlc}":
        "signal {name!r} occupies bytes {first}..{last}, but DLC = {dlc}",
    "{key} не применяется при encoding: {encoding}": "{key} does not apply to encoding: {encoding}",
    "сигнал-флаг {name!r} длиной {bits} бит": "flag signal {name!r} is {bits} bits long",
    "сигнал {name!r}: float — 32 или 64 бита, задано {bits}":
        "signal {name!r}: float must be 32 or 64 bits, got {bits}",
    "сигнал {name!r} без описания": "signal {name!r} has no description",
    "у шины {name!r} нет названия (title)": "bus {name!r} has no name (title)",
    "у устройства {name!r} нет полного названия (title)": "device {name!r} has no full name (title)",
    "signed_code у беззнакового сигнала {name!r} не используется":
        "signed_code is ignored on unsigned signal {name!r}",
    "{path}: DBC хранит знаковые значения только в дополнительном коде, сигналы в обратном "
    "или прямом коде записаны как дополнительный: {names}":
        "{path}: DBC stores signed values in two's complement only; signals in ones' complement or "
        "sign and magnitude are written as two's complement: {names}",
    "{name!r}: DBC хранит знаковые значения только в дополнительном коде, в DBC-файле сигнал будет прочитан иначе":
        "{name!r}: DBC stores signed values in two's complement only, so the DBC file reads this signal differently",
    "имя {name!r} у значений {a} и {b}": "name {name!r} is used for values {a} and {b}",
    "флаг {name!r} (биты {first}..{last}) вне поля длиной {bits} бит":
        "flag {name!r} (bits {first}..{last}) is outside the {bits}-bit field",
    "файл логотипа не найден: {path}": "logo file not found: {path}",
    "address у устройства на шине {protocol}": "address set on a device on a {protocol} bus",
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
        "exchange {name!r} duplicates {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})",
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

    # ------------------------------------------------------------------ JSON Schema (подсказки в IDE)
    "mapcan — карта сигналов CAN (формат v1)": "mapcan — CAN signal map (format v1)",
    "Широковещательные кадры без устройства-владельца (NMT, SYNC, TIME).":
        "Broadcast frames without an owning device (NMT, SYNC, TIME).",
    "Короткое обозначение, напр. «BMS».": "Short designation, e.g. \"BMS\".",
    "CANopen: адрес узла 1..127.": "CANopen: node address 1..127.",
    "J1939: адрес источника 0..253.": "J1939: source address 0..253.",
    "Нумерация бит: lsb0 — бит 0 это младший бит байта 0. "
    "Поле фиксирует соглашение явно и выводится во всех документах.":
        "Bit numbering: lsb0 — bit 0 is the least significant bit of byte 0. "
        "The field states the convention explicitly and is shown in every document.",
    "Логотип предприятия: путь к PNG/JPG/SVG относительно файла карты.":
        "Company logo: path to a PNG/JPG/SVG relative to the map file.",
    "Обозначение документа, напр. «АБВГ.468332.001 Д1» (ЕСКД).":
        "Document designation, e.g. \"АБВГ.468332.001 Д1\" (ESKD).",
    "Литера документа (ЕСКД), напр. «О1».": "Document letter (ESKD), e.g. \"О1\".",
    "Город для титульного листа.": "City for the title page.",
    "Блок «УТВЕРЖДАЮ» титульного листа.": "The \"APPROVED\" block of the title page.",
    "Блоки «СОГЛАСОВАНО».": "The \"AGREED\" blocks.",
    "Флаг внутри битового поля. ``bit`` — смещение от младшего бита поля.":
        "A flag inside a bit field. ``bit`` is the offset from the field's least significant bit.",
    "Короткий заголовок, напр. «СОСТОЯНИЯ».": "Short heading, e.g. \"STATES\".",
    "Название сигнала для людей, напр. «Напряжение батареи».": "Human-readable signal name, e.g. \"Battery voltage\".",
    "Явный CAN ID. Для CANopen вычисляется из node_id, для J1939 — из PGN.":
        "Explicit CAN ID. For CANopen it is computed from node_id, for J1939 from the PGN.",
    "J1939: номер группы параметров (PGN).": "J1939: parameter group number (PGN).",
    "J1939: приоритет 0..7 (по умолчанию 6).": "J1939: priority 0..7 (6 by default).",
    "J1939: адрес получателя для PDU1 (по умолчанию 0xFF — всем).":
        "J1939: destination address for PDU1 (0xFF, global, by default).",
    "Устройства шины, принимающие кадр (имена).": "Bus devices that receive the frame (names).",
    "Устройство шины, передающее кадр, если это не его владелец: "
    "для RX-кадров (напр. PDO RX узла от мастера) и кадров шины (NMT, SYNC).":
        "Bus device that transmits the frame when it is not the frame's owner: for RX frames "
        "(e.g. a node's RPDO sent by the master) and bus frames (NMT, SYNC).",
    "Период циклической передачи, мс.": "Cyclic transmission period, ms.",
    "Нециклическая передача: event — по событию, on_request — по запросу.":
        "Non-cyclic transmission: event — on event, on_request — on request.",
    "Имя пользователя GitHub автора изменения.": "GitHub username of the change's author.",
    "Настраиваемые правила стиля (проверяются как warning).": "Configurable style rules (checked as warnings).",
    "Коды правил, которые нужно отключить.": "Codes of the rules to disable.",
    "Текст с переводами. Строка вместо объекта трактуется как язык документа.":
        "Text with translations. A plain string instead of an object is treated as text in the document language.",
    "Должностное лицо для блоков «УТВЕРЖДАЮ» / «СОГЛАСОВАНО».":
        "An official for the \"APPROVED\" / \"AGREED\" blocks.",
    "Один SDO-обмен (expedited): команда, индекс, субиндекс, значение.":
        "One SDO transfer (expedited): command, index, subindex, value.",
    "Байт команды (CCS/SCS), напр. 0x2B.": "Command byte (CCS/SCS), e.g. 0x2B.",
    "Кодирование значения: enum, metric, raw.": "Value encoding: enum, metric, raw.",
    "Кодирование сигнала: enum, flag, bitfield, metric, raw, float, bytes.":
        "Signal encoding: enum, flag, bitfield, metric, raw, float, bytes.",
    "Позиция младшего бита (LSB) сигнала в нумерации lsb0.":
        "Position of the signal's least significant bit (LSB) in lsb0 numbering.",
    "Первый байт сигнала.": "First byte of the signal.",
    "Смещение бита в байте.": "Bit offset within the byte.",
    "Код знакового числа: twos_complement — дополнительный (по умолчанию), "
    "ones_complement — обратный, sign_magnitude — прямой. Сгенерированный код C/Python "
    "кодирует значение в заданном коде; DBC хранит только дополнительный.":
        "Signed number encoding: twos_complement (default), ones_complement, sign_magnitude. "
        "Generated C/Python code encodes the value in this code; DBC stores two's complement only.",
    "Как показывать значения enum в документах.": "How enum values are shown in documents.",
    "Сигнал-селектор мультиплексора.": "Multiplexer selector signal.",
    "Значение(я) селектора, при которых сигнал присутствует.":
        "Selector value(s) for which the signal is present.",
    "Значение по умолчанию (в физических единицах).": "Default value (in physical units).",
    "Сырое значение (или значения), означающее «нет данных / недостоверно».":
        "Raw value (or values) meaning \"no data / invalid\".",
    "Подписи основной надписи ЕСКД (ГОСТ 2.104) и листов утверждения.":
        "Signatures for the ESKD title block (GOST 2.104) and approval sheets.",
    "Разраб.": "Developed by (Разраб.)",
    "Пров.": "Checked by (Пров.)",
    "Т. контр.": "Technical control (Т. контр.)",
    "Н. контр.": "Standards control (Н. контр.)",
    "Утв.": "Approved by (Утв.)",
    "Версия формата файла.": "File format version.",
    # ------------------------------------------------------------------ веб-редактор
    "папка не найдена: {path}": "folder not found: {path}",
    "карта не открыта": "no map is open",
    "в «{name}» есть несохранённые изменения": "“{name}” has unsaved changes",
    "нет доступа к папке: {path}": "access denied to folder: {path}",
    "ошибка {tool}": "{tool} error",
    "{tool} не ответил за {seconds} с": "{tool} did not respond within {seconds} s",
    "папка карты не в репозитории git": "the map folder is not in a git repository",
    "у репозитория нет удалённого репозитория (remote)": "the repository has no remote configured",
    "недопустимое имя репозитория: {name}": "invalid repository name: {name}",
    "GitHub CLI (gh) не установлен": "GitHub CLI (gh) is not installed",
    "у репозитория уже есть remote «{remote}»": "the repository already has the remote “{remote}”",
    "сначала закоммитьте карту": "commit the map first",
    "недопустимая ревизия: {rev}": "invalid revision: {rev}",
    "сначала сохраните карту": "save the map first",
    "недопустимое имя тега: {name}": "invalid tag name: {name}",
    "укажите описание коммита": "enter a commit message",
    "нет изменений для коммита": "nothing to commit",
    "папка уже в репозитории git": "the folder is already in a git repository",
    "тег {name} уже существует": "the tag {name} already exists",
    "в ревизии {rev} нет файла карты": "the map file does not exist in revision {rev}",
    "файл карты исключён через .gitignore — уберите его оттуда":
        "the map file is excluded by .gitignore; remove it from there",
    "HEAD не на ветке: переключитесь на ветку, чтобы отправить изменения":
        "HEAD is detached; switch to a branch to push changes",
    "git не знает автора коммита: укажите имя и GitHub в профиле mapcan "
    "или выполните git config --global user.name / user.email":
        "git does not know the commit author: enter your name and GitHub in the mapcan profile "
        "or run git config --global user.name / user.email",
    "ветка разошлась с {upstream}: и здесь, и на сервере есть свои коммиты. Объедините их в терминале "
    "(git pull --rebase или git merge) и повторите.":
        "the branch has diverged from {upstream}: both this copy and the server have their own commits. "
        "Combine them in a terminal (git pull --rebase or git merge) and try again.",
    "получение изменений перезапишет незакоммиченные правки: сначала закоммитьте их":
        "pulling would overwrite uncommitted changes; commit them first",
    "на сервере есть коммиты, которых нет здесь: сначала получите изменения (pull)":
        "the server has commits that are not here; pull the changes first",
    "редактор запущен в режиме только для чтения": "the editor is running in read-only mode",
    "неверный токен экземпляра": "invalid instance token",
    "{path}: символы {chars} не входят в кодировку {encoding} и записаны как «?»":
        "{path}: characters {chars} are not in the {encoding} encoding and were written as '?'",
    "недопустимый заголовок Host": "invalid Host header",
    "запрос с чужой страницы отклонён": "request from another site rejected",
    "неизвестный формат: {fmt}": "unknown format: {fmt}",
    "неизвестный шаблон PDF: {template}": "unknown PDF template: {template}",
    "карта содержит ошибки структуры — экспорт невозможен": "the map has structural errors and cannot be exported",
    "логотип не задан или файл не найден": "no logo is set or the file was not found",
    "поддерживаются {formats}": "supported formats: {formats}",
    "файл больше {mb} МБ": "the file is larger than {mb} MB",
    "{label}: карта не загружается: {errors}": "{label}: the map failed to load: {errors}",
    "текущая карта содержит ошибки структуры": "the current map has structural errors",
    "не удалось сохранить настройки: {error}": "could not save settings: {error}",
    "файл не найден: {path}": "file not found: {path}",
    "файл уже существует: {path}": "file already exists: {path}",
    "ошибка экспорта {fmt}: {error}": "{fmt} export error: {error}",
    "файл не в UTF-8": "the file is not UTF-8 encoded",
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
    # ------------------------------------------------------------------ языковой сервер
    "Языковой сервер (LSP) через stdio: проверка и подсказки в VS Code и других редакторах.":
        "Language server (LSP) over stdio: validation and hints in VS Code and other editors.",
    "Языковому серверу нужен пакет pygls: pip install \"mapcan[lsp]\"":
        "The language server needs the pygls package: pip install \"mapcan[lsp]\"",
    "биты {msb}…{lsb} (BE)": "bits {msb}…{lsb} (BE)",
    "биты {lo}–{hi}": "bits {lo}–{hi}",
    "единица: {unit}": "unit: {unit}",
    "диапазон: {lo} … {hi}": "range: {lo} … {hi}",
    "цикл {ms} мс": "cycle {ms} ms",
    "Значение": "Value",
    "Имя": "Name",
    "Бит": "Bit",
    "Флаг": "Flag",
    "Байт": "Byte",
    "Экспорт отменён: в карте есть ошибки ({errors}). Исправьте их и повторите.":
        "Export canceled: the map has errors ({errors}). Fix them and try again.",
    "Сохраните карту в файл перед экспортом.": "Save the map to a file before exporting.",
    "Ошибка экспорта: {error}": "Export failed: {error}",
    "Заменить на {value}": "Change to {value}",
    "Заменить на {value!r}": "Change to {value!r}",
    "Добавить extended: true": "Add extended: true",
    "Удалить destination": "Remove destination",
    "Переименовать в {value!r}": "Rename to {value!r}",
    "Переместить на свободные биты: {bits}": "Move to free bits: {bits}",
    "Вставить пробел после «-»": "Insert a space after '-'",
    "Заменить тип на {value}": "Change type to {value}",
    "Карта не разобрана: исправьте ошибки, чтобы увидеть документ.":
        "The map cannot be read: fix the errors to see the document.",
    "Карта не разобрана: исправьте ошибки, чтобы сравнить версии.":
        "The map cannot be read: fix the errors to compare versions.",
    "Версия карты из истории не разобрана.":
        "A version of the map from the history cannot be read.",
    "Историю изменений, записанную в одну строку, нельзя дополнить.":
        "The revision history is written on one line and cannot be extended.",
    "Документ не является картой mapcan.": "The document is not a mapcan map.",
    "в YAML синтаксическая ошибка": "the YAML has a syntax error",
    "Версия {version}": "Version {version}",
    "укажите версию": "enter a version",
}
