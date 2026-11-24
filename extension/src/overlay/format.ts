/**
 * Turns an assistant answer (plain text with "- " bullets and **bold**) into claim + proof blocks:
 * the first line is the claim; bullet lines become proof rows ("label: value" splits into two columns,
 * and "label: value | detail" adds a muted detail line under the row).
 */

export type Inline = { text: string; strong: boolean }[];

export type Row = { label: Inline; value: Inline | null; detail?: Inline };

export type Block =
  | { kind: "claim"; content: Inline }
  | { kind: "para"; content: Inline }
  | { kind: "rows"; rows: Row[] };

/** A figure that signals a problem: a percentage above 100, or words naming an over/overdue state. */
export function isAlert(content: Inline | null | undefined): boolean {
  const text = (content ?? []).map((p) => p.text).join("");
  return /\b(over-allocated|overdue|past due)\b/i.test(text) || [...text.matchAll(/(\d+)%/g)].some((m) => Number(m[1]) > 100);
}

export function inline(text: string): Inline {
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**") ? { text: part.slice(2, -2), strong: true } : { text: part, strong: false });
}

export function toBlocks(answer: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of answer.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("- ")) {
      const [body, detail] = line.slice(2).split(" | ", 2);
      const cut = body.indexOf(": ");
      const row: Row = cut > 0 ? { label: inline(body.slice(0, cut)), value: inline(body.slice(cut + 2)) } : { label: inline(body), value: null };
      if (detail) row.detail = inline(detail);
      const last = blocks.at(-1);
      if (last?.kind === "rows") last.rows.push(row);
      else blocks.push({ kind: "rows", rows: [row] });
    } else {
      blocks.push({ kind: blocks.length === 0 ? "claim" : "para", content: inline(line) });
    }
  }
  return blocks;
}
