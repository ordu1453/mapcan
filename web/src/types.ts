// Типы ответа /api/state (см. src/mapcan/web/session.py).

export type PathEl = string | number;
export type Path = PathEl[];

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
}

export interface ResolvedFlag {
  name: string;
  bit: number;
  bit_length: number;
  occupied: number[];
}

export interface ResolvedValue {
  value: number;
  name: string;
}

export interface ResolvedSignal {
  index: number | null;
  path: Path;
  name: string;
  kind: string;
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
  dlc: number;
  type: string;
  direction: string | null;
  device: string | null;
  signals: ResolvedSignal[];
}

export interface State {
  file: string;
  path: string;
  version: number;
  dirty: boolean;
  readonly: boolean;
  can_undo: boolean;
  can_redo: boolean;
  disk_changed: boolean;
  text: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any | null;
  resolved: { frames: ResolvedFrame[]; language: string } | null;
  diagnostics: Diagnostic[];
  palette: string[];
  /** Справочник единиц: пары обозначений [ru, en]. */
  units: Array<[string, string]>;
  session_id: number;
}

export type Op =
  | { op: "set"; path: Path; value: unknown }
  | { op: "remove"; path: Path }
  | { op: "insert"; path: Path; value: unknown; index?: number }
  | { op: "move"; path: Path; to: number }
  | { op: "rename_key"; path: Path; new_key: string | number }
  | { op: "set_layout"; path: Path; start_bit: number; bit_length: number };

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
  language: string;
  language_chosen: boolean;      // false — первый запуск, язык ещё не выбран
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
}

export interface GitRevs {
  available: boolean;
  /** Почему сравнение с git недоступно */
  reason?: "no-git" | "no-repo" | "untracked";
  tags: string[];
  commits: Array<{ rev: string; subject: string; date: string }>;
}

/** Состояние git для файла карты (меню Git) */
export interface GitStatus {
  available: boolean;
  reason?: "no-git" | "no-repo" | "error";
  error?: string;
  branch?: string | null;
  upstream?: string | null;
  ahead?: number;
  behind?: number;
  file?: "clean" | "modified" | "untracked";
  last?: { rev: string; subject: string; date: string } | null;
  /** Удалённый репозиторий (origin или первый из списка) */
  remote?: string | null;
}
