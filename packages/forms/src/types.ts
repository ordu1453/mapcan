// What a form gives back: edits of the YAML document, in the operations of the editors' API
// (src/mapcan/web/yamlops.py).

export type PathEl = string | number;
export type Path = PathEl[];

export type Op =
  | { op: "set"; path: Path; value: unknown }
  | { op: "remove"; path: Path }
  | { op: "insert"; path: Path; value: unknown; index?: number }
  | { op: "move"; path: Path; to: number }
  | { op: "rename_key"; path: Path; new_key: string | number }
  | { op: "set_layout"; path: Path; start_bit: number; bit_length: number };
