import { MentionView } from '@api';

/** One piece of a step: either plain words, or words that name a page. */
export interface Piece {
  readonly text: string;
  readonly slug: string | null;
  readonly name: string | null;
}

/**
 * Split an instruction into the words that link and the words that do not.
 *
 * The server sends offsets rather than marked-up text (ADR-040): what is stored is the
 * instruction, and the marks are read out of its own words when it is shown. Cutting the
 * string here rather than building HTML is what keeps the instruction the cook's own text
 * — nothing is escaped, injected or re-encoded on the way to the screen.
 *
 * Mentions arrive in reading order and never overlap, so one pass is enough.
 */
export function marked(instruction: string, mentions: readonly MentionView[] | undefined): Piece[] {
  const pieces: Piece[] = [];
  let at = 0;
  for (const mention of mentions ?? []) {
    if (mention.start > at) {
      pieces.push({ text: instruction.slice(at, mention.start), slug: null, name: null });
    }
    pieces.push({
      text: instruction.slice(mention.start, mention.end),
      slug: mention.slug,
      name: mention.name,
    });
    at = mention.end;
  }
  if (at < instruction.length) {
    pieces.push({ text: instruction.slice(at), slug: null, name: null });
  }
  return pieces;
}
