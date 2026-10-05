// Шаблон PDF-документа canmap.
//
// Данные карты передаются как JSON через `sys.inputs.data` (см. canmap/docmodel.py).
// Чтобы сделать своё оформление, выполните `canmap template pdf -o my.typ`,
// отредактируйте копию и соберите: `canmap export pdf map.yaml --template my.typ`.

#let data = json(bytes(sys.inputs.at("data", default: "{}")))
#let L = data.labels
#let doc = data.document

#let font-main = ("PT Sans", "Libertinus Serif")
#let font-mono = ("DejaVu Sans Mono",)
#let accent = rgb("#1F4E79")
#let line-color = rgb("#A6A6A6")

// Разрешить перенос длинных идентификаторов по «_».
#let ident(s) = s.replace("_", "_\u{200B}")
#let mono(s) = text(font: font-mono, size: 0.92em, s)

#set document(title: doc.title, author: if doc.author != "" { doc.author } else { () })
#set text(font: font-main, size: 9.5pt, lang: data.lang)
#set par(justify: false, leading: 0.55em)
#set heading(numbering: "1.1.")
#show heading: set text(fill: accent)
#show heading.where(level: 1): it => { pagebreak(weak: true); v(0.3em); it; v(0.4em) }
#set table(stroke: 0.5pt + line-color, inset: (x: 4pt, y: 3pt))
#show table.cell.where(y: 0): set text(weight: "bold")

