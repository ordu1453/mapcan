// Шаблон «mapcan» — техническое оформление без требований ГОСТ.
//
// Данные карты — JSON в `sys.inputs.data` (см. mapcan/docmodel.py), общие элементы — lib.typ.
// Своя версия: `mapcan template pdf -o my.typ` (рядом скопируется lib.typ), затем
// `mapcan export pdf map.yaml --template my.typ`.

#import "lib.typ": *

#let data = load-data()
#let L = data.labels
#let doc = data.document
#let th = theme-color

#let font-main = ("PT Sans", "Libertinus Serif")

#set document(title: doc.title, author: if doc.author != "" { doc.author } else { () })
#set text(font: font-main, size: 9.5pt, lang: data.lang)
#set par(justify: false, leading: 0.55em)
#set heading(numbering: "1.1.")
#show heading: set text(fill: th.accent)
#show heading.where(level: 1): it => { pagebreak(weak: true); v(0.3em); it; v(0.4em) }
#show table.cell.where(y: 0): set text(weight: "bold")

#set page(
  paper: "a4",
  margin: (top: 22mm, bottom: 18mm, left: 20mm, right: 15mm),
  header: context {
    if counter(page).get().first() > 1 {
      set text(size: 8pt, fill: luma(90))
      grid(columns: (auto, 1fr, auto), column-gutter: 6pt, align: horizon,
        logo(doc, height: 5mm), doc.title, [#L.version #doc.version])
      v(-0.6em)
      line(length: 100%, stroke: 0.4pt + th.line)
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
  #logo(doc, height: 18mm)
  #if doc.organization != "" { v(2mm); text(size: 11pt, fill: luma(80), doc.organization) }
  #v(45mm)
  #text(size: 26pt, weight: "bold", fill: th.accent, doc.title)
  #if doc.subtitle != "" { v(2mm); text(size: 14pt, doc.subtitle) }
  #v(14mm)
  #table(
    columns: (45mm, 70mm),
    stroke: none,
    inset: (x: 0pt, y: 4pt),
    [*#L.version*], doc.version,
    [*#L.date*], doc.date,
    ..if doc.designation != "" { ([*#L.designation*], doc.designation) },
    ..if doc.author != "" { ([*#L.author*], doc.author) },
  )
  #v(1fr)
  #block(fill: rgb("#F2F6FA"), inset: 8pt, radius: 3pt, width: 100%)[
    #text(size: 9pt, doc.bit_note)
  ]
]

#outline(title: L.contents, depth: 3, indent: auto)

// ---------------------------------------------------------------- кадры

#let frame-section(fr) = {
  block(breakable: false, {
    heading(level: 3, frame-title(fr))
    if fr.description != "" { par(fr.description) }
    frame-props(fr, L, th: th)
    if fr.comment != "" { par(text(fill: rgb("#9C5700"), [#L.comment: #fr.comment])) }
    if fr.signals.len() == 0 {
      par(text(style: "italic", fill: luma(110), L.no_signals))
    } else if fr.grid.len() > 0 {
      bit-diagram(fr, L, th: th)
    }
  })
  if fr.signals.len() > 0 {
    v(2mm)
    signal-table(fr, L, th: th)
  }
  if fr.sdo.len() > 0 {
    v(2mm)
    text(weight: "bold", L.sdo)
    sdo-table(fr, L, th: th)
  }
  v(4mm)
}

#for bus in data.buses {
  heading(level: 1, bus.title)
  if bus.description != "" { par(bus.description) }
  bus-props(bus, L, th: th)

  heading(level: 2, L.addressing)
  addressing-table(bus, L, th: th)

  for g in bus-groups(bus, L) {
    heading(level: 2, g.title)
    if g.description != "" { par(g.description) }
    for fr in g.frames { frame-section(fr) }
  }
}

// ---------------------------------------------------------------- приложение

#if doc.history.len() > 0 {
  heading(level: 1, numbering: none, L.history)
  history-table(doc, L, th: th)
}
