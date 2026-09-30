export interface SourceStamp {
  frameKey?: string;
  sourcePts: number;
  streamId: string;
}

const MARKER = 'b60519ab079c4e199428f40aef3c91ec';

/** Read our unregistered SEI without modifying the encoded H.264 frame. */
export function readSourceStamp(data: ArrayBuffer): SourceStamp | undefined {
  const bytes = new Uint8Array(data);
  const starts: Array<{ end: number; start: number }> = [];
  for (let i = 0; i < bytes.length - 3; i++) {
    if (
      bytes[i] === 0 &&
      bytes[i + 1] === 0 &&
      (bytes[i + 2] === 1 || (bytes[i + 2] === 0 && bytes[i + 3] === 1))
    ) {
      if (starts.length > 0) starts.at(-1)!.end = i;
      const start = i + (bytes[i + 2] === 1 ? 3 : 4);
      starts.push({ start, end: bytes.length });
      i = start - 1;
    }
  }
  // Some receivers expose length-prefixed NAL units instead of Annex B.
  if (starts.length === 0) {
    const view = new DataView(data);
    for (let i = 0; i + 4 <= bytes.length; ) {
      const length = view.getUint32(i);
      i += 4;
      if (!length || i + length > bytes.length) return;
      starts.push({ start: i, end: i + length });
      i += length;
    }
  }
  for (const nal of starts) {
    if ((bytes[nal.start]! & 31) !== 6) continue;
    const rbsp: number[] = [];
    for (let i = nal.start + 1; i < nal.end; i++) {
      if (bytes[i] === 3 && bytes[i - 1] === 0 && bytes[i - 2] === 0) continue;
      rbsp.push(bytes[i]!);
    }
    for (let i = 0; i < rbsp.length; ) {
      let type = 0;
      let size = 0;
      while (rbsp[i] === 255) {
        type += 255;
        i++;
      }
      if (i >= rbsp.length) break;
      type += rbsp[i++]!;
      while (rbsp[i] === 255) {
        size += 255;
        i++;
      }
      if (i >= rbsp.length) break;
      size += rbsp[i++]!;
      if (i + size > rbsp.length) break;
      if (type === 5 && (size === 40 || size === 56)) {
        const hex = (values: number[]) =>
          values.map((value) => value.toString(16).padStart(2, '0')).join('');
        if (hex(rbsp.slice(i, i + 16)) === MARKER) {
          const id = hex(rbsp.slice(i + 16, i + 32));
          const sourcePts = rbsp
            .slice(i + 32, i + 40)
            .reduce((value, byte) => value * 256 + byte, 0);
          if (!Number.isSafeInteger(sourcePts)) return;
          return {
            frameKey: size === 56 ? hex(rbsp.slice(i + 40, i + 56)) : undefined,
            sourcePts,
            streamId: `${id.slice(0, 8)}-${id.slice(8, 12)}-${id.slice(12, 16)}-${id.slice(16, 20)}-${id.slice(20)}`,
          };
        }
      }
      i += size;
    }
  }
}
