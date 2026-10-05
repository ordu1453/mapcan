// Шаблон «gost-7.32» — отчёт по ГОСТ 7.32-2017.
//
//  * поля: левое 30 мм, правое 15 мм, верхнее и нижнее 20 мм; шрифт типа Times (PT Serif) 12 пт,
//    полуторный интервал, абзацный отступ 1,25 см;
//  * номер страницы — внизу по центру, титульный лист включается в нумерацию без номера;
//  * структурные элементы (СПИСОК ИСПОЛНИТЕЛЕЙ, РЕФЕРАТ, СОДЕРЖАНИЕ, ПРИЛОЖЕНИЕ) — прописными
//    полужирными по центру, без номера; разделы — с абзацного отступа, «1», «1.1»;
//  * таблицы: «Таблица N — Название» над таблицей слева.
//
// Реквизиты: document.organization, approve, signatures, city.

#import "lib.typ": *

#let data = load-data()
#let L = data.labels
#let doc = data.document
#let th = theme-gost

#let font-main = ("PT Serif", "Libertinus Serif")
#let doc-kind = "Карта сигналов"
#let sig = doc.signatures

#set document(title: doc.title, author: if doc.author != "" { doc.author } else { () })
#set text(font: font-main, size: 12pt, lang: data.lang)
#set par(justify: true, leading: 1em, spacing: 1em, first-line-indent: (amount: 12.5mm, all: true))
#show: gost-tables.with(caption-size: 12pt)
#show table: set text(size: 10pt)
#show table: set par(justify: false, first-line-indent: 0pt, leading: 0.55em)

#set heading(numbering: "1.1")
#show heading: set text(size: 12pt, weight: "bold")
// Структурные элементы — прописными по центру с новой страницы; разделы — с абзацного
// отступа, каждый раздел первого уровня — с новой страницы.
#show heading: it => {
  if it.numbering == none {
    pagebreak(weak: true)
    align(center, block(below: 1.2em, sticky: true, upper(it.body)))
  } else {
    if it.level == 1 { pagebreak(weak: true) }
    block(above: 1.4em, below: 1em, sticky: true, pad(left: 12.5mm, it))
  }
}

#set page(
  paper: "a4",
  margin: (left: 30mm, right: 15mm, top: 20mm, bottom: 20mm),
  footer: context {
    if here().page() > 1 { align(center, text(size: 12pt, counter(page).display())) }
  },
)

// ---------------------------------------------------------------- титульный лист

#page[
  #set par(first-line-indent: 0pt, justify: false, leading: 0.65em)
  #align(center)[
    #logo(doc, height: 15mm)
    #if doc.organization != "" { v(2mm); text(size: 12pt, upper(doc.organization)) }
  ]
  #v(12mm)
  #if doc.approve != none {
    align(right, box(width: 80mm, align(left, gost-sign-block([УТВЕРЖДАЮ], doc.approve, doc.year, size: 12pt))))
  }
  #v(1fr)
  #align(center)[
    #text(size: 14pt, weight: "bold")[ОТЧЁТ]
    #v(4mm)
    #text(size: 14pt, weight: "bold", upper(doc-kind))
    #v(6mm)
    #text(size: 16pt, weight: "bold", upper(doc.title))
    #if doc.subtitle != "" { v(3mm); text(size: 13pt, doc.subtitle) }
    #v(4mm)
    #text(size: 12pt)[Версия #doc.version]
    #if doc.designation != "" { v(2mm); text(size: 12pt, doc.designation) }
  ]
  #v(1fr)
  #if sig.approved != "" or sig.developed != "" {
    grid(columns: (1fr, 40mm, auto), row-gutter: 6mm, align: (left + bottom, center + bottom, left + bottom),
      ..if sig.approved != "" { ([Руководитель работы], [\_\_\_\_\_\_\_\_\_\_\_\_], sig.approved) },
      ..if sig.developed != "" { ([Ответственный исполнитель], [\_\_\_\_\_\_\_\_\_\_\_\_], sig.developed) },
    )
  }
  #v(12mm)
  #align(center, text(size: 12pt, (if doc.city != "" { doc.city + " " } else { "" }) + doc.year))
]

// ---------------------------------------------------------------- список исполнителей

