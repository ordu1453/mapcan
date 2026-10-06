// Общие элементы PDF-шаблонов mapcan: битовые диаграммы, таблицы сигналов, адресация.
// Данные карты — JSON из sys.inputs.data (см. mapcan/docmodel.py).
//
// Каждая функция принимает тему оформления `th` — словарь цветов и шрифтов.

#let load-data() = json(bytes(sys.inputs.at("data", default: "{}")))

/// Разрешить перенос длинных идентификаторов по «_».
#let ident(s) = s.replace("_", "_\u{200B}")

#let theme-color = (
  accent: rgb("#1F4E79"),
  head-fill: rgb("#1F4E79"),
  head-text: white,
  line: rgb("#A6A6A6"),
  byte-fill: luma(235),
  mono: ("DejaVu Sans Mono",),
  diagram-text: 7pt,
)

// ГОСТ: чёрные линии, заголовки таблиц без заливки.
#let theme-gost = (
  accent: black,
  head-fill: none,
  head-text: black,
  line: black,
  byte-fill: none,
  mono: ("DejaVu Sans Mono",),
  diagram-text: 7pt,
)

#let mono(s, th: theme-color) = text(font: th.mono, size: 0.9em, s)

/// Логотип предприятия (если задан в карте).
#let logo(doc, height: 15mm, width: auto) = {
  if doc.at("logo", default: "") != "" { image(doc.logo, height: height, width: width, fit: "contain") }
}

#let _head(th, body) = table.cell(fill: th.head-fill, text(fill: th.head-text, weight: "bold", body))

