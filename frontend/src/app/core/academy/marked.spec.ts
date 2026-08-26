import { marked } from './marked';

const mention = (slug: string, name: string, start: number, end: number) => ({
  slug,
  name,
  start,
  end,
});

describe('marked', () => {
  it('leaves an instruction that names nothing in one piece', () => {
    expect(marked('Put it on a plate.', [])).toEqual([
      { text: 'Put it on a plate.', slug: null, name: null },
    ]);
  });

  it('cuts the words that link out of the words that do not', () => {
    expect(marked('Gently fold in the whites.', [mention('fold', 'fold', 0, 11)])).toEqual([
      { text: 'Gently fold', slug: 'fold', name: 'fold' },
      { text: ' in the whites.', slug: null, name: null },
    ]);
  });

  it('keeps the text either side of a mention in the middle', () => {
    expect(marked('Now blanch them.', [mention('blanch', 'blanch', 4, 10)])).toEqual([
      { text: 'Now ', slug: null, name: null },
      { text: 'blanch', slug: 'blanch', name: 'blanch' },
      { text: ' them.', slug: null, name: null },
    ]);
  });

  it('handles two mentions in one step', () => {
    const text = 'Blanch, then sauté.';
    const pieces = marked(text, [
      mention('blanch', 'blanch', 0, 6),
      mention('saute', 'sauté', 13, 18),
    ]);
    expect(pieces.filter((one) => one.slug).map((one) => one.slug)).toEqual(['blanch', 'saute']);
  });

  it('never loses or duplicates a character', () => {
    // The property that matters: a cook reads the instruction, not our reassembly of it.
    const text = 'Fold in the whites, then blanch the beans.';
    const pieces = marked(text, [
      mention('fold', 'fold', 0, 7),
      mention('blanch', 'blanch', 25, 31),
    ]);
    expect(pieces.map((one) => one.text).join('')).toBe(text);
  });

  it('handles a mention that runs to the end', () => {
    const text = 'Now blanch';
    const pieces = marked(text, [mention('blanch', 'blanch', 4, 10)]);
    expect(pieces.map((one) => one.text).join('')).toBe(text);
  });
});
