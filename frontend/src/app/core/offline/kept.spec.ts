import { forgetKept, keep, kept } from './kept';

describe('what is kept for a lost connection', () => {
  beforeEach(() => localStorage.clear());

  it('gives back what was put in', () => {
    keep('cooking.7', { title: 'Shortbread' });
    expect(kept<{ title: string }>('cooking.7')).toEqual({ title: 'Shortbread' });
  });

  it('has nothing to say about something it was never given', () => {
    expect(kept('cooking.404')).toBeNull();
  });

  it('does not choke on something that is not ours', () => {
    // An older version, a half-written value, somebody else's key collision. None of
    // those should stop a cook reading their recipe.
    localStorage.setItem('quookly.kept.cooking.7', 'not json');
    expect(kept('cooking.7')).toBeNull();
  });

  it('forgets everything it kept, and nothing else', () => {
    // Signing in clears this. The next person at the tablet is not necessarily the last
    // one, and half a stranger's dinner is not something to leave lying about.
    keep('cooking.7', { title: 'Shortbread' });
    localStorage.setItem('quookly.session', 'a token');

    forgetKept();

    expect(kept('cooking.7')).toBeNull();
    expect(localStorage.getItem('quookly.session')).toBe('a token');
  });
});