/// Битовая раскладка кадра: строки — байты, колонки — биты 7…0.
#let bit-diagram(fr, L, th: theme-color) = {
  table(
    columns: (13mm,) + (1fr,) * 8,
    align: center + horizon,
    inset: (x: 2pt, y: 4pt),
    stroke: 0.5pt + th.line,
    table.header(_head(th, L.byte), ..range(7, -1, step: -1).map(b => _head(th, str(b)))),
    ..fr.grid.map(row => (
      table.cell(fill: th.byte-fill)[*#row.byte*],
      ..row.segments.map(seg => table.cell(
        colspan: seg.span,
        fill: rgb(seg.color),
        stroke: if seg.conflict { 1.5pt + red } else { 0.5pt + th.line },
      )[#text(size: th.diagram-text, fill: if seg.conflict { red } else { black }, ident(seg.label))]),
    )).flatten(),
  )
}

/// Таблица сигналов кадра.
#let signal-table(fr, L, th: theme-color, comment-color: rgb("#9C5700")) = {
  table(
    columns: (auto, auto, 1.25fr, 1.45fr, 0.95fr, 2.3fr),
    align: (center, center, left, left, left, left),
    stroke: 0.5pt + th.line,
    inset: (x: 4pt, y: 3pt),
    table.header(
      _head(th, L.byte), _head(th, L.bits), _head(th, L.signal),
      _head(th, L.description), _head(th, L.encoding), _head(th, L.values),
    ),
    ..fr.signals.map(s => (
      mono(s.bytes, th: th),
      mono(s.bits, th: th),
      grid(columns: (6pt, 1fr), column-gutter: 3pt,
        box(width: 6pt, height: 6pt, fill: rgb(s.color), stroke: 0.3pt + luma(120)),
        text(weight: "bold", ident(s.name))),
      {
        s.description
        if s.mux != "" { linebreak(); text(style: "italic", size: 0.9em, s.mux) }
        if s.comment != "" { linebreak(); text(fill: comment-color, size: 0.9em, [#L.comment: #s.comment]) }
      },
      s.encoding.join(linebreak()),
      text(size: 0.92em, s.values.join(linebreak())),
    )).flatten(),
  )
}

/// Таблица SDO-обменов кадра.
#let sdo-table(fr, L, th: theme-color) = {
  table(
    columns: (1.4fr, auto, auto, auto, 1.6fr, 1.4fr),
    stroke: 0.5pt + th.line,
    inset: (x: 4pt, y: 3pt),
    table.header(
      _head(th, L.signal), _head(th, L.command), _head(th, L.index),
      _head(th, L.subindex), _head(th, L.description), _head(th, L.value),
    ),
    ..fr.sdo.map(e => (
      text(weight: "bold", ident(e.name)), mono(e.command, th: th), mono(e.index, th: th), mono(e.subindex, th: th),
      e.description, e.value,
    )).flatten(),
  )
}

/// Сводка свойств кадра (ID, тип, DLC, направление, период).
#let frame-props(fr, L, th: theme-color) = {
  table(
    columns: (auto, 1fr, auto, 1fr, auto, 1fr),
    stroke: none,
    inset: (x: 3pt, y: 2pt),
    [*#L.frame*], mono(fr.name, th: th),
    [*#L.id*], [#mono(fr.id, th: th) #if fr.id_formula != "" { text(size: 0.85em, fill: luma(90), "(" + fr.id_formula + ")") }],
    [*#L.type*], fr.type_label,
    [*#L.dlc*], str(fr.dlc),
    [*#L.direction*], fr.direction,
    [*#L.period*], fr.period,
    ..if fr.at("pgn", default: "") != "" { ([*#L.pgn*], mono(fr.pgn, th: th), [*#L.priority*], fr.priority, [], []) },
    ..if fr.at("sender", default: "") != "" {
      ([*#L.sender*], table.cell(colspan: 5, fr.sender))
    },
    ..if fr.at("receivers", default: "") != "" {
      ([*#L.receivers*], table.cell(colspan: 5, fr.receivers))
    },
  )
}

/// Сводка свойств шины.
#let bus-props(bus, L, th: theme-color) = {
  table(
    columns: (auto, 1fr, auto, 1fr),
    stroke: none,
    inset: (x: 3pt, y: 2pt),
    [*#L.protocol*], bus.protocol, [*#L.bitrate*], bus.bitrate,
    [*#L.interface*], mono(bus.interface, th: th),
    [*#L.summary*], [#bus.stats.frames #L.frames_total, #bus.stats.signals #L.signals_total],
  )
}

/// Таблица адресации шины.
#let addressing-table(bus, L, th: theme-color, unused-fill: luma(245)) = {
  let a = bus.addressing
  if a.kind == "matrix" {
    let rows = ()
    for row in a.rows {
      let entries = ()
      for c in row.broadcast { entries.push((a.broadcast_label, c)) }
      for (i, cells) in row.cells.enumerate() {
        for c in cells { entries.push((a.columns.at(i), c)) }
      }
      let n = calc.max(entries.len(), 1)
      let typecell = table.cell(rowspan: n, fill: if row.used { none } else { unused-fill })[
        *#row.label* #mono(row.base, th: th) \ #text(size: 0.85em, fill: luma(90), row.purpose)]
      if entries.len() == 0 {
        rows.push((typecell, table.cell(colspan: 3, fill: unused-fill)[—]))
      } else {
        for (k, e) in entries.enumerate() {
          let r = ()
          if k == 0 { r.push(typecell) }
          r += (e.at(0), mono(e.at(1).id, th: th), e.at(1).description)
          rows.push(r)
        }
      }
    }
    table(
      columns: (32mm, 38mm, 18mm, 1fr),
      stroke: 0.5pt + th.line,
      inset: (x: 4pt, y: 3pt),
      table.header(_head(th, L.message_type), _head(th, L.device), _head(th, L.id), _head(th, L.purpose)),
      ..rows.flatten(),
    )
  } else {
    let pg = a.at("has_pgn", default: false)
    let sd = a.at("has_sender", default: false)
    let rc = a.at("has_receivers", default: false)
    let cols = (26mm, 22mm) + (if pg { (15mm,) } else { () }) + (1fr, 22mm, 22mm) + (if sd { (24mm,) } else { () }) + (if rc { (28mm,) } else { () })
    let heads = (L.device, L.id) + (if pg { (L.pgn,) } else { () }) + (L.purpose, L.direction, L.period) + (if sd { (L.sender,) } else { () }) + (if rc { (L.receivers,) } else { () })
    table(
      columns: cols,
      stroke: 0.5pt + th.line,
      inset: (x: 4pt, y: 3pt),
      table.header(..heads.map(h => _head(th, h))),
      ..a.rows.map(r => (
        (r.device, mono(r.id, th: th)) + (if pg { (mono(r.pgn, th: th),) } else { () })
        + (r.description, r.direction, r.period) + (if sd { (r.sender,) } else { () }) + (if rc { (r.receivers,) } else { () })
      )).flatten(),
    )
  }
}

/// Автор записи истории со ссылкой на GitHub.
#let history-author(h, th: theme-color) = {
  h.author
  if h.github != "" {
    if h.author != "" { linebreak() }
    link(h.github_url, text(fill: th.accent, "@" + h.github))
  }
}

/// История версий карты.
#let history-table(doc, L, th: theme-color) = {
  table(
    columns: (auto, auto, auto, 1fr),
    stroke: 0.5pt + th.line,
    inset: (x: 4pt, y: 3pt),
    table.header(_head(th, L.version), _head(th, L.date), _head(th, L.author), _head(th, L.description)),
    ..doc.history.map(h => (
      text(weight: "bold", h.version), h.date, history-author(h, th: th),
      list(..h.changes),
    )).flatten(),
  )
}

/// Все кадры шины (широковещательные, затем по устройствам) — для обхода в шаблонах.
#let bus-groups(bus, L) = {
  let groups = ()
  if bus.broadcast.len() > 0 {
    groups.push((title: L.broadcast, description: "", frames: bus.broadcast, receives: (), sends_other: ()))
  }
  for dev in bus.devices {
    groups.push((
      title: dev.label + (if dev.title != "" { " — " + dev.title } else { "" }),
      description: dev.description,
      frames: dev.frames,
      receives: dev.at("receives", default: ()),
      sends_other: dev.at("sends_other", default: ()),
    ))
  }
  groups
}

/// Сводка обмена устройства: принимаемые кадры (`peer` — отправитель) или кадры других устройств,
/// которые оно передаёт (`peer` — владелец кадра).
#let exchange-table(rows, peer, L, th: theme-color) = {
  table(
    columns: (22mm, auto, auto, 1fr),
    stroke: 0.5pt + th.line,
    inset: (x: 4pt, y: 3pt),
    table.header(_head(th, L.id), _head(th, L.frame), _head(th, peer), _head(th, L.description)),
    ..rows.map(c => (mono(c.id, th: th), mono(ident(c.name), th: th), c.peer, c.description)).flatten(),
  )
}

/// Заголовок кадра: «0x196 · СОСТОЯНИЯ».
#let frame-title(fr) = fr.id + " · " + (if fr.title != "" { fr.title } else { fr.name })

// ---------------------------------------------------------------- общие элементы ГОСТ

/// Дополнительные графы на поле подшивки (ГОСТ 2.104, графы 19–25; ГОСТ 19.104).
/// `first` — добавить «Перв. примен.» и «Справ. №» в верхней части.
#let gost-side-fields(font: ("PT Sans",), stroke: 0.5mm, first: false) = {
  let x0 = 8mm
  let w1 = 5mm
  let w2 = 7mm
  let column(items, y-start, downward) = {
    let y = y-start
    for (label, h) in items {
      if not downward { y -= h }
      place(top + left, dx: x0, dy: y, rect(width: w1 + w2, height: h, stroke: stroke))
      place(top + left, dx: x0 + w1, dy: y, line(angle: 90deg, length: h, stroke: stroke))
      place(top + left, dx: x0, dy: y, box(width: w1, height: h, align(center + horizon,
        rotate(-90deg, reflow: true, text(font: font, size: 6.5pt, label)))))
      if downward { y += h }
    }
  }
  column((("Инв. № подл.", 25mm), ("Подп. и дата", 35mm), ("Взам. инв. №", 25mm),
          ("Инв. № дубл.", 25mm), ("Подп. и дата", 35mm)), 292mm, false)
  if first { column((("Перв. примен.", 60mm), ("Справ. №", 60mm)), 5mm, true) }
}

/// Лист регистрации изменений (ГОСТ 2.503, ГОСТ 19.603) — пустая форма.
#let gost-change-register(rows: 22, size: 8pt) = {
  set text(size: size)
  set par(first-line-indent: 0pt, justify: false)
  let h(body) = table.cell(align: center + horizon, body)
  let v(body) = table.cell(align: center + horizon, rotate(-90deg, reflow: true, body))
  table(
    columns: (10mm, 16mm, 16mm, 16mm, 16mm, 18mm, 20mm, 33mm, 15mm, 15mm),
    rows: (8mm, 27mm) + (8mm,) * rows,
    stroke: 0.4pt,
    table.header(
      table.cell(rowspan: 2, h[Изм.]),
      table.cell(colspan: 4, h[Номера листов (страниц)]),
      table.cell(rowspan: 2, h[Всего листов (страниц) в докум.]),
      table.cell(rowspan: 2, h[№ докум.]),
      table.cell(rowspan: 2, h[Входящий № сопроводительного докум. и дата]),
      table.cell(rowspan: 2, h[Подп.]),
      table.cell(rowspan: 2, h[Дата]),
      v[изменённых], v[заменённых], v[новых], v[аннулированных],
    ),
    ..range(rows * 10).map(_ => []),
  )
}

/// Блок подписи «УТВЕРЖДАЮ» / «СОГЛАСОВАНО»: должность, подпись, дата.
#let gost-sign-block(title, p, year, size: 11pt) = {
  set par(first-line-indent: 0pt, justify: false)
  set text(size: size)
  title
  linebreak()
  if p.position != "" { p.position; linebreak() }
  v(4mm)
  [\_\_\_\_\_\_\_\_\_\_\_\_ #p.name]
  linebreak()
  [«\_\_\_\_» \_\_\_\_\_\_\_\_\_\_\_\_ #year г.]
}

/// Подписи «Разработал / Проверил / Н. контроль» (только заполненные).
#let gost-signers(rows, size: 11pt) = {
  set text(size: size)
  table(
    columns: (auto, 35mm, auto),
    stroke: none,
    align: (left, center, left),
    ..rows.filter(r => r.at(1) != "").map(r => (r.at(0), [\_\_\_\_\_\_\_\_\_\_\_\_], r.at(1))).flatten(),
  )
}

/// Оформление таблиц по ГОСТ: подпись «Таблица N — …» над таблицей, без отступа, не отрывается.
#let gost-tables(body, caption-size: 10pt) = {
  set figure(supplement: [Таблица])
  show figure.where(kind: table): set figure.caption(position: top)
  show figure.where(kind: table): set align(left)
  show figure.caption.where(kind: table): it => block(sticky: true, below: 0.5em, par(first-line-indent: 0pt,
    text(size: caption-size)[Таблица #context it.counter.display(it.numbering) — #it.body]))
  body
}

/// Таблица с подписью; `breakable: false` — не разрывать (битовые диаграммы).
#let gost-table(caption, body, breakable: true) = {
  show figure: set block(breakable: breakable)
  figure(kind: table, caption: caption, body)
}
