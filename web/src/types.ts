// Types of the /api/state response (see src/mapcan/web/session.py).

import type { Path } from "@mapcan/forms";

export type { Op, Path, PathEl } from "@mapcan/forms";

export type Level = "error" | "warning" | "info";

export interface Diagnostic {
  level: Level;
  code: string;
  message: string;
  file: string | null;
  line: number | null;
  column: number | null;
  path: string;
  node: Path;
  /** A message about an included file: its place in that file (relative to the map), for its YAML tab. */
  part?: { file: string; line: number | null; column: number | null };
}

export interface ResolvedFlag {
  name: string;
  bit: number;
  bit_length: number;
  /** The field is the frame's multiplexer selector (#149). */
  multiplexer: boolean;
  occupied: number[];
  values: ResolvedValue[];
}

export interface ResolvedValue {
  value: number;
  name: string;
}

export interface ResolvedSignal {
  index: number | null;
  path: Path;
  name: string;
  encoding: string;
  start_bit: number;
  bit_length: number;
  byte_order: "little_endian" | "big_endian";
  signed: boolean;
  multiplexer: boolean;
  mux: number[] | null;
  occupied: number[];
  flags: ResolvedFlag[];
  values: ResolvedValue[];
  synthetic: boolean;
}

export interface ResolvedFrame {
  path: Path;
  name: string;
  can_id: number | null;
  extended: boolean;
  length: number;
  type: string;
  direction: string | null;
  device: string | null;
  /** Sending device (the owner of a TX frame or sender); null: the sender is outside the map. */
  sender: string | null;
  /** Receiving devices: receivers and the owner of an RX frame. */
  receivers: string[];
  signals: ResolvedSignal[];
}

export interface Included {
  path: Path;
  file: string;
  /** The node's path in its file: the second device of a bus may be the first of the file. */
  local?: Path;
}

export interface State {
  file: string;
  path: string;
  version: number;
  dirty: boolean;
  /** Included files with unsaved edits (relative to the map): Save writes them too. */
  dirty_files?: string[];
  /** The included file asked for, when its map was opened in its place (relative to the map). */
  opened_part?: string | null;
  readonly: boolean;
  can_undo: boolean;
  can_redo: boolean;
  disk_changed: boolean;
  text: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any | null;
  /** Computed from the map: frames, and the estimated load of each bus ("≥" when not every frame is counted). */
  resolved: { frames: ResolvedFrame[]; buses?: { path: Path; load: string; note?: string }[]; language: string } | null;
  /** Buses together with the included files (include); null if nothing is included. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  included_buses: any[] | null;
  /** Nodes added by included files, and their file (relative to the map). */
  included: Included[];
  /** Texts of the included files (relative to the map), for the YAML tab. */
  parts?: Record<string, string>;
  diagnostics: Diagnostic[];
  palette: string[];
  /** Reference of units: pairs of symbols [ru, en]. */
  units: Array<[string, string]>;
  session_id: number;
}

export interface DiffResult {
  old_version: string;
  new_version: string;
  label: string;
  lines: string[];
  changes: Array<Record<string, unknown>>;
}

export interface UserProfile {
  name: string;
  github: string | null;
  github_url: string | null;
}

export interface RecentFile {
  path: string;
  name: string;
  dir: string;
  exists: boolean;
}

export interface Meta {
  version: string;
  user: UserProfile;
  recent: RecentFile[];
  cwd: string;
  home: string;
  readonly: boolean;
  templates: Record<string, string>;
  examples: { name: string; title: string }[];
  open: boolean;
  file: string | null;
  session_id: number;
  /** How mapcan runs: the app window or mapcan serve (for a bug report). */
  mode?: "app" | "serve";
  /** The server's system and Python (for a bug report). */
  system?: string;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  newer: boolean;
  url: string;
  installer: string | null;
}

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  mtime: number;
}

export interface FsList {
  dir: string;
  parent: string | null;
  entries: FsEntry[];
  drives: string[];
  sep: string;
}

export interface SessionResult {
  meta: Meta;
  state: State | null;
}

export interface PdfTemplate {
  name: string;
  title: string;
  description: string;
  lang: string | null;           // the language is fixed by the template (GOST: Russian only)
}

export interface GitRevs {
  available: boolean;
  /** Why comparing with git is not available */
  reason?: "no-git" | "no-repo" | "untracked";
  /** Tags that have the map file (newest first) */
  tags: string[];
  /** All tags of the repository, so that a taken name is not offered */
  all_tags: string[];
  /** Branches with the map file other than the current one; upstream first */
  branches: string[];
  commits: GitCommit[];
}

export interface GitCommit {
  rev: string;
  subject: string;
  date: string;
  author: string;
  tags: string[];
}

/** Git state of the map file (the Git menu) */
/** Draft of a version release (GET /api/git/release). */
export interface ReleaseDraft {
  version: string;
  /** Changes since the previous release, or from the history entry added already (recorded). */
  changes: string[];
  /** The entry of this version is already in the revision history: no new one is added. */
  recorded: boolean;
  /** What the map was compared with: the tag of the previous release or HEAD; null if the map is not in git yet. */
  base: string | null;
}

export interface GitStatus {
  available: boolean;
  reason?: "no-git" | "no-repo" | "error";
  error?: string;
  branch?: string | null;
  upstream?: string | null;
  ahead?: number;
  behind?: number;
  /** State of the map and its logo; ignored: the map is excluded by .gitignore */
  file?: "clean" | "modified" | "untracked" | "ignored";
  last?: { rev: string; subject: string; date: string } | null;
  /** The remote repository (origin or the first in the list) */
  remote?: string | null;
  /** Its address for the browser, if known (https, or an ssh address like git@host:owner/repo) */
  remote_url?: string | null;
}