#set page(
  paper: "a4",
  margin: (top: 22mm, bottom: 18mm, left: 20mm, right: 15mm),
  header: context {
    if counter(page).get().first() > 1 {
      set text(size: 8pt, fill: luma(90))
      grid(columns: (1fr, auto), doc.title, [#L.version #doc.version])
      v(-0.6em)
      line(length: 100%, stroke: 0.4pt + line-color)
    }
  },
  footer: context {
    set text(size: 8pt, fill: luma(90))
    grid(columns: (1fr, auto),
      [#L.generated · #doc.date],
      [#counter(page).display() / #counter(page).final().first()])
  },
)

// ---------------------------------------------------------------- титул
#page(header: none)[
  #v(55mm)
  #text(size: 26pt, weight: "bold", fill: accent, doc.title)
  #if doc.subtitle != "" { v(2mm); text(size: 14pt, doc.subtitle) }
  #v(14mm)
  #table(
    columns: (45mm, 70mm),
    stroke: none,
    inset: (x: 0pt, y: 4pt),
    [*#L.version*], doc.version,
    [*#L.date*], doc.date,
    ..if doc.author != "" { ([*#L.author*], doc.author) },
    ..if doc.organization != "" { ([], doc.organization) },
  )
  #v(1fr)
  #block(fill: rgb("#F2F6FA"), inset: 8pt, radius: 3pt, width: 100%)[
    #text(size: 9pt, doc.bit_note)
  ]
]

#outline(title: L.contents, depth: 3, indent: auto)

// ---------------------------------------------------------------- элементы

#let bit-diagram(fr) = {
  let cols = (14mm,) + (1fr,) * 8
  table(
    columns: cols,
    align: center + horizon,
    inset: (x: 2pt, y: 4pt),
    table.header(
      table.cell(fill: accent)[#text(fill: white, L.byte)],
      ..range(7, -1, step: -1).map(b => table.cell(fill: accent)[#text(fill: white, str(b))]),
    ),
    ..fr.grid.map(row => (
      table.cell(fill: luma(235))[*#row.byte*],
      ..row.segments.map(seg => table.cell(
        colspan: seg.span,
        fill: rgb(seg.color),
        stroke: if seg.conflict { 1.5pt + red } else { 0.5pt + line-color },
      )[#text(size: 7pt, fill: if seg.conflict { red } else { black }, ident(seg.label))]),
    )).flatten(),
  )
}

#let signal-table(fr) = {
  table(
    columns: (auto, auto, 1.25fr, 1.45fr, 0.95fr, 2.3fr),
    align: (center, center, left, left, left, left),
    table.header(L.byte, L.bits, L.signal, L.description, L.encoding, L.values),
    ..fr.signals.map(s => (
      mono(s.bytes),
      mono(s.bits),
      grid(columns: (6pt, 1fr), column-gutter: 3pt,
        box(width: 6pt, height: 6pt, fill: rgb(s.color), stroke: 0.3pt + luma(120)),
        text(weight: "bold", ident(s.name))),
      {
        s.description
        if s.mux != "" { linebreak(); text(style: "italic", size: 0.9em, s.mux) }
        if s.comment != "" { linebreak(); text(fill: rgb("#9C5700"), size: 0.9em, [#L.comment: #s.comment]) }
      },
      s.encoding.join(linebreak()),
      text(size: 0.92em, s.values.join(linebreak())),
    )).flatten(),
  )
}

#let sdo-table(fr) = {
  table(
    columns: (1.4fr, auto, auto, auto, 1.6fr, 1.4fr),
    table.header(L.signal, L.command, L.index, L.subindex, L.description, L.value),
    ..fr.sdo.map(e => (
      text(weight: "bold", ident(e.name)), mono(e.command), mono(e.index), mono(e.subindex),
      e.description, e.value,
    )).flatten(),
  )
}

#let frame-section(fr) = {
  let head = fr.id + " · " + (if fr.title != "" { fr.title } else { fr.name })
  block(breakable: false, {
  heading(level: 3, head)
  if fr.description != "" { par(fr.description) }
  table(
    columns: (auto, 1fr, auto, 1fr, auto, 1fr),
    stroke: none,
    inset: (x: 3pt, y: 2pt),
    [*#L.frame*], mono(fr.name),
    [*#L.id*], [#mono(fr.id) #if fr.id_formula != "" { text(size: 0.85em, fill: luma(90), "(" + fr.id_formula + ")") }],
    [*#L.type*], fr.type_label,
    [*#L.dlc*], str(fr.dlc),
    [*#L.direction*], fr.direction,
    [*#L.period*], fr.period,
  )
  if fr.comment != "" { par(text(fill: rgb("#9C5700"), [#L.comment: #fr.comment])) }
  if fr.signals.len() == 0 {
    par(text(style: "italic", fill: luma(110), L.no_signals))
  } else if fr.grid.len() > 0 {
    bit-diagram(fr)
  }
  })
  if fr.signals.len() > 0 {
    v(2mm)
    signal-table(fr)
  }
  if fr.sdo.len() > 0 {
    v(2mm)
    text(weight: "bold", L.sdo)
    sdo-table(fr)
  }
  v(4mm)
}

#let addressing(bus) = {
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
      let typecell = table.cell(rowspan: n, fill: if row.used { white } else { luma(245) })[
        *#row.label* #mono(row.base) \ #text(size: 0.85em, fill: luma(90), row.purpose)]
      if entries.len() == 0 {
        rows.push((typecell, table.cell(colspan: 3, fill: luma(245))[—]))
      } else {
        for (k, e) in entries.enumerate() {
          let r = ()
          if k == 0 { r.push(typecell) }
          r += (e.at(0), mono(e.at(1).id), e.at(1).description)
          rows.push(r)
        }
      }
    }
    table(
      columns: (32mm, 38mm, 18mm, 1fr),
      table.header(L.message_type, L.device, L.id, L.purpose),
      ..rows.flatten(),
    )
  } else {
    table(
      columns: (30mm, 18mm, 1fr, 14mm, 26mm),
      table.header(L.device, L.id, L.purpose, L.direction, L.period),
      ..a.rows.map(r => (r.device, mono(r.id), r.description, r.direction, r.period)).flatten(),
    )
  }
}

// ---------------------------------------------------------------- шины

#for bus in data.buses {
  heading(level: 1, bus.title)
  if bus.description != "" { par(bus.description) }
  table(
    columns: (auto, 1fr, auto, 1fr),
    stroke: none,
    inset: (x: 3pt, y: 2pt),
    [*#L.protocol*], bus.protocol, [*#L.bitrate*], bus.bitrate,
    [*#L.interface*], mono(bus.interface),
    [*#L.summary*], [#bus.stats.frames #L.frames_total, #bus.stats.signals #L.signals_total],
  )

  heading(level: 2, L.addressing)
  addressing(bus)

  if bus.broadcast.len() > 0 {
    heading(level: 2, L.broadcast)
    for fr in bus.broadcast { frame-section(fr) }
  }
  for dev in bus.devices {
    heading(level: 2, dev.label + (if dev.title != "" { " — " + dev.title } else { "" }))
    if dev.description != "" { par(dev.description) }
    for fr in dev.frames { frame-section(fr) }
  }
}

// ---------------------------------------------------------------- приложение

#if doc.history.len() > 0 {
  heading(level: 1, numbering: none, L.history)
  table(
    columns: (auto, auto, auto, 1fr),
    table.header(L.version, L.date, L.author, L.description),
    ..doc.history.map(h => (
      text(weight: "bold", h.version), h.date, h.author,
      list(..h.changes),
    )).flatten(),
  )
}
