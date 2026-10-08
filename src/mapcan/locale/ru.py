"""Russian translations of the interface messages (key: the English text in the code, see :mod:`mapcan.i18n`)."""

RU: dict[str, str] = {
    # ------------------------------------------------------------------ CLI
    "errors: {errors}, warnings: {warnings}, notes: {infos}":
        "ошибок: {errors}, предупреждений: {warnings}, замечаний: {infos}",
    "mapcan — CAN signal map in YAML → validation, documentation, code.":
        "mapcan — карта сигналов CAN в YAML → проверка, документация, код.",
    "Export documents and files for third-party tools.": "Экспорт документов и файлов для сторонних инструментов.",
    "Code generation.": "Генерация кода.",
    "Map YAML file.": "YAML-файл карты.",
    "Document language (ISO 639-1 code: ru, en, de…); defaults to the map's language.":
        "Язык документа (код ISO 639-1: ru, en, de…); по умолчанию из карты.",
    "Generate even if validation reports errors.": "Генерировать, даже если есть ошибки проверки.",
    "Validate the map. Exit code 1 on errors (and on warnings with --strict).":
        "Проверить карту. Код возврата 1 при ошибках (и предупреждениях с --strict).",
    "mapcan {version}: {path} → {url}  (Ctrl+C to stop)": "mapcan {version}: {path} → {url}  (Ctrl+C — остановить)",
    "Browser-based editor (for servers and development; on a desktop, `mapcan app` is more convenient).":
        "Веб-редактор в браузере (для сервера и разработки; на рабочем месте удобнее `mapcan app`).",
    "Editor in its own window (pywebview); running it again opens the file in the existing window.":
        "Редактор в отдельном окне (pywebview); повторный запуск открывает файл в уже запущенном окне.",
    "Compare two versions of a map (frames, signals, values) and print a changelog.":
        "Сравнить две версии карты (кадры, сигналы, значения) и вывести changelog.",
    "List validation rules.": "Список правил проверки.",
    "Print the format's JSON Schema (for IDE hints).": "Вывести JSON Schema формата (для подсказок в IDE).",
    "List PDF templates or copy a built-in template to customize the layout.":
        "Список шаблонов PDF или копия встроенного шаблона для правки (своё оформление).",
    "Excel: addressing, contents, bit maps, changes.": "Excel: адресация, содержание, битовые карты, изменения.",
    "PDF via Typst: title page, contents, bit diagrams, tables; ESKD template.":
        "PDF через Typst: титул, оглавление, битовые диаграммы, таблицы; шаблон ЕСКД.",
    "Markdown for a README or wiki.": "Markdown для README/вики.",
    "Self-contained HTML page with search.": "Самодостаточная HTML-страница с поиском.",
    "DBC (one file per bus).": "DBC (по файлу на шину).",
    "C: #define IDs, enums, masks, structs, pack/unpack.": "C: #define ID, enum, маски, структуры, pack/unpack.",
    "Python module with the same structures (for tests and test benches).":
        "Python-модуль с теми же структурами (для тестов и стендов).",
    "Validate the map and build all artifacts (for CI).": "Проверить карту и собрать все артефакты (для CI).",
    "Generation aborted: {summary}. Fix the errors (mapcan validate) or use --force.":
        "Генерация прервана: {summary}. Исправьте ошибки (mapcan validate) или используйте --force.",
    "Show the version.": "Показать версию.",
    "Treat warnings as errors.": "Считать предупреждения ошибками.",
    "Output format.": "Формат вывода.",
    "Show info-level notes.": "Показывать замечания уровня info.",
    "Disable a rule (may be repeated).": "Отключить правило (можно несколько раз).",
    "Map to open, or a working folder. Without an argument, the start screen is shown.":
        "Карта для открытия или рабочая папка. Без аргумента — стартовый экран.",
    "Address to listen on.": "Адрес для прослушивания.",
    "Port; defaults to 8765 or any free port.": "Порт; по умолчанию 8765 или свободный.",
    "View only, no saving.": "Только просмотр, без сохранения.",
    "Do not open a browser.": "Не открывать браузер.",
    "Warning: the editor is reachable over the network ({host}) without authentication. Anyone who opens the address "
    "can open and change files.":
        "Внимание: редактор доступен по сети ({host}) без аутентификации. Любой, кто откроет адрес, сможет открывать "
        "и менять файлы.",
    "Open in a browser instead of the app window.": "Открыть в браузере вместо окна приложения.",
    "Old version of the map.": "Старая версия карты.",
    "New version of the map.": "Новая версия карты.",
    "JSON Schema file.": "Файл JSON Schema.",
    "Where to save the template copy.": "Куда сохранить копию шаблона.",
    "Built-in PDF template (see --list).": "Встроенный PDF-шаблон (см. --list).",
    "Show built-in PDF templates.": "Показать встроенные шаблоны PDF.",
    "specify -o/--output": "укажите -o/--output",
    "YAML file with styling.": "YAML с оформлением.",
    "Built-in template (mapcan, gost-2.105) or a path to your own .typ.":
        "Встроенный шаблон (mapcan, gost-2.105) или путь к своему .typ.",
    "Folder with additional fonts.": "Каталог с дополнительными шрифтами.",
    "Custom Jinja2 template.": "Свой Jinja2-шаблон.",
    ".dbc file (single bus) or a folder.": "Файл .dbc (одна шина) или каталог.",
    "Only the given bus.": "Только указанная шина.",
    "Folder for .h/.c files.": "Каталог для .h/.c.",
    "Name prefix (e.g. ne_).": "Префикс имён (напр. ne_).",
    "Only the given buses.": "Только указанные шины.",
    "Folder for the modules.": "Каталог для модулей.",
    "Output folder.": "Каталог результатов.",
    "PDF template (may be repeated; mapcan by default).": "Шаблон PDF (можно несколько раз; по умолчанию mapcan).",
    "unknown formats: {formats}": "неизвестные форматы: {formats}",
    "Error: {error}": "Ошибка: {error}",
    "unknown language: {language}": "неизвестный язык: {language}",
    "{path}: the map could not be loaded": "{path}: карта не загружена",
    "no template {name!r}; available: {known}": "нет шаблона {name!r}; доступны: {known}",
    "Comma-separated: ": "Через запятую: ",
    # ------------------------------------------------------------------ экспорт
    "bus {name!r} not found": "шина {name!r} не найдена",
    "template not found: {template} (built-in: {known})": "шаблон не найден: {template} (встроенные: {known})",
    "mapcan — Standard layout": "mapcan — стандартное оформление",
    "Colored bit diagrams, headers and footers, free-form title page.":
        "Цветные битовые диаграммы, колонтитулы, титульный лист в свободной форме.",
    "ESKD — GOST 2.105 / 2.104": "ЕСКД — ГОСТ 2.105 / 2.104",
    "Design text document: frame, title block (forms 2 and 2a), additional columns, title page, change log sheet.":
        "Текстовый конструкторский документ: рамка, основная надпись (формы 2 и 2а), дополнительные графы, титульный "
        "лист, лист регистрации изменений.",
    "ESPD — GOST 19.104 / 19.106": "ЕСПД — ГОСТ 19.104 / 19.106",
    "Software document: approval sheet, title page, abstract, designation on every page, change log sheet.":
        "Программный документ: лист утверждения, титульный лист, аннотация, обозначение на каждой странице, лист "
        "регистрации изменений.",
    "Report — GOST 7.32-2017": "Отчёт — ГОСТ 7.32-2017",
    "Report: title page, list of contributors, abstract, contents, numbered tables, appendix.":
        "Отчёт: титульный лист, список исполнителей, реферат, содержание, нумерованные таблицы, приложение.",
    "Typst compilation error ({name}): {error}": "ошибка компиляции Typst ({name}): {error}",
    "unknown style parameter: {key}": "неизвестный параметр стиля: {key}",
    # ------------------------------------------------------------------ окно приложения
    "mapcan signal map editor.": "Редактор карты сигналов mapcan.",
    "map (.yaml) or working folder": "карта (.yaml) или рабочая папка",
    "open in a browser instead of the app window": "открыть в браузере вместо окна приложения",
    "view only": "только просмотр",
    "File not found:\n{path}": "Файл не найден:\n{path}",
    "Could not open {path}:\n{error}": "Не удалось открыть {path}:\n{error}",
    "mapcan {version}: {url}  (Ctrl+C to stop)": "mapcan {version}: {url}  (Ctrl+C — остановить)",
    "the mapcan server did not start (is the port in use?)": "сервер mapcan не запустился (порт занят?)",
    "the mapcan server did not respond in time": "сервер mapcan не ответил за отведённое время",
    "“{name}” has unsaved changes.\n\nSave before closing?":
        "В «{name}» есть несохранённые изменения.\n\nСохранить перед закрытием?",
    "Could not save {path}:\n{error}": "Не удалось сохранить {path}:\n{error}",
    "mapcan: the app window is unavailable ({error}), opening the browser":
        "mapcan: окно приложения недоступно ({error}), открываю браузер",
    # ------------------------------------------------------------------ загрузка
    "key": "ключ",
    "value": "значение",
    "unknown field {name!r}": "неизвестное поле {name!r}",
    "{what} {value!r}: decimal comma used, should be {fixed!r}":
        "{what} {value!r}: дробная часть отделена запятой, нужно {fixed!r}",
    "{what} {value!r}: the 0x prefix uses a Cyrillic “х”":
        "{what} {value!r}: в префиксе 0x используется кириллическая «х»",
    "{what} {value!r} is written as a string; remove the quotes": "{what} {value!r} записано строкой; уберите кавычки",
    "missing required field {name!r}": "отсутствует обязательное поле {name!r}",
    "duplicate key: {problem}": "повторяющийся ключ: {problem}",
    "empty file": "пустой файл",
    "specify either start_bit or byte/bit, not both": "укажите либо start_bit, либо byte/bit, но не оба способа",
    "signal length is not set: bit_length or byte_length": "не задана длина сигнала: bit_length или byte_length",
    "specify either bit_length or byte_length": "укажите либо bit_length, либо byte_length",
    "signal position is not set (start_bit or byte)": "не задана позиция сигнала (start_bit или byte)",
    "“{value}” is not a GitHub username": "«{value}» — не имя пользователя GitHub",
    # ------------------------------------------------------------------ правила проверки
    "YAML syntax error, duplicate key": "Синтаксическая ошибка YAML, повторяющийся ключ",
    "Schema violation: wrong type, missing required field or invalid value":
        "Нарушение структуры: тип, обязательное поле, недопустимое значение",
    "Number written with a decimal comma (0,1 instead of 0.1)": "Число записано через запятую (0,1 вместо 0.1)",
    "Cyrillic “х” in a hexadecimal number": "Кириллическая «х» в шестнадцатеричном числе",
    "Number written as a quoted string": "Число записано строкой в кавычках",
    "Name cannot be used as a C/Python identifier": "Имя нельзя использовать как идентификатор C/Python",
    "Duplicate device name on the bus": "Повтор имени устройства на шине",
    "Duplicate node_id on the bus": "Повтор node_id на шине",
    "CANopen node_id outside 1..127": "node_id CANopen вне диапазона 1..127",
    "Duplicate frame name on the bus": "Повтор имени кадра на шине",
    "Cannot determine the frame's CAN ID": "Невозможно определить CAN ID кадра",
    "Duplicate CAN ID on the bus": "Повтор CAN ID на шине",
    "CAN ID does not fit in 11 bits (needs extended: true)": "CAN ID не помещается в 11 бит (нужно extended: true)",
    "Invalid DLC": "Недопустимый DLC",
    "Duplicate signal/flag name in the frame": "Повтор имени сигнала/флага в кадре",
    "Signal extends beyond the DLC": "Сигнал выходит за пределы DLC",
    "Overlapping signals (multiplexing-aware)": "Пересечение сигналов по битам (с учётом мультиплексирования)",
    "Enum value does not fit in the field width": "Значение enum не помещается в разрядность поля",
    "Same name for different enum values": "Одинаковое имя у разных значений enum",
    "Field does not apply to the signal encoding": "Поле не применимо к кодированию сигнала",
    "Flag extends beyond the bit field": "Флаг выходит за пределы битового поля",
    "Flags overlap inside the bit field": "Пересечение флагов внутри битового поля",
    "Flag signal longer than 1 bit": "Сигнал типа flag длиной больше 1 бита",
    "Zero factor": "Нулевой масштаб",
    "min/max outside the range the field can represent": "min/max вне диапазона, представимого полем",
    "min is greater than max": "min больше max",
    "Multiplexed signal in a frame without a selector": "Мультиплексированный сигнал в кадре без селектора",
    "More than one selector in the frame": "Больше одного селектора в кадре",
    "mux value does not fit in the selector": "Значение mux не помещается в селектор",
    "mux value is not in the selector's value table": "Значения mux нет в таблице значений селектора",
    "Selector is itself multiplexed": "Селектор сам мультиплексирован",
    "cycle_ms is set together with trigger": "cycle_ms задан вместе с trigger",
    "Direction conflicts with the CANopen frame type": "Направление противоречит типу кадра CANopen",
    "CANopen frame type on a non-CANopen bus": "Тип кадра CANopen на шине не CANopen",
    "sdo description on a frame that is not sdo_tx/sdo_rx": "Описание sdo у кадра не типа sdo_tx/sdo_rx",
    "Duplicate SDO exchange (command, index, subindex)": "Повтор SDO-обмена (команда, индекс, субиндекс)",
    "Name does not match the style rule (lint)": "Имя не соответствует правилу стиля (lint)",
    "The same value name is spelled differently": "Одно и то же имя значения записано по-разному",
    "J1939 address outside 0..253 or repeated on the bus": "Адрес J1939 вне 0..253 или повторяется на шине",
    "PDU1 PGN (PF < 240) with a non-zero low byte": "PDU1-PGN (PF < 240) с ненулевым младшим байтом",
    "destination set for a PDU2 PGN (PF ≥ 240) and unused":
        "destination задан для PDU2-PGN (PF ≥ 240) и не используется",
    "pgn/priority/destination/address/spn on a non-J1939 bus": "pgn/priority/destination/address/spn на шине не J1939",
    "Frame receiver is not defined on the bus": "Получатель кадра не описан на шине",
    "Frame sender is not defined on the bus": "Отправитель кадра не описан на шине",
    "sender conflicts with the frame direction or matches a receiver":
        "sender противоречит направлению кадра или совпадает с получателем",
    "RX frame duplicates another device's frame (describe the frame at its sender)":
        "RX-кадр повторяет кадр другого устройства (описывайте кадр у отправителя)",
    "RX frame without a sender": "RX-кадр без отправителя",
    "A float signal must be 32 or 64 bits": "Сигнал float должен быть 32 или 64 бита",
    "Default value outside the signal's range": "Значение по умолчанию вне диапазона сигнала",
    "invalid value does not fit in the signal width": "Значение invalid не помещается в разрядность сигнала",
    "Logo file not found": "Файл логотипа не найден",
    "Unsupported logo format": "Неподдерживаемый формат логотипа",
    "Signal has no description": "Нет описания сигнала",
    "Bus or device has no full name": "Нет полного названия шины или устройства",
    "Signed number code cannot be expressed in DBC or is set on an unsigned signal":
        "Код знакового числа не выражается в DBC или задан у беззнакового сигнала",
    "Frame has no signals": "В кадре не описаны сигналы",
    # ------------------------------------------------------------------ сообщения проверки
    "frame name": "имя кадра",
    "device name": "имя устройства",
    "value name": "имя значения",
    "flag name": "имя флага",
    "signal name": "имя сигнала",
    "flag": "флаг",
    "signal": "сигнал",
    "{what} {name!r}: only Latin letters, digits and _ are allowed":
        "{what} {name!r}: допустимы латинские буквы, цифры и _",
    "{what} {name!r} is not in {style} style": "{what} {name!r} не в стиле {style}",
    "{fields} set on a frame on a {protocol} bus": "{fields} у кадра на шине {protocol}",
    "type {type} on a bus with protocol {protocol}": "тип {type} на шине с протоколом {protocol}",
    "a {type} frame is usually {expected} for the device, but {actual} is set":
        "кадр {type} обычно {expected} для устройства, указано {actual}",
    "second selector {name!r}": "второй селектор {name!r}",
    "logo {logo!r}: supported formats are {formats}": "логотип {logo!r}: поддерживаются {formats}",
    "device {name!r} is already defined": "устройство {name!r} уже описано",
    "frame {name!r} is already defined on the bus": "кадр {name!r} уже описан на шине",
    "CAN ID {can_id:#05x} of frame {name!r} matches frame {other!r}":
        "CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}",
    "CAN ID {can_id:#x} > 0x7FF": "CAN ID {can_id:#x} > 0x7FF",
    "DLC {dlc} is not valid for CAN FD": "DLC {dlc} недопустим для CAN FD",
    "brs is set on a bus that is not CAN FD and is not used": "brs задан на шине не CAN FD и не используется",
    "brs on a bus without fd: true is not used": "brs у шины без fd: true не используется",
    "brs of a frame on a bus without fd: true is not used": "brs у кадра на шине без fd: true не используется",
    "CAN FD: bit rate switch (BRS), the data phase is sent at the data bit rate. Empty: as set on the bus.":
        "CAN FD: переключение скорости (BRS) — данные на скорости фазы данных. Пусто — как у шины.",
    "CAN FD: bit rate switch (BRS) of the frames by default. Empty: on.":
        "CAN FD: переключение скорости (BRS) у кадров по умолчанию. Пусто — включено.",
    "DLC {dlc} > 8 (for CAN FD set fd: true on the bus)": "DLC {dlc} > 8 (для CAN FD укажите fd: true у шины)",
    "receiver {name!r} is not defined on bus {bus!r}": "получатель {name!r} не описан на шине {bus!r}",
    "sender {name!r} is not defined on bus {bus!r}": "отправитель {name!r} не описан на шине {bus!r}",
    "frame {name!r} is transmitted by device {device!r} itself (TX); sender {sender!r} conflicts with the direction":
        "кадр {name!r} передаёт само устройство {device!r} (TX), sender {sender!r} противоречит направлению",
    "device {device!r} receives frame {name!r} (RX) and cannot be its sender":
        "устройство {device!r} принимает кадр {name!r} (RX) и не может быть его отправителем",
    "sender {name!r} is listed among the frame receivers": "отправитель {name!r} указан среди получателей кадра",
    "RX frame {name!r} has no sender: if the sender is on the bus, set sender or move the frame to the sender and add "
    "{device!r} to receivers":
        "RX-кадр {name!r} без отправителя: если он описан на шине, укажите sender или перенесите кадр к отправителю и "
        "добавьте {device!r} в receivers",
    "RX frame {name!r} of device {device!r} duplicates frame {other!r} of sender {sender!r} (CAN ID {can_id:#05x}): "
    "describe the frame once at the sender and add {device!r} to receivers":
        "RX-кадр {name!r} устройства {device!r} повторяет кадр {other!r} отправителя {sender!r} (CAN ID "
        "{can_id:#05x}): опишите кадр один раз у отправителя и добавьте {device!r} в receivers",
    "PGN {pgn:#06x} is PDU1: the low byte must be 0 (the destination address is set by destination)":
        "PGN {pgn:#06x} — PDU1: младший байт должен быть 0 (адрес получателя задаётся destination)",
    "PGN {pgn:#06x} is PDU2 (broadcast), destination is not used":
        "PGN {pgn:#06x} — PDU2 (широковещательный), destination не используется",
    "cycle_ms is set on a frame with trigger: {trigger}": "cycle_ms задан у кадра с trigger: {trigger}",
    "sdo set on a frame of type {type}": "sdo у кадра типа {type}",
    "frame {name!r} has no signals": "кадр {name!r} без сигналов",
    "unknown field {name!r}: if this is meant to be a list item, add a space after '-'":
        "неизвестное поле {name!r}: если это элемент списка, после «-» нужен пробел",
    "a list is expected: if {name!r} is meant to be a list item, add a space after '-'":
        "ожидается список: если {name!r} — его элемент, после «-» нужен пробел",
    "missing space after '-': write the list item as '- {item}'":
        "после «-» нужен пробел: элемент списка записывается как «- {item}»",
    "tab character: YAML indentation must use spaces only":
        "символ табуляции: отступы в YAML делаются только пробелами",
    "unexpected list item '-': a key of the block that starts on line {start} was expected here; check the indentation":
        "элемент списка «-» не на своём месте: здесь ожидался ключ блока, начатого в строке {start}; проверьте отступ",
    "bad indentation: this line does not line up with the block that starts on line {start}":
        "неверный отступ: строка не выровнена по блоку, начатому в строке {start}",
    "unexpected ':': quote a value that contains ': ', or check that the previous line has ':' after its key":
        "лишнее «:» — возьмите значение, содержащее «: », в кавычки или проверьте, что у предыдущей строки есть «:» "
        "после ключа",
    "the quote opened on line {start} is never closed": "кавычка, открытая в строке {start}, не закрыта",
    "the '[' opened on line {start} is not closed, or its items are not separated by commas":
        "«[», открытая в строке {start}, не закрыта или элементы не разделены запятой",
    "the '{{' opened on line {start} is not closed, or its items are not separated by commas":
        "«{{», открытая в строке {start}, не закрыта или элементы не разделены запятой",
    "DLC of a CANopen service frame does not match CiA 301": "DLC служебного кадра CANopen не соответствует CiA 301",
    "Non-standard bus bit rate": "Нестандартная скорость шины",
    "Estimated bus load from cyclic frames above 70%": "Расчётная загрузка шины циклическими кадрами выше 70 %",
    "Name is a C/Python keyword or a member of the generated class":
        "Имя совпадает с ключевым словом C/Python или членом сгенерированного класса",
    "Names collide in generated code (differ only in case, or clash with a _phys property)":
        "Имена совпадают в сгенерированном коде (различаются только регистром или совпадают со свойством _phys)",
    "invalid value falls inside the min..max range": "Значение invalid попадает в рабочий диапазон min..max",
    "Physical quantity without a unit": "Физическая величина без единицы измерения",
    "Frame has no receivers on the bus": "У кадра нет получателей на шине",
    "Duplicate device short label on the bus": "Повтор короткого обозначения устройства на шине",
    "Document version differs from the latest revision history entry":
        "Версия документа не совпадает с последней записью истории",
    "document version is {version!r}, but the latest revision history entry is {latest!r}":
        "версия документа {version!r}, а последняя запись истории — {latest!r}",
    "bit rate {bitrate} bit/s is not a standard value (125000, 250000, 500000, 1000000…)":
        "скорость {bitrate} бит/с не входит в стандартный ряд (125000, 250000, 500000, 1000000…)",
    "short label {short!r} is already used by device {other!r}": "обозначение {short!r} уже у устройства {other!r}",
    "frame {name!r} differs from {other!r} only in case: their C macros will collide":
        "кадр {name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут",
    "estimated load of bus {bus!r} is {load:.0f}% (cyclic frames: {count}, {bitrate} bit/s); keep it at or below "
    "{limit}%":
        "расчётная загрузка шины {bus!r} — {load:.0f} % (циклических кадров: {count}, {bitrate} бит/с), рекомендуется "
        "не больше {limit} %",
    "a {type} frame has DLC {expected} under CiA 301, but {dlc} is set":
        "кадр {type} по CiA 301 имеет DLC {expected}, указано {dlc}",
    "nobody receives frame {name!r}: list the receiving devices in receivers":
        "кадр {name!r} никто не принимает: укажите получателей в receivers",
    "signal name {name!r} is a C/Python keyword: the generated code will not compile":
        "имя сигнала {name!r} — ключевое слово C/Python: сгенерированный код не скомпилируется",
    "signal name {name!r} clashes with a frame class member in the Python module ({members})":
        "имя сигнала {name!r} совпадает с членом класса кадра в Python-модуле ({members})",
    "signal {name!r} clashes with the physical value property of signal {other!r} in the Python module":
        "сигнал {name!r} совпадает со свойством физического значения сигнала {other!r} в Python-модуле",
    "{name!r} differs from {other!r} only in case: their C macros will collide":
        "{name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут",
    "value name {name!r} is a Python keyword: the generated module will not import":
        "имя значения {name!r} — ключевое слово Python: сгенерированный модуль не загрузится",
    "value {name!r} differs from {other!r} only in case: their C macros will collide":
        "значение {name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут",
    "physical quantity {name!r} has no unit": "у физической величины {name!r} не указана единица (unit)",
    "invalid = {value} maps to {phys:g}, inside min..max: a receiver cannot tell \"not available\" from a real value":
        "invalid = {value} соответствует {phys:g} в пределах min..max: приёмник не отличит «нет данных» от реального "
        "значения",
    "selector {name!r} cannot have mux": "селектор {name!r} не может иметь mux",
    "signal {name!r} occupies bytes {first}..{last}, but DLC = {dlc}":
        "сигнал {name!r} занимает байты {first}..{last}, а DLC = {dlc}",
    "{key} does not apply to encoding: {encoding}": "{key} не применяется при encoding: {encoding}",
    "flag signal {name!r} is {bits} bits long": "сигнал-флаг {name!r} длиной {bits} бит",
    "signal {name!r}: float must be 32 or 64 bits, got {bits}":
        "сигнал {name!r}: float — 32 или 64 бита, задано {bits}",
    "signal {name!r} has no description": "сигнал {name!r} без описания",
    "bus {name!r} has no name (title)": "у шины {name!r} нет названия (title)",
    "device {name!r} has no full name (title)": "у устройства {name!r} нет полного названия (title)",
    "signed_code is ignored on unsigned signal {name!r}": "signed_code у беззнакового сигнала {name!r} не используется",
    "{path}: DBC stores signed values in two's complement only; signals in ones' complement or sign and magnitude are "
    "written as two's complement: {names}":
        "{path}: DBC хранит знаковые значения только в дополнительном коде, сигналы в обратном или прямом коде "
        "записаны как дополнительный: {names}",
    "{name!r}: DBC stores signed values in two's complement only, so the DBC file reads this signal differently":
        "{name!r}: DBC хранит знаковые значения только в дополнительном коде, в DBC-файле сигнал будет прочитан иначе",
    "name {name!r} is used for values {a} and {b}": "имя {name!r} у значений {a} и {b}",
    "flag {name!r} (bits {first}..{last}) is outside the {bits}-bit field":
        "флаг {name!r} (биты {first}..{last}) вне поля длиной {bits} бит",
    "logo file not found: {path}": "файл логотипа не найден: {path}",
    "address set on a device on a {protocol} bus": "address у устройства на шине {protocol}",
    "address {address:#04x} is already used by device {other!r}":
        "адрес {address:#04x} уже занят устройством {other!r}",
    "address {address:#04x} outside 0..253 (254, 255 are reserved)":
        "адрес {address:#04x} вне 0..253 (254, 255 — служебные)",
    "node_id {node_id:#x} outside 1..127": "node_id {node_id:#x} вне 1..127",
    "node_id {node_id:#04x} is already used by device {other!r}":
        "node_id {node_id:#04x} уже занят устройством {other!r}",
    "pgn (or id) is required": "нужен pgn (или id)",
    "the device has no address": "у устройства нет address",
    "frame {name!r}: {why}": "кадр {name!r}: {why}",
    "frame {name!r}: type {type} needs an explicit id": "кадр {name!r}: для типа {type} нужен явный id",
    "frame {name!r}: the device has no node_id to compute the {type} ID":
        "кадр {name!r}: нет node_id у устройства для вычисления ID {type}",
    "exchange {name!r} duplicates {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})":
        "обмен {name!r} повторяет {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})",
    "flag {name!r} already exists in frame {frame!r} ({other})": "флаг {name!r} уже есть в кадре {frame!r} ({other})",
    "signal {name!r} already exists in frame {frame!r} ({other})":
        "сигнал {name!r} уже есть в кадре {frame!r} ({other})",
    "value {value} ({name}) does not fit in {bits} bits (signed: {lo}..{hi})":
        "значение {value} ({name}) не помещается в {bits} бит (знаковое: {lo}..{hi})",
    "value {value} ({name}) does not fit in {bits} bits (unsigned: {lo}..{hi})":
        "значение {value} ({name}) не помещается в {bits} бит (беззнаковое: {lo}..{hi})",
    "invalid = {value} does not fit in {bits} bits ({lo}..{hi})":
        "invalid = {value} не помещается в {bits} бит ({lo}..{hi})",
    "initial = {value:g} → raw {raw} outside {lo}..{hi}": "initial = {value:g} → raw {raw} вне {lo}..{hi}",
    "initial = {value:g} outside min/max": "initial = {value:g} вне min/max",
    "signal {name!r} has mux, but the frame has no multiplexer":
        "у сигнала {name!r} задан mux, но в кадре нет multiplexer",
    "flag {name!r} overlaps {other!r} at bit {bit}": "флаг {name!r} пересекается с {other!r} по биту {bit}",
    "value {value} does not fit in flag {name!r}": "значение {value} не помещается во флаг {name!r}",
    "bit {bit}": "бит {bit}",
    "bits {first}..{last}": "биты {first}..{last}",
    "signal {name!r} overlaps {other!r}: {bits} (byte {byte})":
        "сигнал {name!r} пересекается с {other!r}: {bits} (байт {byte})",
    "value {name!r} is spelled differently from {main!r} elsewhere":
        "значение {name!r} записано иначе, чем {main!r} в других местах",
    "min {min} > max {max}": "min {min} > max {max}",
    "mux {value} does not fit in selector {name!r}": "mux {value} не помещается в селектор {name!r}",
    "mux {value} is missing from the values of selector {name!r}":
        "mux {value} отсутствует в values селектора {name!r}",
    "{key} = {value:g} is outside the representable range {lo:g}..{hi:g} {unit}":
        "{key} = {value:g} вне представимого диапазона {lo:g}..{hi:g} {unit}",
    # ------------------------------------------------------------------ JSON Schema (подсказки в IDE)
    "mapcan — CAN signal map (format v1)": "mapcan — карта сигналов CAN (формат v1)",
    "Broadcast frames without an owning device (NMT, SYNC, TIME).":
        "Широковещательные кадры без устройства-владельца (NMT, SYNC, TIME).",
    "CANopen: node address 1..127.": "CANopen: адрес узла 1..127.",
    "J1939: source address 0..253.": "J1939: адрес источника 0..253.",
    "Bit numbering: lsb0 — bit 0 is the least significant bit of byte 0. The field states the convention explicitly "
    "and is shown in every document.":
        "Нумерация бит: lsb0 — бит 0 это младший бит байта 0. Поле фиксирует соглашение явно и выводится во всех "
        "документах.",
    "Company logo: path to a PNG/JPG/SVG relative to the map file.":
        "Логотип предприятия: путь к PNG/JPG/SVG относительно файла карты.",
    "Document designation, e.g. \"АБВГ.468332.001 Д1\" (ESKD).":
        "Обозначение документа, напр. «АБВГ.468332.001 Д1» (ЕСКД).",
    "Document letter (ESKD), e.g. \"О1\".": "Литера документа (ЕСКД), напр. «О1».",
    "City for the title page.": "Город для титульного листа.",
    "The \"APPROVED\" block of the title page.": "Блок «УТВЕРЖДАЮ» титульного листа.",
    "The \"AGREED\" blocks.": "Блоки «СОГЛАСОВАНО».",
    "Explicit CAN ID. For CANopen it is computed from node_id, for J1939 from the PGN.":
        "Явный CAN ID. Для CANopen вычисляется из node_id, для J1939 — из PGN.",
    "J1939: parameter group number (PGN).": "J1939: номер группы параметров (PGN).",
    "J1939: priority 0..7 (6 by default).": "J1939: приоритет 0..7 (по умолчанию 6).",
    "J1939: destination address for PDU1 (0xFF, global, by default).":
        "J1939: адрес получателя для PDU1 (по умолчанию 0xFF — всем).",
    "Bus devices that receive the frame (names).": "Устройства шины, принимающие кадр (имена).",
    "Bus device that transmits the frame when it is not the frame's owner: for RX frames (e.g. a node's RPDO sent by "
    "the master) and bus frames (NMT, SYNC).":
        "Устройство шины, передающее кадр, если это не его владелец: для RX-кадров (напр. PDO RX узла от мастера) и "
        "кадров шины (NMT, SYNC).",
    "Cyclic transmission period, ms.": "Период циклической передачи, мс.",
    "Default document language: ISO 639-1 code (ru, en, de…).":
        "Язык документов по умолчанию: код ISO 639-1 (ru, en, de…).",
    "a translation key must be an ISO 639-1 language code (de, fr…)":
        "ключ перевода должен быть кодом языка ISO 639-1 (de, fr…)",
    "Frame DLC is not set": "Не задан DLC кадра",
    "The same SPN on several signals of the bus": "Один и тот же SPN у нескольких сигналов шины",
    "CANopen dictionary object on a non-PDO signal, outside 0x2000..0x9FFF or big-endian":
        "Объект словаря CANopen у сигнала не PDO, вне 0x2000..0x9FFF или big-endian",
    "The same dictionary object on several signals of a device": "Один объект словаря у нескольких сигналов устройства",
    "{name!r}: a dictionary object is set only on PDO signals of a device on a CANopen bus":
        "{name!r}: объект словаря задаётся только у сигналов PDO устройства на шине CANopen",
    "{name!r}: subindex without index": "{name!r}: subindex без index",
    "{name!r}: index {index:#06x} is outside the manufacturer and profile areas (0x2000..0x9FFF)":
        "{name!r}: индекс {index:#06x} вне областей производителя и профилей (0x2000..0x9FFF)",
    "{name!r}: CANopen PDOs carry little-endian data": "{name!r}: PDO CANopen передаёт данные little-endian",
    "object {index:04X}:{sub:02X} is already mapped by {other}": "объект {index:04X}:{sub:02X} уже у сигнала {other}",
    "CANopen: index of the dictionary object mapped into the PDO.":
        "CANopen: индекс объекта словаря, отображённого в PDO.",
    "CANopen: subindex of the dictionary object (0 by default).":
        "CANopen: субиндекс объекта словаря (по умолчанию 0).",
    "Signal longer than 64 bits that is not an aligned byte array":
        "Сигнал длиннее 64 бит, но не выровненный массив байт",
    "signal {name!r} is {bits} bits long: only a byte array (encoding: bytes, little-endian, starting at a byte "
    "boundary) can be longer than 64 bits":
        "сигнал {name!r} длиной {bits} бит: длиннее 64 бит может быть только массив байт (encoding: bytes, "
        "little-endian, с границы байта)",
    "A PGN longer than 8 bytes is sent with the J1939-21 transport protocol":
        "PGN длиннее 8 байт передаётся транспортным протоколом J1939-21",
    "{dlc}-byte PGN: sent with the J1939-21 transport protocol ({mode})":
        "PGN {dlc} байт: передаётся транспортным протоколом J1939-21 ({mode})",
    "spn on a signal of a {protocol} bus": "spn у сигнала на шине {protocol}",
    "SPN {spn} is already used by signal {other}": "SPN {spn} уже у сигнала {other}",
    "J1939: suspect parameter number (SPN) per SAE J1939-71.": "J1939: номер параметра (SPN) по SAE J1939-71.",
    "Data length, bytes. Required except for CANopen service frames (NMT, SYNC, TIME, Heartbeat, SDO), whose length "
    "is set by CiA 301. Up to 1785 bytes on a J1939 bus, with the transport protocol.":
        "Длина данных, байт. Обязательна, кроме служебных кадров CANopen (NMT, SYNC, TIME, Heartbeat, SDO): их длина "
        "задана CiA 301. На шине J1939 до 1785 байт — транспортным протоколом.",
    "Import a map from other tools' formats.": "Импорт карты из форматов других инструментов.",
    "EDS (CiA 306) for every device of the CANopen buses: PDO objects and their mapping.":
        "EDS (CiA 306) на каждое устройство шин CANopen: объекты PDO и их отображение.",
    "Directory for the .eds files.": "Каталог для .eds.",
    "{frame}: a multiplexed PDO is not mapped in the EDS": "{frame}: мультиплексированный PDO в EDS не отображается",
    "{frame}.{signal}: overlaps the previous object and is not mapped in the EDS":
        "{frame}.{signal}: пересекается с предыдущим объектом, в EDS не отображён",
    "DBC → YAML map: nodes, frames, signals, value tables, transmission modes.":
        "DBC → YAML-карта: узлы, кадры, сигналы, таблицы значений, режимы передачи.",
    "DBC file.": "DBC-файл.",
    "YAML map file; <name>.yaml by default.": "YAML-файл карты; по умолчанию <имя>.yaml.",
    "Document title; the file name by default.": "Название документа; по умолчанию имя файла.",
    "Document language (ISO 639-1 code).": "Язык документа (код ISO 639-1).",
    "Overwrite an existing file.": "Перезаписать существующий файл.",
    "{path} already exists; give another -o or --force": "{path} уже существует; укажите другой -o или --force",
    "{where}: the scale and offset of a signal with a value table are not imported":
        "{where}: у сигнала с таблицей значений масштаб и смещение не переносятся",
    "{frame}: the frame has several senders, the first is used": "{frame}: у кадра несколько отправителей, взят первый",
    "{frame}: sender {name!r} is not a DBC node": "{frame}: отправитель {name!r} не описан как узел DBC",
    "{frame}.{signal}: nested multiplexing is imported as one level":
        "{frame}.{signal}: вложенное мультиплексирование перенесено одним уровнем",
    "Included file is missing or has keys that cannot be included":
        "Подключаемый файл не найден или содержит недопустимые ключи",
    "No value table with this name in value_tables": "Таблица значений с таким именем не описана в value_tables",
    "include: the map has no path to resolve included files from":
        "include: у карты нет пути, подключать файлы не от чего",
    "include: file {name!r} not found": "include: файл {name!r} не найден",
    "an included file must be a YAML mapping": "подключаемый файл должен быть словарём YAML",
    "key {key!r} cannot be included: only buses and value_tables":
        "ключ {key!r} нельзя подключать: допустимы buses и value_tables",
    "the node is described in the included file {file}: edit it there":
        "узел описан в подключённом файле {file} — правьте его там",
    "value table {name!r} is already defined": "таблица значений {name!r} уже описана",
    "bus {name!r} is already defined: an included file can only add devices and frames to it, not {key!r}":
        "шина {name!r} уже описана: подключаемый файл может только добавить ей devices и frames, а не {key!r}",
    "value table {name!r} is not defined in value_tables": "таблица значений {name!r} не описана в value_tables",
    "Value table (value → name) or the name of a table in value_tables.":
        "Таблица значений (значение → имя) или имя таблицы из value_tables.",
    "Included files (paths relative to the map file): their buses, devices, frames and value_tables are added to the "
    "map.":
        "Подключаемые файлы (пути от файла карты): их шины, устройства, кадры и value_tables добавляются к карте.",
    "Named value tables: in a signal, values: <name>.": "Именованные таблицы значений: в сигнале — values: <имя>.",
    "frame {name!r}: dlc (data length, bytes) is not set": "кадр {name!r}: не задан dlc (длина данных, байт)",
    "Name for people, e.g. \"States\": the label in the map tree and the heading in documents.":
        "Название для людей, напр. «Состояния»: подпись в дереве карты и заголовок в документах.",
    "What it is and what for: shown in documents, comments of generated code and DBC.":
        "Что это и зачем: выводится в документах, комментариях сгенерированного кода и DBC.",
    "A note or caveat: \"Note:\" in documents, after the description in DBC.":
        "Примечание или оговорка: в документах — «Примечание:», в DBC — после описания.",
    "Device abbreviation, e.g. \"BMS\": in document tables and before the name in the tree.":
        "Сокращение устройства, напр. «BMS»: в таблицах документов и в дереве перед названием.",
    "Protocol: canopen — IDs from the frame type and node_id, j1939 — from the PGN and address, can — explicit IDs.":
        "Протокол: canopen — ID из типа кадра и node_id, j1939 — из PGN и адреса, can — явные ID.",
    "Non-cyclic transmission: event — on event, on_request — on request.":
        "Нециклическая передача: event — по событию, on_request — по запросу.",
    "GitHub username of the change's author.": "Имя пользователя GitHub автора изменения.",
    "Codes of the rules to disable.": "Коды правил, которые нужно отключить.",
    "Command byte (CCS/SCS), e.g. 0x2B.": "Байт команды (CCS/SCS), напр. 0x2B.",
    "Value encoding: enum, scaled, raw.": "Кодирование значения: enum, scaled, raw.",
    "Signal encoding: enum, flag, bitfield, scaled, raw, float, bytes.":
        "Кодирование сигнала: enum, flag, bitfield, scaled, raw, float, bytes.",
    "Position of the signal's least significant bit (LSB) in lsb0 numbering.":
        "Позиция младшего бита (LSB) сигнала в нумерации lsb0.",
    "First byte of the signal.": "Первый байт сигнала.",
    "Bit offset within the byte.": "Смещение бита в байте.",
    "Signed number encoding: twos_complement (default), ones_complement, sign_magnitude. Generated C/Python code "
    "encodes the value in this code; DBC stores two's complement only.":
        "Код знакового числа: twos_complement — дополнительный (по умолчанию), ones_complement — обратный, "
        "sign_magnitude — прямой. Сгенерированный код C/Python кодирует значение в заданном коде; DBC хранит только "
        "дополнительный.",
    "How enum values are shown in documents.": "Как показывать значения enum в документах.",
    "Multiplexer selector signal.": "Сигнал-селектор мультиплексора.",
    "Selector value(s) for which the signal is present.": "Значение(я) селектора, при которых сигнал присутствует.",
    "Default value (in physical units).": "Значение по умолчанию (в физических единицах).",
    "Raw value (or values) meaning \"no data / invalid\".":
        "Сырое значение (или значения), означающее «нет данных / недостоверно».",
    "Developed by (Разраб.)": "Разраб.",
    "Checked by (Пров.)": "Пров.",
    "Technical control (Т. контр.)": "Т. контр.",
    "Standards control (Н. контр.)": "Н. контр.",
    "Approved by (Утв.)": "Утв.",
    "File format version.": "Версия формата файла.",
    # ------------------------------------------------------------------ веб-редактор
    "folder not found: {path}": "папка не найдена: {path}",
    "no map is open": "карта не открыта",
    "“{name}” has unsaved changes": "в «{name}» есть несохранённые изменения",
    "access denied to folder: {path}": "нет доступа к папке: {path}",
    "{tool} error": "ошибка {tool}",
    "{tool} did not respond within {seconds} s": "{tool} не ответил за {seconds} с",
    "the map folder is not in a git repository": "папка карты не в репозитории git",
    "the repository has no remote configured": "у репозитория нет удалённого репозитория (remote)",
    "invalid repository name: {name}": "недопустимое имя репозитория: {name}",
    "GitHub CLI (gh) is not installed": "GitHub CLI (gh) не установлен",
    "the repository already has the remote “{remote}”": "у репозитория уже есть remote «{remote}»",
    "commit the map first": "сначала закоммитьте карту",
    "invalid revision: {rev}": "недопустимая ревизия: {rev}",
    "save the map first": "сначала сохраните карту",
    "invalid tag name: {name}": "недопустимое имя тега: {name}",
    "enter a commit message": "укажите описание коммита",
    "nothing to commit": "нет изменений для коммита",
    "the folder is already in a git repository": "папка уже в репозитории git",
    "the tag {name} already exists": "тег {name} уже существует",
    "the map file does not exist in revision {rev}": "в ревизии {rev} нет файла карты",
    "the map file is excluded by .gitignore; remove it from there":
        "файл карты исключён через .gitignore — уберите его оттуда",
    "HEAD is detached; switch to a branch to push changes":
        "HEAD не на ветке: переключитесь на ветку, чтобы отправить изменения",
    "git does not know the commit author: enter your name and GitHub in the mapcan profile or run git config --global "
    "user.name / user.email":
        "git не знает автора коммита: укажите имя и GitHub в профиле mapcan или выполните git config --global "
        "user.name / user.email",
    "the branch has diverged from {upstream}: both this copy and the server have their own commits. Combine them in a "
    "terminal (git pull --rebase or git merge) and try again.":
        "ветка разошлась с {upstream}: и здесь, и на сервере есть свои коммиты. Объедините их в терминале (git pull "
        "--rebase или git merge) и повторите.",
    "pulling would overwrite uncommitted changes; commit them first":
        "получение изменений перезапишет незакоммиченные правки: сначала закоммитьте их",
    "the server has commits that are not here; pull the changes first":
        "на сервере есть коммиты, которых нет здесь: сначала получите изменения (pull)",
    "the editor is running in read-only mode": "редактор запущен в режиме только для чтения",
    "invalid instance token": "неверный токен экземпляра",
    "{path}: characters {chars} are not in the {encoding} encoding and were written as '?'":
        "{path}: символы {chars} не входят в кодировку {encoding} и записаны как «?»",
    "invalid Host header": "недопустимый заголовок Host",
    "request from another site rejected": "запрос с чужой страницы отклонён",
    "unknown format: {fmt}": "неизвестный формат: {fmt}",
    "unknown PDF template: {template}": "неизвестный шаблон PDF: {template}",
    "the map has structural errors and cannot be exported": "карта содержит ошибки структуры — экспорт невозможен",
    "no logo is set or the file was not found": "логотип не задан или файл не найден",
    "supported formats: {formats}": "поддерживаются {formats}",
    "the file is larger than {mb} MB": "файл больше {mb} МБ",
    "{label}: the map failed to load: {errors}": "{label}: карта не загружается: {errors}",
    "the current map has structural errors": "текущая карта содержит ошибки структуры",
    "could not save settings: {error}": "не удалось сохранить настройки: {error}",
    "file not found: {path}": "файл не найден: {path}",
    "file already exists: {path}": "файл уже существует: {path}",
    "{fmt} export error: {error}": "ошибка экспорта {fmt}: {error}",
    "the file is not UTF-8 encoded": "файл не в UTF-8",
    "could not read {name}: {error}": "не удалось прочитать {name}: {error}",
    "could not create {path}: {error}": "не удалось создать {path}: {error}",
    "could not save {path}: {error}": "не удалось сохранить {path}: {error}",
    "could not save the logo: {error}": "не удалось сохранить логотип: {error}",
    "the file was changed on disk by another program": "файл изменён на диске другой программой",
    "the YAML has a syntax error; fix the text in the YAML tab":
        "в YAML синтаксическая ошибка — исправьте текст во вкладке YAML",
    # шаблоны новой карты (содержимое карты — на языке интерфейса)
    "CANopen: a bus and one device": "CANopen: шина и одно устройство",
    "SAE J1939: an ECU with one PGN": "SAE J1939: ECU с одним PGN",
    "CAN with explicit IDs: a bus and one device": "CAN с явными ID: шина и одно устройство",
    "Empty: just a bus": "Пустая: только шина",
    "unknown template: {template}": "неизвестный шаблон: {template}",
    "unknown example: {name}": "неизвестный пример: {name}",
    # примеры на стартовом экране
    "Minimal": "Минимальный",
    "SAE J1939": "SAE J1939",
    "Electric vehicle": "Электромобиль",
    "CANopen drive": "CANopen-привод",
    "Tractor: a map in several files": "Трактор: карта из нескольких файлов",
    "mapcan signal map (format v1).": "Карта сигналов mapcan (формат v1).",
    "Bytes and bits are numbered from 0; start_bit is the position of the least significant bit; physical = raw * "
    "factor + offset.":
        "Байты и биты нумеруются с 0; start_bit — позиция младшего бита; physical = raw * factor + offset.",
    "Map created.": "Создана карта.",
    "Bus 1": "Шина 1",
    "Device": "Устройство",
    "Device state": "Состояние устройства",
    "Status": "Статус",
    "New map": "Новая карта",
    "J1939 bus": "Шина J1939",
    "Control unit": "Блок управления",
    "Unit state": "Состояние блока",
    "Operating mode": "Режим работы",
    # операции редактора
    "empty path": "пустой путь",
    "path not found: {path}": "путь не найден: {path}",
    "parent is not a mapping: {path}": "родитель не словарь: {path}",
    "not a list: {path}": "не список: {path}",
    "only list items can be moved: {path}": "перемещать можно только элементы списка: {path}",
    "index out of range": "индекс вне списка",
    "index out of range: {path}": "индекс вне списка: {path}",
    "not a mapping: {path}": "не словарь: {path}",
    "key {key!r} already exists": "ключ {key!r} уже существует",
    "key not found: {path}": "ключ не найден: {path}",
    "not a signal: {path}": "не сигнал: {path}",
    "invalid position": "недопустимая позиция",
    "cannot remove: {path}": "нельзя удалить: {path}",
    "unknown operation: {op!r}": "неизвестная операция: {op!r}",
    "path must be a list": "path должен быть списком",
    "The interface is not built: run <code>npm run build</code> in <code>web/</code>. The API is available at <a "
    "href='/api/docs'>/api/docs</a>.":
        "Интерфейс не собран: выполните <code>npm run build</code> в каталоге <code>web/</code>. API доступно на <a "
        "href='/api/docs'>/api/docs</a>.",
    # ------------------------------------------------------------------ языковой сервер
    "Language server (LSP) over stdio: validation and hints in VS Code and other editors.":
        "Языковой сервер (LSP) через stdio: проверка и подсказки в VS Code и других редакторах.",
    "The language server needs the pygls package: pip install \"mapcan[lsp]\"":
        "Языковому серверу нужен пакет pygls: pip install \"mapcan[lsp]\"",
    "bits {msb}…{lsb} (BE)": "биты {msb}…{lsb} (BE)",
    "bits {lo}–{hi}": "биты {lo}–{hi}",
    "unit: {unit}": "единица: {unit}",
    "range: {lo} … {hi}": "диапазон: {lo} … {hi}",
    "cycle {ms} ms": "цикл {ms} мс",
    "Value": "Значение",
    "Name": "Имя",
    "Bit": "Бит",
    "Flag": "Флаг",
    "Byte": "Байт",
    "Export canceled: the map has errors ({errors}). Fix them and try again.":
        "Экспорт отменён: в карте есть ошибки ({errors}). Исправьте их и повторите.",
    "Save the map to a file before exporting.": "Сохраните карту в файл перед экспортом.",
    "Export failed: {error}": "Ошибка экспорта: {error}",
    "Change to {value}": "Заменить на {value}",
    "Change to {value!r}": "Заменить на {value!r}",
    "Add extended: true": "Добавить extended: true",
    "Remove destination": "Удалить destination",
    "Rename to {value!r}": "Переименовать в {value!r}",
    "Move to free bits: {bits}": "Переместить на свободные биты: {bits}",
    "Insert a space after '-'": "Вставить пробел после «-»",
    "Change type to {value}": "Заменить тип на {value}",
    "The map cannot be read: fix the errors to see the document.":
        "Карта не разобрана: исправьте ошибки, чтобы увидеть документ.",
    "The map cannot be read: fix the errors to compare versions.":
        "Карта не разобрана: исправьте ошибки, чтобы сравнить версии.",
    "A version of the map from the history cannot be read.": "Версия карты из истории не разобрана.",
    "The revision history is written on one line and cannot be extended.":
        "Историю изменений, записанную в одну строку, нельзя дополнить.",
    "The document is not a mapcan map.": "Документ не является картой mapcan.",
    "the YAML has a syntax error": "в YAML синтаксическая ошибка",
    "Version {version}": "Версия {version}",
    "enter a version": "укажите версию",
}
