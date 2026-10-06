// Шаблон «gost-2.105» — текстовый конструкторский документ ЕСКД.
//
//  * ГОСТ 2.104: рамка (поле подшивки 20 мм, остальные 5 мм), основная надпись по форме 2
//    на первом листе и по форме 2а на последующих, дополнительные графы 19–25 на левом поле;
//  * ГОСТ 2.105: титульный лист, «Содержание», нумерация разделов без точки, таблицы
//    с названием «Таблица N — …», приложение, лист регистрации изменений (ГОСТ 2.503).
//
// Реквизиты берутся из document: designation, litera, organization, signatures, approve, agree.
// Шрифт основной надписи — «GOST type A», если он установлен в системе, иначе PT Sans.

#import "lib.typ": *

#let data = load-data()
#let L = data.labels
#let doc = data.document
#let th = theme-gost

#let font-main = ("PT Sans", "Libertinus Serif")
#let font-stamp = ("GOST type A", "GOST Type A", "ГОСТ тип А", "ISOCPEUR", "PT Sans")
#let thick = 0.5mm       // сплошная основная линия
#let thin = 0.18mm       // сплошная тонкая линия
#let doc-kind = "Карта сигналов"
#let sig = doc.signatures

// ---------------------------------------------------------------- примитивы основной надписи

#let at(x, y, body) = place(top + left, dx: x, dy: y, body)
#let hline(x, y, w, s) = at(x, y, line(length: w, stroke: s))
#let vline(x, y, h, s) = at(x, y, line(angle: 90deg, length: h, stroke: s))
#let cell(x, y, w, h, body, size: 7pt, align: center + horizon) = at(x, y, box(
  width: w, height: h, inset: (x: 0.7mm), clip: true,
  std.align(align, text(font: font-stamp, size: size, body)),
))

#let side-fields(first: false) = gost-side-fields(font: font-stamp, stroke: thick, first: first)

/// Строки «Изм. | Лист | № докум. | Подп. | Дата» (две пустые строки и строка заголовков).
#let change-rows(x0, y0) = {
  let xs = (0mm, 7mm, 17mm, 40mm, 55mm)
  let ws = (7mm, 10mm, 23mm, 15mm, 10mm)
  hline(x0, y0 + 5mm, 65mm, thin)
  hline(x0, y0 + 10mm, 65mm, thin)
  for (i, t) in ("Изм.", "Лист", "№ докум.", "Подп.", "Дата").enumerate() {
    cell(x0 + xs.at(i), y0 + 10mm, ws.at(i), 5mm, t, size: 6.5pt)
  }
}

