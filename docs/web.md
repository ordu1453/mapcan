# Web editor (`mapcan app`, `mapcan serve`)

The web editor is a full map editor: a map tree, property forms, an interactive frame bit layout,
live validation, document preview and export, and version comparison. It saves YAML **with
comments, key order and formatting intact**, so `git diff` shows only the lines that actually
changed.

## Desktop app

On a workstation, run the editor as an application: use the mapcan shortcut created by the
installer or run `mapcan app` (requires `mapcan[desktop]`; without it the editor opens in the
browser):

```sh
mapcan app                               # own window, start screen
mapcan app my-map.yaml                   # open a map right away
mapcan app --browser                     # the same in a browser tab
```

* **Single instance.** Launching mapcan again or double-clicking a `.yaml` file does not start a
  second editor: the file opens in the running window, which is brought to the front. If the
  current map has unsaved changes, the editor asks what to do with them first.
* **Port.** 8765, or any free port if it is taken. The window opens once the server is ready.
* **Closing the window** with unsaved changes asks for confirmation.
* **Updates.** Once a day the editor checks the
  [latest release](https://github.com/ordu1453/mapcan/releases/latest) and shows a banner with a
  link to the installer. **Hide** dismisses it until the next version. To turn the check off, set
  the environment variable `MAPCAN_NO_UPDATE_CHECK=1`.
* **Files.** Window settings, the theme and the selected PDF template are stored in
  `~/.mapcan/webview/`; the desktop app's error log is `~/.mapcan/mapcan.log`.

## Browser mode

`mapcan serve` runs the same editor in a browser tab, which is convenient on a server and for
frontend development:

```sh
mapcan serve                             # start screen: create or open a map
mapcan serve my-map.yaml                 # open a map right away (http://127.0.0.1:8765/)
mapcan serve maps/                       # start screen with maps/ as the working folder
mapcan serve my-map.yaml --readonly      # view only
mapcan serve my-map.yaml --port 9000 --no-browser
```

There is no need to restart the server to work on another map: **File → New map… / Open… /
Save as… / Close map** all work in the browser. The file dialog can browse any folder or drive,
accepts a typed path and lists recent files. If the current map has unsaved changes, the editor
offers to save them before switching.

The start screen also lists the bundled examples: pick one, choose where to save a copy, and it
opens. The mapcan version is shown in the top bar next to the title and on the start screen.

### Security

The editor is meant for a single user on their own machine. By default it listens on `127.0.0.1`
only and has no authentication. With `--host 0.0.0.0` it becomes reachable from the network, and
mapcan prints a warning at startup.

## Author profile

On first launch the editor asks for your **name** and, optionally, your **GitHub** user name or
profile link. The profile is stored locally in `~/.mapcan/config.json` (override the folder with
the `MAPCAN_CONFIG_DIR` environment variable), together with the list of recent files. To change
it, click the button with your initials in the top-right corner.

The profile records who made which changes:

* **New map** fills in `document.author` and creates the first revision history entry in your
  name.
* **Git → Compare versions… → Add to history** signs the entry with your name and GitHub account:

  ```yaml
  history:
    - version: 1.0.1
      date: 2026-10-06
      author: Jane Smith
      github: jsmith
      changes:
        - "0x196 imd_state: added signal reserve (bits 24–31)"
  ```

* The author, linked to their GitHub profile, appears on the Excel "Changes" sheet, in the PDF
  appendix, and in Markdown and HTML.

## Interface

| Area | What it does |
|---|---|
| **Tree** (left) | Document → buses → devices → frames → signals → flags and SDO exchanges. Frames show their CAN ID, signals the bits they occupy. A dot marks an error or warning in the node itself, a ring marks one in its children. |
| **Search** | By name, description or CAN ID (`0x196` or `406`). With several words, all of them must match. |
| **Properties** | The form for the selected node. A value is applied on Enter or when the field loses focus. Validation messages appear under the field. `en` adds an English translation of a text field. The **?** next to a field label explains the setting, why it matters and which values are allowed (shown on hover; click to pin, Esc to close). |
| **Frame layout** | The bit map of the frame: rows are bytes, columns are bits 7…0. Cells are labelled with signal names and the flags of bit fields. |
| **Frames** | The frame list on a bus or device page; ✕ in a row deletes the frame. **+ Frame** adds a frame to the list without changing the selected node. |
| **Receives** | On a device page: the bus frames the device receives (its own RX frames and other devices' frames that list it as a receiver), with their senders. Below it, **Transmits frames of other devices** lists the frames it sends on behalf of other devices (`sender`). Both are computed from the frames; click a row to jump to the frame. On a frame page, **Sender** is picked from the bus devices and **Receivers** are toggled on and off; renaming a device updates both. |
| **Values / Flags** | Enum and bit field tables: value (decimal or `0x…`), name, description. **+ Flag** adds a row without leaving the signal page. |
| **Validation** (bottom) | The same rules as `mapcan validate`. Click a message to jump to the node (or, on the YAML tab, to the line). While the YAML tab holds text that is not applied yet (for example, with a syntax error), the panel lists the messages for that text and marks them **YAML text not applied**. |
| **YAML** | Edit the whole file as text. The text is validated as you type: lines with problems are marked in the gutter (hover a line number to read the message), and the first syntax error is shown in the YAML toolbar; click it to jump to its line. Once the text parses, it is applied automatically after a short pause, so the tree and the editor follow your typing; a whole run of typing is one undo step. Switching to the editor applies what is left (it stays on the YAML tab if there is a syntax error). Renaming a device in the text also updates `sender` and `receivers` of the bus frames, as renaming in the form does. Tab and Shift+Tab indent and outdent the selected lines, Enter keeps the indentation (one level deeper after `key:`), Backspace after spaces goes back to the previous tab stop (2 spaces); press Esc first to move focus with Tab. Ctrl+Enter applies the edit at once. |
| **Export** | Documents (PDF, HTML, Markdown, Excel) and development formats (DBC, C, Python), generated from the current state, including unsaved changes. Clicking a document opens a preview; for PDF, the template is chosen there: `mapcan` or ESKD (see [templates.md](templates.md)). ↓ on the right downloads the file directly. The document language (English or Russian; the map's language by default) is chosen in the menu and in the preview. The ESKD template is always in Russian. |
| **Layout and document details** | In the document properties: logo (file upload), designation, letter, organization, city, title block signatures, approval blocks. |
| **Git → Compare versions…** | Diffs the current map against a git revision (HEAD, a tag or a commit) or an uploaded file: changes to frames, signals, values and flags. **Add to history** writes the changelog into `document.history` and bumps the version. |
| **Git** | The version menu for the map. It starts with **Compare versions…** (see above), followed by the branch, the state of the map file and the number of unpushed commits. **Commit…** commits only the map and its logo (optionally tagging the version), **Create tag…** tags the last commit, **Pull changes** runs `git pull --ff-only` and reloads the map, and **Push to &lt;remote&gt;** pushes (the first push sets the upstream). If the folder is not a repository, the menu offers **Create a repository here**; if there is no remote, **Publish on GitHub…** runs `gh repo create --source . --push` through [GitHub CLI](https://cli.github.com) (requires `gh auth login`). For github.com, push and pull use the `gh` credentials when `gh` is installed. Without git, or in read-only mode, only the comparison is available. |

### Bit layout

* **New signal:** drag across free bits. The signal gets a little-endian position from the lowest
  selected bit to the highest.
* **Move:** drag a signal.
* **Resize:** a selected little-endian signal has handles on its lowest and highest bits; drag
  them. Big-endian signals can be moved; set their length in the form.
* **Overlaps** are highlighted with red hatching while you drag. Multiplexed frames have a
  selector value switch; **All** shows every signal set at once (mutually exclusive signals on the
  same bits do not count as overlaps).
* The position is written in the most readable form: `byte`/`bit`/`byte_length` if the signal is
  byte-aligned, `start_bit`/`bit_length` otherwise. A signal that was written with `start_bit`
  keeps that form.

### Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+S | Save |
| Ctrl+Shift+S | Save as |
| Ctrl+O | Open |
| Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) | Undo / redo (outside input fields) |
| Delete | Delete the selected tree node (no confirmation; undo with Ctrl+Z; outside input fields) |
| Ctrl+Enter | Apply the edit on the YAML tab |
| Esc | Close a dialog, cancel a drag |

## How formatting is preserved

The browser never sends the whole YAML file. Each action is an operation on a path in the document
(`set`, `insert`, `remove`, `move`, `rename_key`, `set_layout`). The server applies it to the
ruamel.yaml round-trip tree and then carries the changes over to the original text line by line.
Untouched fragments, including comments, blank lines, quoting, hexadecimal numbers and manual line
breaks inside `{...}` flow mappings, stay byte-for-byte identical. Line endings (LF/CRLF) are
preserved.

If the file is changed by another program (for example in VS Code or by `git pull`), a banner
offers to **Reload from disk** or **Keep my version**. Saving over external changes requires
confirmation. The **⟳** button next to the file name reloads the file at any time (it asks first
if there are unsaved changes, which are lost along with the undo history).

## HTTP API

The UI runs on top of an HTTP API that can also be used from scripts. Interactive documentation is
available at `http://127.0.0.1:8765/api/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | mapcan version, profile, recent files, whether a map is open |
| GET/PUT | `/api/user` | Author profile `{name, github}` |
| GET | `/api/update` | Newer version on GitHub Releases: `{current, latest, newer, url, installer}` (`mapcan app` and local `serve` only) |
| POST | `/api/instance/activate` | `{token, path}`: a second launch hands the file to the running instance (the token is in `~/.mapcan/instance.json`) |
| GET | `/api/fs/list?dir=` | Folders and YAML files for the file dialog |
| POST | `/api/file/open`, `/api/file/new`, `/api/file/example`, `/api/file/save_as`, `/api/file/close` | File operations; `409 unsaved` means there are unsaved changes (pass `force: true` to proceed) |
| GET | `/api/state` | Text, data, computed layout and diagnostics |
| POST | `/api/ops` | `{"ops": [...]}`: apply operations atomically |
| POST | `/api/text` | Replace the YAML text |
| POST | `/api/check` | `{"text": ...}`: validate text without applying it; returns `{diagnostics}` |
| POST | `/api/undo`, `/api/redo` | Edit history |
| POST | `/api/save` | `{"force": false}`; `409` means the file changed on disk |
| POST | `/api/reload` | Reload the file from disk |
| GET | `/api/export/{xlsx,pdf,md,html,dbc,c,py}` | Export the current state (`?download=true`, `?lang=ru\|en`, for PDF `?template=gost-2.105`; the ESKD template is always `ru`) |
| GET | `/api/templates` | Built-in PDF templates |
| GET/POST | `/api/logo` | Get or upload the map logo (saved next to the map) |
| GET | `/api/git/revs` | Tags and commits that contain the map file |
| POST | `/api/diff/git`, `/api/diff/upload` | Compare with a git revision or an uploaded file |
| GET | `/api/git/status` | Branch, upstream, remote, divergence, file state, last commit |
| POST | `/api/git/init`, `/api/git/commit`, `/api/git/tag`, `/api/git/push`, `/api/git/pull` | Git operations (the map must be saved) |
| GET/POST | `/api/gh/status`, `/api/gh/create` | GitHub CLI login status; create a GitHub repository and push |
| WS | `/ws` | `state` events (an edit in another tab) and `file-changed` events |

## Frontend development

The sources are in [web/](../web) (Vue 3 + TypeScript + Vite). The built bundle lives in
`src/mapcan/web/static/` and ships with the package, so users do not need Node.js.

```sh
mapcan serve my-map.yaml --no-browser     # API on :8765
cd web
npm ci
npm run dev                               # http://localhost:5173 with hot reload
npm run build                             # type check + build into src/mapcan/web/static
```

UI strings are written in Russian in the source and translated through
[web/src/locale/en.json](../web/src/locale/en.json); `tests/test_i18n.py` fails if a string has no
translation or a translation is no longer used.
After changing `web/src`, rebuild the bundle and commit `src/mapcan/web/static`: CI checks that
the bundle matches the sources.
