// Шаблон «gost-19» — программный документ ЕСПД.
//
//  * ГОСТ 19.104: лист утверждения (ЛУ, отдельный документ — в нумерацию не входит),
//    титульный лист, графы на поле подшивки;
//  * ГОСТ 19.105 / 19.106: номер страницы над текстом посередине, обозначение документа
//    в верхней части каждой страницы, «АННОТАЦИЯ», «СОДЕРЖАНИЕ», заголовки разделов
//    прописными буквами симметрично тексту, приложения, лист регистрации изменений (ГОСТ 19.603).
//
// Реквизиты: document.designation (напр. «RU.12345678.00001-01 90 01»), organization,
// approve, agree, signatures.

#import "lib.typ": *

#let data = load-data()
#let L = data.labels
#let doc = data.document
#let th = theme-gost

#let font-main = ("PT Serif", "Libertinus Serif")
#let doc-kind = "Карта сигналов"
#let sig = doc.signatures
#let lu-designation = if doc.designation != "" { doc.designation + "-ЛУ" } else { "" }

#set document(title: doc.title, author: if doc.author != "" { doc.author } else { () })
#set text(font: font-main, size: 12pt, lang: data.lang)
#set par(justify: true, leading: 0.65em, first-line-indent: (amount: 12.5mm, all: true))
#show: gost-tables
#show table: set text(size: 9.5pt)
#show table: set par(justify: false, first-line-indent: 0pt)

#set heading(numbering: "1.1.")
#show heading: it => block(above: 1.3em, below: 0.9em, sticky: true, it)
#show heading: set text(size: 12pt, weight: "bold")
// Разделы — прописными буквами симметрично тексту.
#show heading.where(level: 1): it => align(center, block(above: 1.3em, below: 0.9em, sticky: true,
  upper(it)))
#show heading.where(numbering: none): set align(center)

#set page(paper: "a4", margin: (left: 25mm, right: 10mm, top: 25mm, bottom: 20mm))

// ---------------------------------------------------------------- лист утверждения

#page(header: none, background: gost-side-fields(font: font-main))[
  #set par(first-line-indent: 0pt, justify: false)
  #align(center)[
    #logo(doc, height: 14mm)
    #if doc.organization != "" { v(2mm); text(size: 12pt, upper(doc.organization)) }
  ]
  #v(10mm)
  #grid(columns: (1fr, 1fr), column-gutter: 20mm,
    { for p in doc.agree { gost-sign-block([СОГЛАСОВАНО], p, doc.year); v(6mm) } },
    if doc.approve != none { gost-sign-block([УТВЕРЖДАЮ], doc.approve, doc.year) },
  )
  #v(1fr)
  #align(center)[
    #text(size: 16pt, weight: "bold", upper(doc.title))
    #if doc.subtitle != "" { v(3mm); text(size: 13pt, doc.subtitle) }
    #v(8mm)
    #text(size: 14pt, weight: "bold", upper(doc-kind))
    #v(6mm)
    #text(size: 14pt, weight: "bold")[ЛИСТ УТВЕРЖДЕНИЯ]
    #v(4mm)
    #text(size: 13pt, lu-designation)
  ]
  #v(1fr)
  #align(right)[
    #set text(size: 11pt)
    Представители предприятия-разработчика
    #v(3mm)
    #gost-signers((("Руководитель разработки", sig.approved), ("Разработчик", sig.developed),
                   ("Проверил", sig.checked), ("Нормоконтролёр", sig.norm_control)))
  ]
  #v(8mm)
  #align(center, text(size: 12pt, (if doc.city != "" { doc.city + " " } else { "" }) + doc.year))
]

// ---------------------------------------------------------------- титульный лист (стр. 1)

#counter(page).update(1)
#page(header: none, background: gost-side-fields(font: font-main))[
  #set par(first-line-indent: 0pt, justify: false)
  #if lu-designation != "" { align(left, text(size: 12pt)[УТВЕРЖДЁН \ #lu-designation]) }
  #v(1fr)
  #align(center)[
    #text(size: 16pt, weight: "bold", upper(doc.title))
    #if doc.subtitle != "" { v(3mm); text(size: 13pt, doc.subtitle) }
    #v(8mm)
    #text(size: 14pt, weight: "bold", upper(doc-kind))
    #v(4mm)
    #text(size: 13pt, doc.designation)
    #v(4mm)
    #context text(size: 12pt)[Листов #counter(page).final().first()]
  ]
  #v(1fr)
  #align(center, text(size: 12pt, (if doc.city != "" { doc.city + " " } else { "" }) + doc.year))
]

// ---------------------------------------------------------------- страницы документа

#set page(header: context {
  set text(size: 11pt)
  set par(first-line-indent: 0pt)
  align(center)[
    #counter(page).display() \
    #text(size: 10pt, doc.designation)
  ]
})

#heading(level: 1, numbering: none, outlined: false)[Аннотация]

Документ «#doc.title» (версия #doc.version) содержит карту сигналов обмена по
шинам CAN: адресацию кадров, битовую раскладку и описание сигналов. Описано шин~—
#doc.stats.buses, устройств~— #doc.stats.devices, кадров~— #doc.stats.frames,
сигналов~— #doc.stats.signals.

В разделе 1 приведены общие сведения и соглашения о нумерации бит, в последующих
разделах — адресация и содержание кадров каждой шины. В приложении 1 приведена история
версий карты.

Документ сформирован утилитой canmap из YAML-карты сигналов.

#pagebreak()
#outline(title: [Содержание], depth: 3, indent: auto)
#pagebreak()

#let frame-section(fr) = {
  heading(level: 3, frame-title(fr))
  if fr.description != "" { par(fr.description) }
  block(breakable: false, frame-props(fr, L, th: th))
  if fr.comment != "" { par([Примечание. #fr.comment]) }
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

Карта сигналов «#doc.title» описывает обмен по шинам: шин~— #doc.stats.buses,
кадров~— #doc.stats.frames, сигналов~— #doc.stats.signals.

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

#show <appendix-1>: it => block(above: 0pt, below: 1em, {
  align(right, text(weight: "bold")[ПРИЛОЖЕНИЕ 1])
  align(center, text(weight: "bold")[ИСТОРИЯ ВЕРСИЙ КАРТЫ])
})

#if doc.history.len() > 0 {
  pagebreak(weak: true)
  [#heading(level: 1, numbering: none)[Приложение 1. История версий карты] <appendix-1>]
  gost-table([История версий карты], history-table(doc, L, th: th))
}

// ---------------------------------------------------------------- лист регистрации изменений

#pagebreak(weak: true)
#heading(level: 1, numbering: none)[Лист регистрации изменений]
#gost-change-register(rows: 21)