/// Основная надпись по форме 2 (185 × 40 мм) — первый лист документа.
#let stamp-form2(page-no, total) = {
  let x0 = 20mm
  let y0 = 252mm
  change-rows(x0, y0)
  hline(x0, y0 + 15mm, 185mm, thick)
  for r in range(4, 8) { hline(x0, y0 + r * 5mm, 65mm, thin) }
  vline(x0 + 7mm, y0, 15mm, thick)
  for x in (17mm, 40mm, 55mm, 65mm) { vline(x0 + x, y0, 40mm, thick) }
  vline(x0 + 135mm, y0 + 15mm, 25mm, thick)
  hline(x0 + 135mm, y0 + 20mm, 50mm, thick)
  hline(x0 + 135mm, y0 + 25mm, 50mm, thick)
  vline(x0 + 150mm, y0 + 15mm, 10mm, thick)
  vline(x0 + 170mm, y0 + 15mm, 10mm, thick)
  vline(x0 + 140mm, y0 + 20mm, 5mm, thin)
  vline(x0 + 145mm, y0 + 20mm, 5mm, thin)
  at(x0, y0, rect(width: 185mm, height: 40mm, stroke: thick))

  let rows = (("Разраб.", sig.developed), ("Пров.", sig.checked), ("Т. контр.", sig.tech_control),
              ("Н. контр.", sig.norm_control), ("Утв.", sig.approved))
  for (i, r) in rows.enumerate() {
    let y = y0 + 15mm + i * 5mm
    cell(x0, y, 17mm, 5mm, r.at(0), size: 6.5pt, align: left + horizon)
    cell(x0 + 17mm, y, 23mm, 5mm, r.at(1), size: 6.5pt, align: left + horizon)
  }
  cell(x0 + 65mm, y0, 120mm, 15mm, doc.designation, size: 14pt)
  cell(x0 + 65mm, y0 + 15mm, 70mm, 25mm, [#doc.title \ #text(size: 8pt, doc-kind)], size: 9pt)
  cell(x0 + 135mm, y0 + 15mm, 15mm, 5mm, "Лит.", size: 6.5pt)
  cell(x0 + 150mm, y0 + 15mm, 20mm, 5mm, "Лист", size: 6.5pt)
  cell(x0 + 170mm, y0 + 15mm, 15mm, 5mm, "Листов", size: 6.5pt)
  cell(x0 + 135mm, y0 + 20mm, 5mm, 5mm, doc.litera, size: 6.5pt)
  cell(x0 + 150mm, y0 + 20mm, 20mm, 5mm, str(page-no), size: 7.5pt)
  cell(x0 + 170mm, y0 + 20mm, 15mm, 5mm, str(total), size: 7.5pt)
  at(x0 + 135mm, y0 + 25mm, box(width: 50mm, height: 15mm, inset: 1mm, clip: true, align(center + horizon, {
    if doc.logo != "" {
      image(doc.logo, height: if doc.organization != "" { 7.5mm } else { 12mm }, width: 46mm, fit: "contain")
      if doc.organization != "" { v(0.5mm, weak: true); text(font: font-stamp, size: 5.5pt, doc.organization) }
    } else {
      text(font: font-stamp, size: 8pt, doc.organization)
    }
  })))
}

/// Основная надпись по форме 2а (185 × 15 мм) — последующие листы.
#let stamp-form2a(page-no) = {
  let x0 = 20mm
  let y0 = 277mm
  change-rows(x0, y0)
  for x in (7mm, 17mm, 40mm, 55mm, 65mm, 175mm) { vline(x0 + x, y0, 15mm, thick) }
  hline(x0 + 175mm, y0 + 7mm, 10mm, thick)
  at(x0, y0, rect(width: 185mm, height: 15mm, stroke: thick))
  cell(x0 + 65mm, y0, 110mm, 15mm, doc.designation, size: 14pt)
  cell(x0 + 175mm, y0, 10mm, 7mm, "Лист", size: 6.5pt)
  cell(x0 + 175mm, y0 + 7mm, 10mm, 8mm, str(page-no), size: 8pt)
}

// ---------------------------------------------------------------- страница

#set document(title: doc.title, author: if doc.author != "" { doc.author } else { () })
#set text(font: font-main, size: 11pt, lang: data.lang)
#set par(justify: true, leading: 0.6em, first-line-indent: (amount: 12.5mm, all: true))
#set page(
  paper: "a4",
  margin: (left: 25mm, right: 10mm, top: 12mm, bottom: 27mm),
  background: context {
    let p = here().page()
    let total = counter(page).final().first()
    let marks = query(<eskd-first-sheet>)
    let first = if marks.len() > 0 { marks.first().location().page() } else { 2 }
    at(20mm, 5mm, rect(width: 185mm, height: 287mm, stroke: thick))
    side-fields(first: p == first)
    if p == first { stamp-form2(p, total) } else if p > first { stamp-form2a(p) }
  },
)

#set heading(numbering: "1.1")
#show heading: set text(size: 12pt, weight: "bold")
#show heading: it => block(above: 1.2em, below: 0.8em, sticky: true, it)
#show heading.where(level: 1): set text(size: 13pt)
#show heading.where(numbering: none): set align(center)

#show table: set text(size: 9pt)
#show table: set par(justify: false, first-line-indent: 0pt)
#show: gost-tables
#let tbl(caption, body, breakable: true) = gost-table(caption, body, breakable: breakable)

// Приложение: в тексте — три строки по центру, в содержании — одна.
#show <appendix-a>: it => align(center, block(below: 0.8em)[
  #text(weight: "bold")[Приложение А] \ (справочное) \ #text(weight: "bold")[История версий карты]])

// ---------------------------------------------------------------- титульный лист (ГОСТ 2.105)

#let sign-block(title, p) = gost-sign-block(title, p, doc.year)

