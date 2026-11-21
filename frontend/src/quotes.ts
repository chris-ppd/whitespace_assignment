export type QuoteSpan = { start: number; end: number }; // [start, end) in the raw text

/** Collapse runs of whitespace to single spaces, remembering where each
 *  collapsed character came from in the raw string. Mirrors the contract:
 *  docs/contracts.md, "Review output", quote rule. */
export function collapseWithMap(raw: string): { collapsed: string; map: number[] } {
  const chars: string[] = [];
  const map: number[] = [];
  let lastWasSpace = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (/\s/.test(ch)) {
      if (!lastWasSpace) {
        chars.push(' ');
        map.push(i);
        lastWasSpace = true;
      }
    } else {
      chars.push(ch);
      map.push(i);
      lastWasSpace = false;
    }
  }
  return { collapsed: chars.join(''), map };
}

/** First occurrence of `quote` in `raw` under the contract's collapse rule,
 *  as a raw-text span; null when absent or when quote is null/empty. */
export function findQuoteSpan(raw: string, quote: string | null): QuoteSpan | null {
  if (quote === null || quote.length === 0) return null;
  const { collapsed, map } = collapseWithMap(raw);
  const q = quote.replace(/\s+/g, ' ');
  const at = collapsed.indexOf(q);
  if (at === -1) return null;
  return { start: map[at], end: map[at + q.length - 1] + 1 };
}
