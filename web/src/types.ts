// Типы ответа /api/state (см. src/canmap/web/session.py).

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

export interface GitRevs {
  available: boolean;
  tags: string[];
  commits: Array<{ rev: string; subject: string; date: string }>;
}