#page[
  #set par(first-line-indent: 0pt, justify: false)
  #align(center)[
    #logo(doc, height: 14mm)
    #if doc.organization != "" { v(2mm); text(size: 12pt, upper(doc.organization)) }
  ]
  #v(10mm)
  #grid(
    columns: (1fr, 1fr),
    column-gutter: 20mm,
    align: (left + top, left + top),
    {
      for p in doc.agree { sign-block([СОГЛАСОВАНО], p); v(6mm) }
    },
    if doc.approve != none { sign-block([УТВЕРЖДАЮ], doc.approve) },
  )
  #v(1fr)
  #align(center)[
    #text(size: 16pt, weight: "bold", upper(doc.title))
    #if doc.subtitle != "" { v(3mm); text(size: 13pt, doc.subtitle) }
    #v(8mm)
    #text(size: 14pt, weight: "bold", upper(doc-kind))
    #v(4mm)
    #text(size: 14pt, doc.designation)
    #v(4mm)
    #context text(size: 12pt)[Листов #counter(page).final().first()]
  ]
  #v(1fr)
  #align(right, gost-signers((("Разработал", sig.developed), ("Проверил", sig.checked),
                               ("Н. контроль", sig.norm_control))))
  #v(8mm)
  #align(center, text(size: 11pt, (if doc.city != "" { doc.city + " " } else { "" }) + doc.year))
]

// ---------------------------------------------------------------- первый лист (форма 2)

#metadata("first-sheet") <eskd-first-sheet>
// Резерв места под основную надпись формы 2: она на 25 мм выше формы 2а.
#place(bottom, float: true, clearance: 0mm, block(height: 25mm))

#outline(title: [Содержание], depth: 3, indent: auto)

// ---------------------------------------------------------------- текст

#let frame-section(fr, n) = {
  heading(level: 3, frame-title(fr))
  if fr.description != "" { par(fr.description) }
  block(breakable: false, frame-props(fr, L, th: th))
  if fr.comment != "" { par([Примечание — #fr.comment]) }
  if fr.signals.len() == 0 {
    par(L.no_signals)
  } else {
    if fr.grid.len() > 0 { tbl([Раскладка кадра #fr.id #fr.name], bit-diagram(fr, L, th: th), breakable: false) }
    tbl([Сигналы кадра #fr.id #fr.name], signal-table(fr, L, th: th, comment-color: black))
  }
  if fr.sdo.len() > 0 { tbl([SDO-обмены кадра #fr.id #fr.name], sdo-table(fr, L, th: th)) }
}

= Общие положения

Настоящий документ содержит карту сигналов «#doc.title» версии #doc.version: адресацию кадров
и содержание сигналов по шинам (шин~— #doc.stats.buses, устройств~— #doc.stats.devices,
кадров~— #doc.stats.frames, сигналов~— #doc.stats.signals).

#doc.bit_note

Физическое значение сигнала вычисляется по формуле: physical = raw × factor + offset.

#for bus in data.buses {
  heading(level: 1, bus.title)
  if bus.description != "" { par(bus.description) }
  block(breakable: false, bus-props(bus, L, th: th))
  heading(level: 2, L.addressing)
  tbl([Адресация кадров. #bus.title], addressing-table(bus, L, th: th, unused-fill: none))
  for g in bus-groups(bus, L) {
    heading(level: 2, g.title)
    if g.description != "" { par(g.description) }
    if g.receives.len() > 0 {
      tbl([Кадры, принимаемые устройством #g.title], exchange-table(g.receives, L.sender, L, th: th))
    }
    if g.sends_other.len() > 0 {
      tbl([Кадры других устройств, передаваемые устройством #g.title],
        exchange-table(g.sends_other, L.device, L, th: th))
    }
    for (n, fr) in g.frames.enumerate() { frame-section(fr, n) }
  }
}

// ---------------------------------------------------------------- приложение

#if doc.history.len() > 0 {
  pagebreak(weak: true)
  [#heading(level: 1, numbering: none)[Приложение А (справочное) История версий карты] <appendix-a>]
  tbl([История версий карты], history-table(doc, L, th: th))
}

// ---------------------------------------------------------------- лист регистрации изменений (ГОСТ 2.503)

#pagebreak(weak: true)
#heading(level: 1, numbering: none)[Лист регистрации изменений]
#gost-change-register()
