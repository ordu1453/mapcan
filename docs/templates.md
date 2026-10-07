# PDF templates and GOST formatting

PDF documents are built by the bundled [Typst](https://typst.app) compiler from one of the
built-in templates:

| Template | Standard | Contents |
|---|---|---|
| `mapcan` (default) | — (standard layout) | Colored bit diagrams, headers and footers, free-form title page |
| `gost-2.105` | ESKD: GOST 2.105, 2.104, 2.503 | Drawing frame (20 mm binding margin, 5 mm elsewhere); title block in form 2 on the first sheet and form 2a on the following ones; additional columns 19–25 in the left margin; title page with "СОГЛАСОВАНО" / "УТВЕРЖДАЮ" approval blocks; table of contents; numbered sections ("1", "1.1"); captioned tables ("Таблица N — …"); appendix; change registration sheet |

The ESKD template is always produced in Russian: the document language of the map or the one
chosen at export is ignored for it. The `mapcan` template follows the map's `document.language`
or the language chosen at export (`--lang en`).

## Choosing a template

```sh
mapcan template --list                                   # list built-in templates
mapcan export pdf my-map.yaml --template gost-2.105      # built-in template by name
mapcan build my-map.yaml --pdf-template mapcan --pdf-template gost-2.105   # several PDFs in CI
```

In the web editor, open the PDF preview from the **Export** menu and pick the template there; the
↓ button next to the format downloads the PDF straight away. The editor remembers your choice.

## Document details

The title block, title page and approval sheets are filled in from `document`. Every field is
optional: empty boxes stay blank and can be filled in by hand.

```yaml
document:
  title: Product signal map
  version: 1.0.0
  organization: Example LLC
  logo: logo.png                     # relative to the map file (PNG, JPG, SVG, GIF, WEBP)
  designation: ABCD.468332.001 D1    # document designation (ESKD)
  litera: O1                         # letter (ESKD "Лит.")
  city: Moscow                       # city on the title page
  signatures:                        # ESKD title block, approval sheet, list of contributors
    developed: Ivanov                # Разраб. (developed by)
    checked: Petrov                  # Пров. (checked by)
    tech_control: Sidorov            # Т. контр. (technical control)
    norm_control: Kuznetsova         # Н. контр. (standards control)
    approved: Smirnov                # Утв. (approved by)
  approve:                           # "УТВЕРЖДАЮ" (approved) block on the title page
    position: Chief Designer
    name: A. A. Smirnov
  agree:                             # "СОГЛАСОВАНО" (agreed) blocks, any number
    - position: Head of Department
      name: B. B. Orlov
```

In the web editor, the same fields are in the document properties, on the
**Layout and document details** card.

Where each field appears:

| Field | `mapcan` | ESKD `gost-2.105` |
|---|---|---|
| `logo` | title page, header | title page, title block box 9 |
| `organization` | title page | title page, box 9 |
| `designation` | title page | title block box 2, title page |
| `litera` | — | "Лит." box |
| `signatures` | — | "Разраб.", "Пров.", "Т. контр.", "Н. контр.", "Утв." boxes; signatures on the title page |
| `approve`, `agree` | — | title page |
| `city` | — | title page |

## Logo

* **File format:** PNG, JPG, GIF, WEBP or SVG. The path in `document.logo` is relative to the map
  file; an absolute path also works.
* **Web editor:** **Upload…** saves the file next to the map as `<map name>-logo.<ext>` and sets
  `document.logo`.
* **Where it appears:** in PDF (see the table above), in HTML (embedded in the file) and on the
  Excel "Summary" sheet. Excel does not support SVG, so use PNG or JPG if you need the logo there.
* **Validation:** a missing file produces the `logo-missing` warning; an unsupported format is the
  `logo-format` error.

## Fonts

PT Sans and PT Serif (SIL Open Font License) are bundled, so the PDF looks the same on every
machine. The ESKD title block uses "GOST type A" if it is installed on the system and falls back to
PT Sans otherwise. Additional fonts are loaded with `--font-path DIR`.

## Custom templates

To apply a corporate layout, copy a built-in template and edit it:

```sh
mapcan template pdf --name gost-2.105 -o corp/corp.typ   # template copy + corp/lib.typ
# edit corp/corp.typ: title block boxes, fonts, logo, extra sheets
mapcan export pdf my-map.yaml --template corp/corp.typ
```

`lib.typ` holds the shared building blocks: the bit diagram, signal tables, addressing, the change
registration sheet and the binding-margin columns. The template receives the map data as
`json(bytes(sys.inputs.data))`; its structure is defined in
[`src/mapcan/docmodel.py`](../src/mapcan/docmodel.py).
