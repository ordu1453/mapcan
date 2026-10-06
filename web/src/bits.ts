// Раскладка бит — порт src/mapcan/bits.py (нумерация lsb0, start — позиция LSB).

export function occupiedBits(start: number, length: number, bigEndian: boolean): number[] {
  const out: number[] = [];
  let pos = start;
  let left = length;
  while (left > 0) {
    const byte = Math.floor(pos / 8);
    const shift = ((pos % 8) + 8) % 8;
    const n = Math.min(8 - shift, left);
    for (let k = 0; k < n; k++) out.push(byte * 8 + shift + k);
    left -= n;
    pos = bigEndian ? (byte - 1) * 8 : (byte + 1) * 8;
  }
  return out;
}

export function rangeLabel(a: number, b: number): string {
  return a === b ? String(a) : `${a}–${b}`;
}

export function hex(v: number | null | undefined, width = 3): string {
  if (v === null || v === undefined) return "—";
  return "0x" + v.toString(16).toUpperCase().padStart(width, "0");
}

/** Присутствуют ли два сигнала в кадре одновременно (с учётом мультиплексирования). */
export function coexist(a: number[] | null, b: number[] | null): boolean {
  if (a === null || b === null) return true;
  return a.some((v) => b.includes(v));
}