#let executors = (
  ("Руководитель работы", sig.approved),
  ("Исполнитель", sig.developed),
  ("Проверил", sig.checked),
  ("Технический контроль", sig.tech_control),
  ("Нормоконтроль", sig.norm_control),
).filter(r => r.at(1) != "")

#if executors.len() > 0 {
  heading(numbering: none, outlined: false)[Список исполнителей]
  set par(first-line-indent: 0pt)
  table(
    columns: (1fr, 40mm, 45mm),
    stroke: none,
    row-gutter: 8mm,
    align: (left + bottom, center + bottom, left + bottom),
    ..executors.map(r => (r.at(0), [\_\_\_\_\_\_\_\_\_\_\_\_ \ #text(size: 9pt)[подпись, дата]], r.at(1))).flatten(),
  )
}

// ---------------------------------------------------------------- реферат

#heading(numbering: none, outlined: false)[Реферат]

#context {
  let pages = counter(page).final().first()
  let tables = counter(figure.where(kind: table)).final().first()
  let apps = if doc.history.len() > 0 { 1 } else { 0 }
  par[Отчёт #pages~с., #tables~табл., #apps~прил.]
}

#par(first-line-indent: 0pt)[КАРТА СИГНАЛОВ, CAN, CANOPEN, КАДР, СИГНАЛ, БИТОВАЯ РАСКЛАДКА, ИДЕНТИФИКАТОР]

Объектом рассмотрения является обмен данными по шинам CAN, описанный картой сигналов
«#doc.title» версии #doc.version.

Цель работы — документирование адресации кадров и содержания сигналов: позиций бит,
кодирования, физических величин и таблиц значений.

В отчёте описано шин~— #doc.stats.buses, устройств~— #doc.stats.devices,
кадров~— #doc.stats.frames, сигналов~— #doc.stats.signals. Документ сформирован утилитой
canmap из YAML-карты сигналов, являющейся единственным источником данных для документации
и программного кода.

// ---------------------------------------------------------------- содержание

#show outline: it => { pagebreak(weak: true); it }
#outline(title: [Содержание], depth: 3, indent: auto)

// ---------------------------------------------------------------- основная часть

#let frame-section(fr) = {
  heading(level: 3, frame-title(fr))
  if fr.description != "" { par(fr.description) }
  block(breakable: false, frame-props(fr, L, th: th))
  if fr.comment != "" { par([Примечание — #fr.comment]) }
  if fr.signals.len() == 0 {
    par(L.no_signals)
  } else {
    if fr.grid.len() > 0 {
      gost-table([Раскладка кадра #fr.id #fr.name], bit-diagram(fr, L, th: th), breakable: false)
    }
    gost-table([Сигналы кадра #fr.id #fr.name], signal-table(fr, L, th: th, comment-color: black))
  }
  if fr.sdo.len() > 0 { gost-table([SDO-обмены кадра #fr.id #fr.name], sdo-table(fr, L, th: th)) }
}

= Общие сведения

Карта сигналов «#doc.title» описывает адресацию кадров и содержание сигналов обмена
по шинам CAN.

#doc.bit_note

Физическое значение сигнала вычисляется по формуле: physical = raw × factor + offset.

#for bus in data.buses {
  heading(level: 1, bus.title)
  if bus.description != "" { par(bus.description) }
  block(breakable: false, bus-props(bus, L, th: th))
  heading(level: 2, L.addressing)
  gost-table([Адресация кадров. #bus.title], addressing-table(bus, L, th: th, unused-fill: none))
  for g in bus-groups(bus, L) {
    heading(level: 2, g.title)
    if g.description != "" { par(g.description) }
    for fr in g.frames { frame-section(fr) }
  }
}

// ---------------------------------------------------------------- приложение

#show <appendix-a>: it => {
  pagebreak(weak: true)
  align(center, block(below: 1.2em, sticky: true)[
    #text(weight: "bold")[ПРИЛОЖЕНИЕ А] \ (справочное) \ #text(weight: "bold")[История версий карты]])
}

#if doc.history.len() > 0 {
  [#heading(level: 1, numbering: none)[Приложение А (справочное) История версий карты] <appendix-a>]
  gost-table([История версий карты], history-table(doc, L, th: th))
}
