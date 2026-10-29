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
    "Exit code 1 on breaking changes (breaking) or on any change (any).":
        "Код возврата 1 при несовместимых изменениях (breaking) или при любых (any).",
    "breaking changes: {count}": "несовместимых изменений: {count}",
    "changes: {count}": "изменений: {count}",
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
    "Access token on a network address; a random one is generated if not given.":
        "Токен доступа на сетевом адресе; если не задан, создаётся случайный.",
    "No token on a network address (behind a proxy that authenticates users).":
        "Без токена на сетевом адресе (за прокси, который сам проверяет пользователей).",
    "mapcan: open the address with the token that `mapcan serve` printed (…/?token=…)":
        "mapcan: откройте адрес с токеном, который вывел `mapcan serve` (…/?token=…)",
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
    "Type of physical values: float (double only for fields longer than 24 bits), double, or int (integers in "
    "units of the factor's decimals, for MCUs without an FPU).":
        "Тип физических значений: float (double только для полей длиннее 24 бит), double или int (целые в "
        "единицах десятичных знаков множителя — для MCU без FPU).",
    "expected one of: {values}": "ожидается одно из: {values}",
    "Code of one device instead of the buses: its frames, TX schedule, RX filters and dispatch (repeatable).":
        "Код одного устройства вместо шин: его кадры, расписание передачи, фильтры приёма и разбор (можно "
        "повторять).",
    "Code of every device instead of the buses.": "Код каждого устройства вместо шин.",
    "c: the driver-independent code; zephyr: also an adapter to the Zephyr RTOS CAN API (struct can_frame, "
    "filters, TX schedule).":
        "c — код, не зависящий от драйвера; zephyr — ещё и адаптер к CAN API Zephyr RTOS (struct can_frame, "
        "фильтры, расписание передачи).",
    "Module of one device instead of the buses, for a test bench standing in for it (repeatable).":
        "Модуль одного устройства вместо шин — для стенда, который его заменяет (можно повторять).",
    "Module of every device instead of the buses.": "Модуль каждого устройства вместо шин.",
    "no frames are sent or received by: {names}": "нет кадров, которые передаёт или принимает: {names}",
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
    "Duplicate bus name in the map": "Повтор имени шины в карте",
    "Duplicate device name on the bus": "Повтор имени устройства на шине",
    "Duplicate node_id on the bus": "Повтор node_id на шине",
    "CANopen node_id outside 1..127": "node_id CANopen вне диапазона 1..127",
    "Duplicate frame name on the bus": "Повтор имени кадра на шине",
    "Cannot determine the frame's CAN ID": "Невозможно определить CAN ID кадра",
    "Duplicate CAN ID on the bus": "Повтор CAN ID на шине",
    "CAN ID does not fit in 11 bits (needs extended: true)": "CAN ID не помещается в 11 бит (нужно extended: true)",
    "Duplicate signal/flag name in the frame": "Повтор имени сигнала/флага в кадре",
    "Overlapping signals (multiplexing-aware)": "Пересечение сигналов по битам (с учётом мультиплексирования)",
    "Enum value does not fit in the field width": "Значение enum не помещается в разрядность поля",
    "Same name for different enum values": "Одинаковое имя у разных значений enum",
    "Field does not apply to the signal encoding": "Поле не применимо к кодированию сигнала",
    "Flag extends beyond the bit field": "Флаг выходит за пределы битового поля",
    "Flags overlap inside the bit field": "Пересечение флагов внутри битового поля",
    "Zero factor": "Нулевой масштаб",
    "min/max outside the range the field can represent": "min/max вне диапазона, представимого полем",
    "min is greater than max": "min больше max",
    "Multiplexed signal in a frame without a selector": "Мультиплексированный сигнал в кадре без селектора",
    "More than one selector in the frame": "Больше одного селектора в кадре",
    "mux value does not fit in the selector": "Значение mux не помещается в селектор",
    "mux value is not in the selector's value table": "Значения mux нет в таблице значений селектора",
    "Selector is itself multiplexed": "Селектор сам мультиплексирован",
    "cycle_ms is set together with trigger: on_request": "cycle_ms задан вместе с trigger: on_request",
    "Document version or date repeats the latest revision history entry":
        "Версия или дата документа повторяют последнюю запись истории изменений",
    "the version is that of the latest revision history entry: remove document.version":
        "версия совпадает с последней записью истории изменений: уберите document.version",
    "the date is that of the latest revision history entry: remove document.date":
        "дата совпадает с последней записью истории изменений: уберите document.date",
    "document date is {date}, but the latest revision history entry is of {latest}":
        "дата документа {date}, а последняя запись истории изменений — от {latest}",
    "Map version: MAJOR.MINOR or MAJOR.MINOR.PATCH, numbers only (1.4.0). With a revision history it is the "
    "version of its latest entry and is not written. A device can send it in a frame (signal source map_version.*).":
        "Версия карты: MAJOR.MINOR или MAJOR.MINOR.PATCH, только числа (1.4.0). При истории изменений — версия её "
        "последней записи, её не пишут. Устройство может передавать её в кадре (источник сигнала map_version.*).",
    "Release date. With a revision history it is the date of its latest entry and is not written.":
        "Дата выпуска. При истории изменений — дата её последней записи, её не пишут.",
    "Remove the document's version and date repeated from the revision history (mapcan migrate)":
        "Убрать версию и дату документа, повторяющие историю изменений (mapcan migrate)",
    "Minimum interval between transmissions longer than the period":
        "Минимальный интервал между передачами больше периода",
    "Minimum interval between transmissions on a frame sent only cyclically":
        "Минимальный интервал между передачами у кадра, передаваемого только циклически",
    "minimum interval {inhibit} ms is longer than the period {cycle} ms: the frame cannot be sent every period":
        "минимальный интервал {inhibit} мс больше периода {cycle} мс: кадр не сможет передаваться каждый период",
    "the frame is sent only every {cycle} ms: a minimum interval changes nothing":
        "кадр передаётся только раз в {cycle} мс: минимальный интервал ничего не меняет",
    "Minimum time between two transmissions in milliseconds (inhibit time): the frame is not sent again sooner. "
    "May be fractional, e.g. 0.5 (CANopen counts it in 0.1 ms). In DBC: GenMsgDelayTime; in EDS: the PDO's "
    "inhibit time; in C: …_INHIBIT_US.":
        "Минимальное время между двумя передачами в миллисекундах (inhibit time): раньше кадр повторно не "
        "передаётся. Может быть дробным, напр. 0.5 (в CANopen — в единицах 0,1 мс). В DBC — GenMsgDelayTime, "
        "в EDS — inhibit time PDO, в C — …_INHIBIT_US.",
    "min. interval {ms} ms": "мин. интервал {ms} мс",
    "{path}: DBC stores the minimum interval (GenMsgDelayTime) in whole milliseconds; rounded up: {names}":
        "{path}: DBC хранит минимальный интервал (GenMsgDelayTime) в целых миллисекундах; округлено вверх: {names}",
    "Direction conflicts with the CANopen frame type": "Направление противоречит типу кадра CANopen",
    "direction is set: it follows from the CANopen function and the sender":
        "задано direction: оно следует из функции CANopen и отправителя",
    "direction of frame {name!r} means nothing on a frame of the bus: remove it":
        "direction кадра {name!r} ничего не значит у кадра шины: удалите его",
    "direction of frame {name!r} follows from the CANopen function and the sender: remove it (mapcan migrate does)":
        "direction кадра {name!r} следует из функции CANopen и отправителя: удалите его (это делает mapcan migrate)",
    "frame {name!r} comes from outside the map: describe it in the frames of bus {bus!r} with {device!r} in receivers "
    "(mapcan migrate moves it)":
        "кадр {name!r} приходит извне карты: опишите его в кадрах шины {bus!r}, указав {device!r} в receivers "
        "(mapcan migrate переносит его)",
    "direction of frame {name!r} contradicts its CANopen function or sender: remove it, and set sender to the device "
    "that sends the frame":
        "direction кадра {name!r} противоречит его функции CANopen или отправителю: удалите его и укажите в sender "
        "устройство, которое передаёт кадр",
    "CANopen frame type on a non-CANopen bus": "Тип кадра CANopen на шине не CANopen",
    "Big-endian signal on a CANopen or J1939 bus (they carry little-endian data)":
        "Сигнал big-endian на шине CANopen или J1939 (они передают данные little-endian)",
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
    "A floating-point signal must be 32 or 64 bits": "Сигнал с плавающей точкой должен быть 32 или 64 бита",
    "Default value outside the signal's range": "Значение по умолчанию вне диапазона сигнала",
    "Logo file not found": "Файл логотипа не найден",
    "Unsupported logo format": "Неподдерживаемый формат логотипа",
    "Signal has no description": "Нет описания сигнала",
    "Bus or device has no full name": "Нет полного названия шины или устройства",
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
    "bus {name!r} is already defined": "шина {name!r} уже описана",
    "device {name!r} is already defined": "устройство {name!r} уже описано",
    "frame {name!r} is already defined on the bus": "кадр {name!r} уже описан на шине",
    "CAN ID {can_id:#05x} of frame {name!r} matches frame {other!r}":
        "CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}",
    "CAN ID {can_id:#x} > 0x7FF": "CAN ID {can_id:#x} > 0x7FF",
    "brs is set on a bus that is not CAN FD and is not used": "brs задан на шине не CAN FD и не используется",
    "brs on a bus without fd: true is not used": "brs у шины без fd: true не используется",
    "brs of a frame on a bus without fd: true is not used": "brs у кадра на шине без fd: true не используется",
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
    "Non-standard bus bit rate": "Нестандартная скорость шины",
    "Estimated bus load above 70%": "Расчётная загрузка шины выше 70 %",
    "Name is a C/Python keyword or a member of the generated class":
        "Имя совпадает с ключевым словом C/Python или членом сгенерированного класса",
    "Names collide in generated code (differ only in case, or clash with a _phys property)":
        "Имена совпадают в сгенерированном коде (различаются только регистром или совпадают со свойством _phys)",
    "Physical quantity without a unit": "Физическая величина без единицы измерения",
    "Frame has no receivers on the bus": "У кадра нет получателей на шине",
    "Duplicate device short label on the bus": "Повтор короткого обозначения устройства на шине",
    "Document version differs from the latest revision history entry":
        "Версия документа не совпадает с последней записью истории",
    "document version is {version!r}, but the latest revision history entry is {latest!r}":
        "версия документа {version!r}, а последняя запись истории — {latest!r}",
    "Map version is not MAJOR.MINOR or MAJOR.MINOR.PATCH":
        "Версия карты не в виде MAJOR.MINOR или MAJOR.MINOR.PATCH",
    "map version {version!r} is not MAJOR.MINOR or MAJOR.MINOR.PATCH (e.g. 1.4.0)":
        "версия карты {version!r} не в виде MAJOR.MINOR или MAJOR.MINOR.PATCH (напр. 1.4.0)",
    "A signal's source value cannot be sent: the map version is not numeric, the value does not fit, or initial is "
    "set too":
        "Значение source сигнала нельзя передать: версия карты не числовая, значение не помещается или задан ещё и "
        "initial",
    "{name!r} takes its value from {source}: remove initial":
        "{name!r} получает значение из {source}: уберите initial",
    "{name!r} sends {source}, but the map version {version!r} is not MAJOR.MINOR[.PATCH]":
        "{name!r} передаёт {source}, но версия карты {version!r} не в виде MAJOR.MINOR[.PATCH]",
    "{source} = {value} does not fit in {bits} bits ({lo}..{hi})":
        "{source} = {value} не помещается в {bits} бит ({lo}..{hi})",
    "bit rate {bitrate} bit/s is not a standard value (125000, 250000, 500000, 1000000…)":
        "скорость {bitrate} бит/с не входит в стандартный ряд (125000, 250000, 500000, 1000000…)",
    "short label {short!r} is already used by device {other!r}": "обозначение {short!r} уже у устройства {other!r}",
    "frame {name!r} differs from {other!r} only in case: their C macros will collide":
        "кадр {name!r} отличается от {other!r} только регистром: в C-коде их макросы совпадут",
    "Set the bitrate of the bus to estimate its load.": "Задайте скорость шины (bitrate), чтобы оценить её загрузку.",
    "Set data_bitrate to estimate the load: frames with bit rate switching send their data at it.":
        "Задайте data_bitrate, чтобы оценить загрузку: кадры с переключением скорости передают данные на ней.",
    "Bus load unknown: no frame has a cycle or a minimum interval.":
        "Загрузка неизвестна: ни у одного кадра нет периода или минимального интервала.",
    "Estimated bus load: {load}": "Расчётная загрузка шины: {load}",
    "At least: {counted} of {total} frames are counted; frames without a cycle or a minimum interval are not.":
        "Не меньше: учтено кадров {counted} из {total}; кадры без периода и минимального интервала не учитываются.",
    "Frames sent on an event are counted at their minimum interval, with worst-case bit stuffing.":
        "Кадры по событию учитываются с минимальным интервалом, bit stuffing — по худшему случаю.",
    "estimated load of bus {bus!r} is {load:.0f}% (frames counted: {count}, {bitrate} bit/s; event frames at their "
    "minimum interval); keep it at or below {limit}%":
        "расчётная загрузка шины {bus!r} — {load:.0f} % (учтено кадров: {count}, {bitrate} бит/с; кадры по событию — "
        "с их минимальным интервалом), рекомендуется не больше {limit} %",
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
    "selector {name!r} cannot have mux": "селектор {name!r} не может иметь mux",
    "{key} does not apply to encoding: {encoding}": "{key} не применяется при encoding: {encoding}",
    "signal {name!r}: float must be 32 or 64 bits, got {bits}":
        "сигнал {name!r}: float — 32 или 64 бита, задано {bits}",
    "signal {name!r} has no description": "сигнал {name!r} без описания",
    "bus {name!r} has no name (title)": "у шины {name!r} нет названия (title)",
    "device {name!r} has no full name (title)": "у устройства {name!r} нет полного названия (title)",
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
    "the source address of a frame from outside the map is unknown: give id":
        "адрес источника кадра извне карты неизвестен: задайте id",
    "the source address of an RX frame is unknown: set sender to the sending device or give id":
        "адрес источника RX-кадра неизвестен: укажите в sender передающее устройство или задайте id",
    "the sender has no address": "у отправителя нет address",
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
    "mapcan — CAN signal map (format v2)": "mapcan — карта сигналов CAN (формат v2)",
    "Frames whose sender is outside the map, with the receiving devices in receivers; also CANopen broadcast frames "
    "(NMT, SYNC, TIME).":
        "Кадры, отправитель которых вне карты, с принимающими устройствами в receivers; а также широковещательные "
        "кадры CANopen (NMT, SYNC, TIME).",
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
    "Default document language: ISO 639-1 code (ru, en, de…).":
        "Язык документов по умолчанию: код ISO 639-1 (ru, en, de…).",
    "a translation key must be an ISO 639-1 language code (de, fr…)":
        "ключ перевода должен быть кодом языка ISO 639-1 (de, fr…)",
    "The same SPN on several signals of the bus": "Один и тот же SPN у нескольких сигналов шины",
    "CANopen dictionary object on a non-PDO signal, outside 0x2000..0x9FFF or big-endian":
        "Объект словаря CANopen у сигнала не PDO, вне 0x2000..0x9FFF или big-endian",
    "The same dictionary object on several signals of a device": "Один объект словаря у нескольких сигналов устройства",
    "{name!r}: a dictionary object is set only on PDO signals of a device on a CANopen bus":
        "{name!r}: объект словаря задаётся только у сигналов PDO устройства на шине CANopen",
    "{name!r}: subindex without index": "{name!r}: subindex без index",
    "{name!r}: index {index:#06x} is outside the manufacturer and profile areas (0x2000..0x9FFF)":
        "{name!r}: индекс {index:#06x} вне областей производителя и профилей (0x2000..0x9FFF)",
    "{name!r}: {protocol} carries little-endian data": "{name!r}: {protocol} передаёт данные little-endian",
    "object {index:04X}:{sub:02X} is already mapped by {other}": "объект {index:04X}:{sub:02X} уже у сигнала {other}",
    "A signal at subindex 0 of an array or a record: subindex 0 holds the number of its entries":
        "Сигнал на субиндексе 0 массива или записи: субиндекс 0 хранит число их элементов",
    "{name!r}: subindex 0 of object {index:04X} holds the number of its entries (an array or a record): give the "
    "signal a subindex from 1":
        "{name!r}: субиндекс 0 объекта {index:04X} хранит число его элементов (массив или запись): задайте сигналу "
        "субиндекс от 1",
    "CANopen: index of the dictionary object mapped into the PDO.":
        "CANopen: индекс объекта словаря, отображённого в PDO.",
    "CANopen: subindex of the dictionary object (0 by default).":
        "CANopen: субиндекс объекта словаря (по умолчанию 0).",
    "Signal longer than 64 bits that is not aligned bytes": "Сигнал длиннее 64 бит, но не выровненные байты",
    "signal {name!r} is {bits} bits long: only bytes (encoding: bytes, little-endian, starting at a byte boundary) "
    "can be longer than 64 bits":
        "сигнал {name!r} длиной {bits} бит: длиннее 64 бит могут быть только байты (encoding: bytes, little-endian, с "
        "границы байта)",
    "A PGN longer than 8 bytes is sent with the J1939-21 transport protocol":
        "PGN длиннее 8 байт передаётся транспортным протоколом J1939-21",
    "spn on a signal of a {protocol} bus": "spn у сигнала на шине {protocol}",
    "SPN {spn} is already used by signal {other}": "SPN {spn} уже у сигнала {other}",
    "J1939: suspect parameter number (SPN) per SAE J1939-71.": "J1939: номер параметра (SPN) по SAE J1939-71.",
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
    "EDS or DCF of a CANopen device → YAML map: its PDOs, the dictionary objects mapped into them, the heartbeat.":
        "EDS или DCF устройства CANopen → YAML-карта: его PDO, отображённые в них объекты словаря, heartbeat.",
    "EDS or DCF file.": "Файл EDS или DCF.",
    "node ID {value} is not 1..127": "node ID {value} вне 1..127",
    "Node ID of the device (1..127); a DCF gives its own, an EDS none (1 is used then).":
        "Node ID устройства (1..127); в DCF он свой, в EDS его нет (тогда берётся 1).",
    "Document title; the product name by default.": "Название документа; по умолчанию название изделия.",
    "{where}: object 0x{index:04X}:{sub:02X} is not described in the file: imported as an unsigned number":
        "{where}: объект 0x{index:04X}:{sub:02X} не описан в файле: перенесён как беззнаковое число",
    "{where}: UNICODE_STRING object 0x{index:04X}:{sub:02X} is imported as a byte array":
        "{where}: объект UNICODE_STRING 0x{index:04X}:{sub:02X} перенесён как массив байтов",
    "{where}: data type 0x{type:04X} of object 0x{index:04X}:{sub:02X} is not a standard one: imported as an "
    "unsigned number":
        "{where}: тип данных 0x{type:04X} объекта 0x{index:04X}:{sub:02X} не стандартный: перенесён как беззнаковое "
        "число",
    "{frame}: the map has the first four PDOs of each direction, this one is not imported":
        "{frame}: в карте есть только первые четыре PDO каждого направления, этот не перенесён",
    "{frame}: the PDO is disabled in the file (bit 31 of its COB-ID), imported as enabled":
        "{frame}: PDO выключен в файле (бит 31 COB-ID), перенесён как включённый",
    "{frame}: the mapped objects take {bits} bits, more than the 64 of a CAN frame":
        "{frame}: отображённые объекты занимают {bits} бит, больше 64 бит кадра CAN",
    "{frame}: {count} dummy entries of the mapping are left as free bits":
        "{frame}: на месте фиктивных записей отображения ({count}) оставлены свободные биты",
    "{frame}: synchronous transmission (type {type}) is not in the format: imported without it":
        "{frame}: синхронной передачи (тип {type}) в формате нет: перенесено без неё",
    "the file gives no node ID: {node_id} is used (--node-id sets another)":
        "в файле нет node ID: взят {node_id} (другой задаёт --node-id)",
    "{count} dictionary objects are mapped into no PDO and are not imported: {objects}":
        "объекты словаря, не отображённые ни в один PDO, не перенесены ({count}): {objects}",
    "No value table with this name in value_tables": "Таблица значений с таким именем не описана в value_tables",
    "include: the map has no path to resolve included files from":
        "include: у карты нет пути, подключать файлы не от чего",
    "include: file {name!r} not found": "include: файл {name!r} не найден",
    "an included file must be a YAML mapping": "подключаемый файл должен быть словарём YAML",
    "key {key!r} cannot be included: only buses and value_tables":
        "ключ {key!r} нельзя подключать: допустимы buses и value_tables",
    "value_tables must be a mapping of tables": "value_tables должен быть словарём таблиц",
    "buses must be a list of buses": "buses должен быть списком шин",
    "a bus must be a mapping with its name": "шина должна быть словарём с её именем",
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
    "Name for people, e.g. \"States\": the label in the map tree and the heading in documents.":
        "Название для людей, напр. «Состояния»: подпись в дереве карты и заголовок в документах.",
    "What it is and what for: shown in documents, comments of generated code and DBC.":
        "Что это и зачем: выводится в документах, комментариях сгенерированного кода и DBC.",
    "A note or caveat: \"Note:\" in documents, after the description in DBC.":
        "Примечание или оговорка: в документах — «Примечание:», в DBC — после описания.",
    "Device abbreviation, e.g. \"BMS\": in document tables and before the name in the tree.":
        "Сокращение устройства, напр. «BMS»: в таблицах документов и в дереве перед названием.",
    "Transmission on an event (event; with cycle_ms also every period) or on request (on_request).":
        "Передача по событию (event; вместе с cycle_ms — ещё и каждый период) или по запросу (on_request).",
    "GitHub username of the change's author.": "Имя пользователя GitHub автора изменения.",
    "Codes of the rules to disable.": "Коды правил, которые нужно отключить.",
    "Value encoding: number or enum.": "Кодирование значения: number или enum.",
    "First byte of the signal.": "Первый байт сигнала.",
    "Bit offset within the byte.": "Смещение бита в байте.",
    "Developed by (Разраб.)": "Разраб.",
    "Checked by (Пров.)": "Пров.",
    "Technical control (Т. контр.)": "Т. контр.",
    "Standards control (Н. контр.)": "Н. контр.",
    "Approved by (Утв.)": "Утв.",
    "File format version: 2. A map of version 1 is still read; mapcan migrate rewrites it.":
        "Версия формата файла: 2. Карта версии 1 по-прежнему читается; mapcan migrate переписывает её.",
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
    "Enter the name of the file": "Введите имя файла",
    "the name of an included file must end with .yaml or .yml":
        "имя включаемого файла должно оканчиваться на .yaml или .yml",
    "the path of an included file is relative to the map": "путь включаемого файла указывается относительно карты",
    "include of the map is not a list": "include карты — не список",
    "Save the map to a file first.": "Сначала сохраните карту в файл.",
    "{fmt} export error: {error}": "ошибка экспорта {fmt}: {error}",
    "the file is not UTF-8 encoded": "файл не в UTF-8",
    "could not read {name}: {error}": "не удалось прочитать {name}: {error}",
    "internal error of mapcan: {error}": "внутренняя ошибка mapcan: {error}",
    "could not import {name}: {error}": "не удалось импортировать {name}: {error}",
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
    "This needs the optional part “{extra}” of mapcan: pip install \"mapcan[{extra}]\" (or \"mapcan[all]\")":
        "Для этого нужна дополнительная часть mapcan «{extra}»: pip install \"mapcan[{extra}]\" "
        "(или \"mapcan[all]\")",
    "bits {msb}…{lsb} (BE)": "биты {msb}…{lsb} (BE)",
    "bits {lo}–{hi}": "биты {lo}–{hi}",
    "unit: {unit}": "единица: {unit}",
    "range: {lo} … {hi}": "диапазон: {lo} … {hi}",
    "cycle {ms} ms": "цикл {ms} мс",
    "cycle {ms} ms and on event": "цикл {ms} мс и по событию",
    "length {n}": "длина {n}",
    "Value": "Значение",
    "Name": "Имя",
    "Bit": "Бит",
    "Flag": "Флаг",
    "Byte": "Байт",
    "Signal": "Сигнал",
    "Position": "Положение",
    "Size": "Размер",
    "bit": "бит",
    "Export canceled: the map has errors ({errors}). Fix them and try again.":
        "Экспорт отменён: в карте есть ошибки ({errors}). Исправьте их и повторите.",
    "Save the map to a file before exporting.": "Сохраните карту в файл перед экспортом.",
    "No free bits left in the frame. Free up space or increase the frame length":
        "В кадре нет свободных бит: освободите место или увеличьте длину кадра",
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
    # ------------------------------------------------------------------ format fields (model descriptions)
    "Signal length in bytes, instead of bit_length.": "Длина сигнала в байтах, вместо bit_length.",
    "Flag identifier: Latin letters, digits and _. Used in generated code and DBC. Required, unique within the frame.":
        "Идентификатор флага: латинские буквы, цифры и _. Используется в сгенерированном коде и DBC. Обязателен, "
        "уникален в кадре.",
    "SDO exchange identifier: Latin letters, digits and _. Used in generated code. Required.":
        "Идентификатор SDO-обмена: латинские буквы, цифры и _. Используется в сгенерированном коде. Обязателен.",
    "Flag offset from the least significant bit of the bit field: 0 is the field's LSB.":
        "Смещение флага от младшего бита битового поля: 0 — младший бит поля.",
    "Flag width in bits, 1 by default. A width above 1 makes a multi-bit value inside the field.":
        "Ширина флага в битах, по умолчанию 1. Больше 1 — многобитовое значение внутри поля.",
    "Signal identifier: Latin letters, digits and _. Used in generated code and DBC. Required, unique within the "
    "frame.":
        "Идентификатор сигнала: латинские буквы, цифры и _. Используется в сгенерированном коде и DBC. Обязателен, "
        "уникален в кадре.",
    "Human-readable signal name, e.g. “Battery voltage”: its label in the map tree. Optional; without it, the tree "
    "shows the identifier.":
        "Название сигнала для людей, напр. «Напряжение батареи»: подпись в дереве карты. Необязательно — без него в "
        "дереве выводится идентификатор.",
    "Position of the signal's least significant bit (LSB) in the frame, counting from 0. Bit N is in byte N div 8 at "
    "position N mod 8.":
        "Номер младшего бита (LSB) сигнала в кадре, от 0. Бит N находится в байте N div 8 на позиции N mod 8.",
    "Signal width in bits: 1..64; longer only for encoding: bytes.":
        "Длина сигнала в битах: 1..64; длиннее — только у encoding: bytes.",
    "Byte order of a multi-byte signal. little-endian (Intel): least significant byte first, typical for CANopen and "
    "J1939. big-endian (Motorola): most significant byte first.":
        "Порядок байт многобайтового сигнала. little-endian (Intel) — младший байт первым, обычно для CANopen и "
        "J1939. big-endian (Motorola) — старший байт первым.",
    "Multiplier: physical value = raw × factor + offset. E.g. 0.1 for voltage in 0.1 V steps.":
        "Множитель: физическое значение = raw × масштаб + смещение. Напр. 0.1 для напряжения с шагом 0,1 В.",
    "Offset: physical value = raw × factor + offset. E.g. −40 for temperature.":
        "Смещение: физическое значение = raw × масштаб + смещение. Напр. −40 для температуры.",
    "Unit of the physical quantity: a standard unit or your own text. Standard units appear in documents in the "
    "document language (V ↔ В).":
        "Единица физической величины: стандартная или свой текст. Стандартные единицы выводятся в документах на языке "
        "документа (V ↔ В).",
    "Allowed minimum in physical units. Leave empty to use the limit of the signal width.":
        "Допустимый минимум в физических единицах. Пусто — по разрядности сигнала.",
    "Allowed maximum in physical units. Leave empty to use the limit of the signal width.":
        "Допустимый максимум в физических единицах. Пусто — по разрядности сигнала.",
    "How enum table values are shown in documents: decimal or hex.":
        "Как показывать значения таблицы enum в документах: десятичными или hex.",
    "Multiplexer selector signal. Multiplexing lets one frame carry different sets of signals: the selector value "
    "tells which signals the frame currently contains. A frame can have only one selector.":
        "Сигнал-селектор мультиплексора. Мультиплексирование позволяет передавать разные наборы сигналов в одном "
        "кадре: значение селектора показывает, какие сигналы сейчас в кадре. В кадре может быть только один селектор.",
    "Multiplexer selector: the value of this field tells which signals the frame currently contains, as the "
    "multiplexer of a signal does. A frame can have only one selector.":
        "Селектор мультиплексора: значение этого поля показывает, какие сигналы сейчас в кадре, как у сигнала-"
        "селектора. В кадре может быть только один селектор.",
    "Selector values for which this signal is in the frame, e.g. 0 or 1, 2. Leave empty if the signal is always "
    "present. Requires a selector signal in the frame.":
        "Значения селектора, при которых этот сигнал есть в кадре, напр. 0 или 1, 2. Пусто — сигнал присутствует "
        "всегда. Требует сигнал-селектор в кадре.",
    "Value after power-up or before the first message is received, in physical units. In C: …_INITIAL_RAW; in DBC: "
    "GenSigStartValue.":
        "Значение после включения или до первого приёма, в физических единицах. В C — …_INITIAL_RAW, в DBC — "
        "GenSigStartValue.",
    "The signal always carries a value taken from the map: map_version.major, .minor or .patch (document.version) "
    "or layout_crc32 (the fingerprint of the frame layouts). The value is written to code as the signal's initial "
    "value, so a device sends the map it was built from.":
        "Сигнал всегда несёт значение из карты: map_version.major, .minor или .patch (document.version) или "
        "layout_crc32 (отпечаток раскладки кадров). Значение попадает в код как начальное значение сигнала, так что "
        "устройство передаёт карту, по которой оно собрано.",
    "SDO command byte (CCS/SCS), e.g. 0x2B — write 2 bytes, 0x23 — write 4 bytes, 0x40 — read.":
        "Байт команды SDO (CCS/SCS), напр. 0x2B — запись 2 байт, 0x23 — запись 4 байт, 0x40 — чтение.",
    "CANopen object dictionary index, 0x0000..0xFFFF.": "Индекс объекта словаря CANopen, 0x0000..0xFFFF.",
    "Object dictionary subindex, 0x00..0xFF.": "Субиндекс объекта словаря, 0x00..0xFF.",
    "Frame identifier: Latin letters, digits and _. Used in generated code and DBC. Required, unique on the bus.":
        "Идентификатор кадра: латинские буквы, цифры и _. Используется в сгенерированном коде и DBC. Обязателен, "
        "уникален на шине.",
    "Human-readable frame name, e.g. “Status”: the frame heading in documents and its label in the map tree. "
    "Optional; without it, the tree shows the identifier.":
        "Название кадра для людей, напр. «Состояния»: заголовок кадра в документах и подпись в дереве карты. "
        "Необязательно — без него в дереве выводится идентификатор.",
    "Frame CAN ID: 11-bit (0x000..0x7FF) or 29-bit (up to 0x1FFFFFFF). Leave empty to compute it: for CANopen from "
    "the type and node_id, for J1939 from the PGN, priority and address.":
        "CAN ID кадра: 11 бит (0x000..0x7FF) или 29 бит (до 0x1FFFFFFF). Пусто — вычисляется: CANopen — из типа и "
        "node_id, J1939 — из PGN, приоритета и адреса.",
    "Use a 29-bit (extended) identifier instead of an 11-bit one.":
        "29-битный (расширенный) идентификатор вместо 11-битного.",
    "Bit rate switch (BRS) of a CAN FD frame: the data field is sent at the data phase bit rate. Empty: as set on the "
    "bus. Written to DBC (the CANFD_BRS attribute).":
        "Переключение скорости (BRS) кадра CAN FD: поле данных передаётся на скорости фазы данных. Пусто — как у "
        "шины. Попадает в DBC (атрибут CANFD_BRS).",
    "J1939 parameter group number, 0..0x3FFFF. PF < 240 (0xF0) means PDU1, a destination-specific frame: the low byte "
    "of the PGN must be 0 and the destination is set separately. PF ≥ 240 means PDU2, broadcast.":
        "Номер группы параметров J1939, 0..0x3FFFF. PF < 240 (0xF0) — PDU1, адресный кадр: младший байт PGN должен "
        "быть 0, получатель задаётся отдельно. PF ≥ 240 — PDU2, широковещательный.",
    "J1939 priority 0..7: the top 3 bits of the ID. Lower values mean higher priority. Default 6.":
        "Приоритет J1939 0..7: старшие 3 бита ID. Меньше — важнее. По умолчанию 6.",
    "Destination address for a J1939 PDU1 frame, 0..255. 0xFF means all nodes.":
        "Адрес получателя для PDU1-кадра J1939, 0..255. 0xFF — всем узлам.",
    "Devices on this bus that receive the frame. The owner of an RX frame is a receiver even without this list. Used "
    "in documents, DBC and each device's \"Receives\" summary.":
        "Устройства этой шины, которые принимают кадр. Владелец RX-кадра — получатель и без этого списка. Попадают в "
        "документы, DBC и сводку «Принимает» у устройств.",
    "Device on this bus that sends the frame when it is not the frame's owner, which then receives it (e.g. a "
    "node's RPDO sent by the master). Empty: a frame of a device is sent by the device (a CANopen RX function: from "
    "outside the map), a frame of the bus from outside the map. A frame sent by one of your devices is best "
    "described at the sender, with the receiving devices listed in \"Receivers\".":
        "Устройство этой шины, которое передаёт кадр, если это не его владелец; владелец тогда его принимает "
        "(напр. PDO RX узла, который шлёт мастер). Пусто: кадр устройства передаёт само устройство (функция приёма "
        "CANopen — извне карты), кадр шины — извне карты. Кадр, который передаёт своё устройство, лучше описывать "
        "у отправителя, а принимающих указать в «Получатели».",
    "Deprecated: the direction follows from the CANopen function and the sender, remove it. A frame from outside the "
    "map goes to the frames of the bus, with the receiving devices in receivers (mapcan migrate moves it).":
        "Устарело: направление следует из функции CANopen и отправителя, удалите его. Кадр извне карты описывается "
        "в кадрах шины, с принимающими устройствами в receivers (mapcan migrate переносит его).",
    "Cyclic transmission period in milliseconds. With trigger: event the frame is also sent at once on an event.":
        "Период циклической передачи в миллисекундах. С trigger: event кадр передаётся ещё и сразу по событию.",
    "Device identifier: Latin letters, digits and _. Used in generated code, DBC, and frame senders and receivers. "
    "Required.":
        "Идентификатор устройства: латинские буквы, цифры и _. Используется в сгенерированном коде, DBC, в "
        "отправителях и получателях кадров. Обязателен.",
    "Short device abbreviation for tables and headings in documents, e.g. BMS. If set, the map tree shows it before "
    "the full name. If empty, documents use the identifier in uppercase.":
        "Короткое обозначение устройства в таблицах и заголовках документов, напр. BMS. Если задано, в дереве карты "
        "выводится перед полным названием. Пусто — в документах идентификатор прописными буквами.",
    "Full human-readable device name, e.g. “Battery management system”. Shown in the device section heading in "
    "documents and in the map tree. Required.":
        "Полное название устройства для людей, напр. «Система управления батареей». Выводится в заголовке раздела "
        "устройства в документах и в дереве карты. Обязательно.",
    "CANopen node address 1..127 (0x01..0x7F). Added to the base ID of PDO, SDO, EMCY and Heartbeat frames.":
        "Адрес узла CANopen 1..127 (0x01..0x7F). Прибавляется к базовому ID кадров PDO, SDO, EMCY, Heartbeat.",
    "J1939 source address 0..253 (0x00..0xFD). Forms the low byte of every frame ID the device sends; 254 and 255 are "
    "reserved.":
        "Адрес источника J1939 (Source Address) 0..253 (0x00..0xFD). Младший байт ID всех кадров устройства; 254 и "
        "255 — служебные.",
    "Bus identifier: Latin letters, digits and _, no spaces. Used in DBC and C file names and as an anchor in "
    "documents. Required.":
        "Идентификатор шины: латинские буквы, цифры и _, без пробелов. Используется в именах файлов DBC и C и как "
        "якорь в документах. Обязателен.",
    "Human-readable bus name, e.g. “Bus 1” or “Powertrain CAN”. Used as the section heading in documents and as the "
    "bus label in the map tree. Required.":
        "Название шины для людей, напр. «Шина 1» или «CAN силовой части». Заголовок раздела в документах и подпись "
        "шины в дереве карты. Обязательно.",
    "Print details of the title page and the title block (logo, designation, signatures…), read by the PDF "
    "templates.":
        "Реквизиты для печати титульного листа и основной надписи (логотип, обозначение, подписи…): их читают "
        "шаблоны PDF.",
    "Connector or harness of the bus, e.g. “X3, pins 4–5”. Used in documents only. The CAN adapter and channel of a "
    "workstation are not part of the map.":
        "Разъём или жгут шины, напр. «X3, контакты 4–5». Только для документов. CAN-адаптер и канал рабочего места "
        "в карту не входят.",
    "Bus bitrate in bit/s, e.g. 250000 or 500000. Shown in documents and DBC.":
        "Скорость шины в бит/с, напр. 250000 или 500000. Попадает в документы и DBC.",
    "Higher-layer protocol. CANopen: the frame ID is computed from the frame type and node_id; SAE J1939: from PGN, "
    "priority and the device address; CAN: each frame has an explicit ID.":
        "Протокол верхнего уровня. CANopen — ID кадра вычисляется из типа кадра и node_id; SAE J1939 — из PGN, "
        "приоритета и адреса устройства; CAN — ID задаётся явно у каждого кадра.",
    "CAN FD bus: frames up to 64 bytes (DLC 0..8, 12, 16, 20, 24, 32, 48, 64).":
        "Шина CAN FD: кадры до 64 байт (DLC 0..8, 12, 16, 20, 24, 32, 48, 64).",
    "Default bit rate switch (BRS) of CAN FD frames: the data field is sent at the data phase bit rate. Turn it off "
    "if the nodes or the wiring of the bus cannot handle the higher rate. A frame can set its own value.":
        "Переключение скорости (BRS) у кадров CAN FD по умолчанию: поле данных передаётся на скорости фазы данных. "
        "Выключите, если узлы или проводка шины не держат высокую скорость. Кадр может задать своё значение.",
    "Rewrite the former names of fields (deprecated-key) to the current ones, and a map of format version 1 in "
    "version 2 (format-v1), keeping comments and layout. Included files are rewritten too.":
        "Заменить прежние имена полей (deprecated-key) текущими, а карту формата версии 1 переписать в версии 2 "
        "(format-v1), сохраняя комментарии и оформление. Подключённые файлы тоже обновляются.",
    "Map files.": "Файлы карт.",
    "Do not write; exit code 1 if a file has former names.":
        "Не записывать; код возврата 1, если в файле есть прежние имена.",
    "No former field names found.": "Прежних имён полей нет.",
    "{file}: former field names, run mapcan migrate": "{file}: прежние имена полей, выполните mapcan migrate",
    "Write the keys of every node in one order (that of docs/format.md), keeping comments, layout and number "
    "notation. Included files are formatted too.":
        "Записать ключи каждого узла в одном порядке (как в docs/format.md), сохранив комментарии, оформление и "
        "запись чисел. Включаемые файлы тоже форматируются.",
    "Do not write; exit code 1 if a file is not formatted.":
        "Не записывать; код выхода 1, если файл не отформатирован.",
    "{file}: not formatted, run mapcan fmt": "{file}: не отформатирован, выполните mapcan fmt",
    "{file}:{line}: note: signal {name!r}: the editors write its position as {keys}":
        "{file}:{line}: примечание: сигнал {name!r}: редакторы записывают его положение как {keys}",
    "part_of: the map {map!r} is not found": "part_of: карта {map!r} не найдена",
    "part_of: the map {map!r} does not include this file": "part_of: карта {map!r} не включает этот файл",
    "the map {map!r} has {n} error(s) outside this file: open it to see them":
        "в карте {map!r} ошибок вне этого файла: {n}; откройте её, чтобы их увидеть",
    "the included file {file} cannot be read": "подключённый файл {file} не читается",
    "All files are formatted.": "Все файлы отформатированы.",
    "cannot format: {error}": "не удалось отформатировать: {error}",
    "cannot format: the result would read differently; the file is left as it is":
        "не удалось отформатировать: результат читался бы иначе; файл оставлен как есть",
    "{old!r} is deprecated: use {new!r} (mapcan migrate rewrites the file)":
        "{old!r} устарело: используйте {new!r} (mapcan migrate обновит файл)",
    "{old!r} is the former name of {new!r}: remove it, {new!r} is already set":
        "{old!r} — прежнее имя {new!r}: удалите его, {new!r} уже задано",
    "Frame data length in bytes: 0..8, for CAN FD up to 64 (12, 16, 20, 24, 32, 48, 64). Required except for CANopen "
    "service frames (NMT, SYNC, TIME, Heartbeat, SDO), whose length is set by CiA 301. Up to 1785 bytes on a J1939 "
    "bus, with the transport protocol. Formerly dlc: the DLC on the bus is the code of this length.":
        "Длина данных кадра в байтах: 0..8, для CAN FD — до 64 (12, 16, 20, 24, 32, 48, 64). Обязательна, кроме "
        "служебных кадров CANopen (NMT, SYNC, TIME, Heartbeat, SDO): их длину задаёт CiA 301. На шине J1939 — до "
        "1785 байт, с транспортным протоколом. Прежнее имя — dlc: DLC на шине — это код этой длины.",
    "Former name of a field: still read, mapcan migrate rewrites it":
        "Прежнее имя поля: читается, mapcan migrate заменит его",
    "Frame length that no DLC can encode": "Длина кадра, которую не выразить кодом DLC",
    "Frame length is not set": "Не задана длина кадра",
    "Length of a CANopen service frame does not match CiA 301":
        "Длина служебного кадра CANopen не соответствует CiA 301",
    "Signal extends beyond the frame length": "Сигнал выходит за длину кадра",
    "frame {name!r}: length (data length, bytes) is not set": "кадр {name!r}: не задана length (длина данных, байт)",
    "{length}-byte PGN: sent with the J1939-21 transport protocol ({mode})":
        "PGN длиной {length} байт: передаётся транспортным протоколом J1939-21 ({mode})",
    "a {type} frame is {expected} bytes long under CiA 301, but {length} is set":
        "по CiA 301 кадр {type} имеет длину {expected} байт, а задано {length}",
    "signal {name!r} occupies bytes {first}..{last}, but the frame is {length} bytes long":
        "сигнал {name!r} занимает байты {first}..{last}, а длина кадра — {length} байт",
    "length {length} is not a CAN FD frame length (0..8, 12, 16, 20, 24, 32, 48, 64)":
        "длина {length} недопустима для кадра CAN FD (0..8, 12, 16, 20, 24, 32, 48, 64)",
    "length {length} > 8 (for CAN FD set fd: true on the bus)":
        "длина {length} > 8 (для CAN FD задайте fd: true у шины)",
    "Remove direction from the frames of this file (mapcan migrate)":
        "Удалить direction из кадров этого файла (mapcan migrate)",
    "Rename the former fields of the whole map (mapcan migrate)":
        "Переименовать прежние поля во всей карте (mapcan migrate)",
    "How the raw value is read as a number. unsigned — no negative values (default). twos_complement — the usual "
    "signed integer (−1 = all ones). ones_complement — a negative value is its magnitude with all bits inverted (−1 = "
    "1…10). sign_magnitude — the top bit is the sign, the rest the magnitude (−1 = 10…01). float — IEEE 754 floating "
    "point, 32 bits (default) or 64. Generated C and Python code use this representation; DBC stores two's complement "
    "only, so the export warns about ones' complement and sign-magnitude. Formerly signed and signed_code.":
        "Как сырое значение читается как число. unsigned — без отрицательных значений (по умолчанию). twos_complement "
        "— обычное знаковое целое, дополнительный код (−1 = все единицы). ones_complement — обратный код: "
        "отрицательное значение — модуль с инвертированными битами (−1 = 1…10). sign_magnitude — прямой код: старший "
        "бит — знак, остальные — модуль (−1 = 10…01). float — число с плавающей точкой IEEE 754, 32 бита (по "
        "умолчанию) или 64. Сгенерированный код на C и Python использует это представление; DBC хранит только "
        "дополнительный код, поэтому экспорт предупреждает об обратном и прямом коде. Прежде — signed и signed_code.",
    "unsigned or twos_complement (a signed integer). Formerly signed: true.":
        "unsigned или twos_complement (знаковое целое). Прежде — signed: true.",
    "Ones' complement or sign-magnitude signal: DBC stores two's complement only":
        "Сигнал в обратном или прямом коде: DBC хранит только дополнительный код",
    "CANopen function of the frame (CiA 301): nmt, sync, emcy, time, pdo_tx1..4, pdo_rx1..4, sdo_tx, sdo_rx, "
    "heartbeat. Sets the base ID (e.g. PDO TX 1 = 0x180 + node_id), the default direction and the length of service "
    "frames. Empty: not a CANopen service frame, the ID is set explicitly. Only on CANopen buses. Formerly type "
    "(raw: empty).":
        "Функция кадра CANopen (CiA 301): nmt, sync, emcy, time, pdo_tx1..4, pdo_rx1..4, sdo_tx, sdo_rx, heartbeat. "
        "Задаёт базовый ID (например, PDO TX 1 = 0x180 + node_id), направление по умолчанию и длину служебных "
        "кадров. Пусто — не служебный кадр CANopen, ID задаётся явно. Только на шинах CANopen. Прежде — type (raw — "
        "пусто).",
    "Raw values meaning “not available”: the sender has no value (e.g. 0xFF).":
        "Сырые значения «нет данных»: у отправителя нет значения (например, 0xFF).",
    "Raw values meaning “error”: the sender has a fault in this value (e.g. 0xFE).":
        "Сырые значения «ошибка»: у отправителя неисправность в этой величине (например, 0xFE).",
    "Raw values that carry no value: one value, a list, ranges such as \"0xFF00..0xFFFF\", or by meaning: "
    "{not_available: …, error: …}. A plain value or list means “not available”. In C: …_is_not_available() and "
    "…_is_error(). Formerly invalid.":
        "Сырые значения, не несущие величины: одно значение, список, диапазоны вида \"0xFF00..0xFFFF\" или по смыслу: "
        "{not_available: …, error: …}. Просто значение или список означает «нет данных». В C: …_is_not_available() и "
        "…_is_error(). Прежде — invalid.",
    "a raw value is a number or a range \"lo..hi\", e.g. 0xFF00..0xFFFF":
        "сырое значение — число или диапазон \"от..до\", например 0xFF00..0xFFFF",
    "a range of raw values must go from the lower bound to the upper one":
        "диапазон сырых значений записывается от нижней границы к верхней",
    "A raw value without a value (invalid_raw) falls inside the min..max range":
        "Сырое значение без величины (invalid_raw) попадает в диапазон min..max",
    "A raw value of invalid_raw does not fit in the signal width":
        "Значение invalid_raw не помещается в разрядность сигнала",
    "invalid_raw {value} does not fit in {bits} bits ({lo}..{hi})":
        "invalid_raw {value} не помещается в {bits} бит ({lo}..{hi})",
    "invalid_raw {value} maps to {phys}, inside min..max: a receiver cannot tell it from a real value":
        "invalid_raw {value} соответствует {phys} — внутри min..max: получатель не отличит его от настоящего "
        "значения",
    "Schema of a file included by a map (part_of).": "Схема файла, подключаемого картой (part_of).",
    "this file is a part of the map {map!r}: open or validate that map":
        "этот файл — часть карты {map!r}: откройте или проверьте эту карту",
    "an included file starts with mapcan: {version} and part_of: {map} (the map it belongs to)":
        "подключаемый файл начинается с mapcan: {version} и part_of: {map} (карта, к которой он относится)",
    "format version 1: mapcan migrate rewrites the map and its included files in version {v}":
        "формат версии 1: mapcan migrate переписывает карту и подключённые файлы в версии {v}",
    "Map of format version 1: still read, mapcan migrate rewrites it in version 2":
        "Карта формата версии 1: читается, mapcan migrate переписывает её в версии 2",
    "Rewrite this file in format version 2 (mapcan migrate)":
        "Переписать этот файл в формате версии 2 (mapcan migrate)",
    "format version {part} differs from the map's {main}": "версия формата {part} отличается от версии карты {main}",
    "part_of is the path of the map file": "part_of — путь к файлу карты",
    "part_of names {named!r}, but the file is included by {map!r}":
        "part_of указывает {named!r}, а файл подключает {map!r}",
    "File format version: the same as the map's.": "Версия формата файла: та же, что у карты.",
    "The map this file belongs to: the path of its file, relative to this one. The map includes this file in its "
    "include list.":
        "Карта, к которой относится файл: путь к её файлу относительно этого. Карта подключает этот файл в списке "
        "include.",
    "New buses, or buses of the map (by name) that get more devices and frames.":
        "Новые шины или шины карты (по имени), в которые добавляются устройства и кадры.",
    "mapcan — file included by a map (format v2)": "mapcan — файл, подключаемый картой (формат v2)",
    "Included file is missing, has keys that cannot be included or belongs to another map":
        "Подключаемый файл не найден, содержит недопустимые ключи или относится к другой карте",
    "Included file does not start with mapcan and part_of": "Подключаемый файл не начинается с mapcan и part_of",
    "CAN FD: bit rate of the data phase in bit/s, e.g. 2000000. Frames with the bit rate switch (BRS) send their "
    "data field at this rate; it is used in the bus load estimate and shown in documents.":
        "CAN FD: скорость фазы данных в бит/с, например 2000000. Кадры с переключением скорости (BRS) передают поле "
        "данных на этой скорости; она учитывается в оценке загрузки шины и показывается в документах.",
    "Sample point of the (nominal) bit rate, percent of the bit time, e.g. 87.5. All nodes of a bus should use the "
    "same one. Shown in documents.":
        "Точка выборки (номинальной) скорости, процент от длительности бита, например 87.5. У всех узлов шины она "
        "должна быть одинаковой. Показывается в документах.",
    "CAN FD: sample point of the data phase, percent, e.g. 75. Shown in documents.":
        "CAN FD: точка выборки фазы данных, процент, например 75. Показывается в документах.",
    "data_bitrate or data_sample_point on a bus that is not CAN FD":
        "data_bitrate или data_sample_point на шине без CAN FD",
    "CAN FD data phase bit rate lower than the bit rate": "Скорость фазы данных CAN FD ниже номинальной скорости",
    "{key} on a bus without fd: true is not used": "{key} на шине без fd: true не используется",
    "data phase bit rate {data} bit/s is lower than the bit rate {bitrate} bit/s":
        "скорость фазы данных {data} бит/с ниже номинальной скорости {bitrate} бит/с",
    "data phase bit rate {bitrate} bit/s is not a standard value (1000000, 2000000, 5000000, 8000000…)":
        "скорость фазы данных {bitrate} бит/с — нестандартное значение (1000000, 2000000, 5000000, 8000000…)",
    "Receive timeout in milliseconds: when the frame has not arrived for this long, the receivers treat its data as "
    "lost. Usually a few periods, e.g. 3 × cycle_ms. In code: …_TIMEOUT_MS.":
        "Тайм-аут приёма в миллисекундах: если кадр не приходил столько времени, получатели считают его данные "
        "потерянными. Обычно несколько периодов, например 3 × cycle_ms. В коде: …_TIMEOUT_MS.",
    "Receive timeout not longer than the period of a cyclic frame":
        "Тайм-аут приёма не длиннее периода циклического кадра",
    "timeout {timeout} ms is not longer than the period {cycle} ms: the frame would time out between two "
    "transmissions":
        "тайм-аут {timeout} мс не длиннее периода {cycle} мс: кадр будет считаться потерянным между двумя передачами",
    "How the value is interpreted. number — a number: the integer as is, or raw × factor + offset with factor and "
    "offset, or IEEE 754 with representation: float; enum — a value table; bitfield — a set of flags; bytes — a byte "
    "array, or text (VIN, software version) with a charset.":
        "Как трактуется значение. number — число: целое как есть, raw × factor + offset при factor и offset или IEEE "
        "754 при representation: float; enum — таблица значений; bitfield — набор флагов; bytes — массив байт или, с "
        "charset, текст (VIN, версия ПО).",
    "Bytes: the field holds text in this character encoding, ascii, utf-8 or latin-1. Without it the field is a byte "
    "array.":
        "Байты: поле содержит текст в этой кодировке, ascii, utf-8 или latin-1. Без неё поле — массив байт.",
    "Text: the byte that ends a shorter text and fills the rest of the field, e.g. 0x00 or \"*\" (as in J1939 text "
    "parameters). Without it the text fills the field and unused bytes are 0x00.":
        "Текст: байт, которым заканчивается более короткий текст и заполняется остаток поля, например 0x00 или \"*\" "
        "(как в текстовых параметрах J1939). Без него текст занимает поле, а неиспользованные байты — 0x00.",
    "Text not aligned to whole bytes, or a terminator that is not one byte":
        "Текст не выровнен по целым байтам или признак конца — не один байт",
    "text {name!r} must start at a byte boundary and take whole bytes (little-endian)":
        "текст {name!r} должен начинаться с границы байта и занимать целые байты (little-endian)",
    "{key} does not apply to a floating-point number": "{key} не применяется к числу с плавающей точкой",
    "{where}: the value table of a signed or floating-point signal is not imported":
        "{where}: таблица значений знакового сигнала или сигнала с плавающей точкой не импортирована",
    "terminator applies to text: set charset": "terminator применяется к тексту: задайте charset",
    "terminator of {name!r} must be one byte: 0x00..0xFF or one character of the charset":
        "признак конца {name!r} должен быть одним байтом: 0x00..0xFF или одним символом кодировки",
}
