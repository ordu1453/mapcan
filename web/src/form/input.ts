// Text of a form field ⇄ value in the YAML. Shared by the web editor and the VS Code form.

import { t } from "../i18n";
import type { FieldType } from "./spec";

export class ParseError extends Error {}

// An integer: decimal or 0x…; "1.5", "1e3" and numbers beyond JavaScript's precision are not accepted
const INT_RE = /^[-+]?(0x[0-9a-f]+|[0-9]+)$/i;

/** Parse an integer; ParseError if the text is not an integer or is too large. */
export function parseInteger(raw: string): number {
  const s = raw.trim();
  const m = INT_RE.exec(s);
  const v = m ? (/0x/i.test(s) ? (s.startsWith("-") ? -1 : 1) * parseInt(m[1].slice(2), 16) : Number(s.replace(/^\+/, ""))) : NaN;
  if (!Number.isSafeInteger(v)) throw new ParseError(t("“{raw}” is not an integer", { raw }));
  return v;
}

/** Text of a field → value for the YAML (null removes the key); ParseError on invalid input. */
export function parseInput(type: FieldType, raw: string): unknown {
  const s = raw.trim();
  if (s === "") return null;
  switch (type) {
    case "int": {
      return parseInteger(s);
    }
    case "hex": {
      // As strict as an integer: "0x12 34" or "0x1G" is an error, not 0x12 or 1 (an ID must not change silently)
      const v = /^(0x[0-9a-f]+|[0-9]+)$/i.test(s) ? parseInteger(s) : NaN;
      if (!Number.isSafeInteger(v)) throw new ParseError(t("“{raw}”: expected a number, such as 0x1A or 26", { raw }));
      return v;
    }
    case "float": {
      const v = Number(s.replace(",", "."));
      if (!Number.isFinite(v)) throw new ParseError(t("“{raw}” is not a number", { raw }));
      return v;
    }
    case "strlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean);
      return parts.length ? parts : null;
    }
    case "rawlist": {
      // Numbers and ranges "lo..hi"; one item is written as itself, several as a list
      const parts = s.split(/[\s,;]+/).filter(Boolean).map((x): number | string => {
        const range = /^(.+?)\.\.(.+)$/.exec(x);
        if (!range) return parseInteger(x);
        const [lo, hi] = [parseInteger(range[1]), parseInteger(range[2])];
        if (lo > hi) throw new ParseError(t("“{raw}”: a range goes from the lower bound to the upper one", { raw: x }));
        return `${range[1]}..${range[2]}`;
      });
      return parts.length === 1 ? parts[0] : parts;
    }
    case "intlist": {
      // One value is written as a number, several as a list
      const parts = s.split(/[\s,;]+/).filter(Boolean).map((x) => (INT_RE.test(x) ? Number(x.replace(/^\+/, "")) : NaN));
      if (parts.some((x) => !Number.isSafeInteger(x))) throw new ParseError(t("“{raw}”: expected a list of integers", { raw }));
      return parts.length === 1 ? parts[0] : parts;
    }
    default:
      return s;
  }
}

const hex = (v: number) => "0x" + v.toString(16).toUpperCase().padStart(2, "0");

/** Value from the YAML → text of a field. */
export function formatValue(type: FieldType, v: unknown): string {
  if (v === null || v === undefined) return "";
  if (type === "hex" && typeof v === "number") return hex(v);
  if (type === "rawlist") {
    // Raw values are codes: shown in hex, as the YAML writes them (a negative value of a signed signal as it is)
    const raw = (x: unknown) => (typeof x === "number" && x >= 0 ? hex(x) : String(x));
    const items = (x: unknown) => (Array.isArray(x) ? x.map(raw).join(", ") : raw(x));
    // Values by meaning: edited in the YAML
    if (typeof v === "object" && !Array.isArray(v)) {
      return Object.entries(v as Record<string, unknown>).filter(([, x]) => x != null)
        .map(([k, x]) => `${k}: ${items(x)}`).join("; ");
    }
    return items(v);
  }
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

/** Value of a select option → value for the YAML: "" removes the key, "true"/"false" of a yes/no select are booleans. */
export function selectValue(raw: string, numeric = false): unknown {
  if (raw === "") return null;
  if (numeric) return Number(raw);
  // A yes/no select (brs): empty is the default, so it cannot be a checkbox
  return raw === "true" || raw === "false" ? raw === "true" : raw;
}
