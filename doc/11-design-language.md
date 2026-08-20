# Design language

**Status: the token contract and shipped themes are Built; the component primitives arrive with
the screens that need them.**

Quookly exists because useful information gets buried in decoration. The interface has to hold
itself to that standard — and still be the thing someone shows a friend unprompted.

Those two goals are not in tension, but the way they are usually reconciled is wrong. Delight does
not come from ornament added on top of content. It comes from **content that is unusually well
served**: type you can read across a kitchen, quantities already in your units, the answer to the
question you were about to ask, sitting where you were about to look. That is the "ah, yes — that
makes sense" feeling, and it is the target.

## The feeling we are aiming for

A good cookbook, redesigned by someone who has actually cooked from it. Confident typography.
Generous space where it aids reading, tight where it aids scanning. Colour used sparingly and
meaningfully. Nothing moves unless the movement explains something.

**The anti-goal, stated plainly:** a recipe site. Hero images that push the ingredients below the
fold, a paragraph before every number, interface chrome competing with the content it frames. If a
screen could be mistaken for the thing this product replaces, it is wrong.

## Principles

**1. The content is the interface.** Chrome recedes; the recipe, the plan, the list *is* the page.
Navigation is available, not present. A screen's job is to make its content easy to act on, not to
be an experience of its own.

**2. Minimal but complete — through disclosure, not omission.** Show what is needed now; keep
everything else exactly one obvious gesture away. Hiding a capability is not minimalism, it is a
missing feature. Burying it three menus deep is worse than showing it.

**3. Density belongs to context, not to taste.** Browsing recipes wants a scannable list. Cooking
wants one step filling the screen, readable at arm's length. Same data, different density —
selected by what the cook is doing, never by a preference they have to find and set.

**4. Answer before asking.** If suitability, cost in time, or pantry coverage can be computed, show
it inline. Do not make someone apply a filter to learn something the system already knows.

**5. Say what happened.** Every action confirms, every failure explains, every wait is visible.
"Could not save" is a bug report; "no connection — this will send when you are back" is an
interface.

**6. Restraint is the aesthetic.** One accent colour doing real work beats five decorating. Where
the design should be striking, it is striking through type, proportion, and a single confident
colour — not through more elements.

**7. Nothing is colour alone.** Every state carries an icon or a word as well as a hue. This is an
accessibility requirement and, for dietary warnings, a safety one.

## Layout

The phone is the design target (NFR-11). Base styles are the narrow viewport; media queries only
ever add width.

| Breakpoint | Width | Shape |
| --- | --- | --- |
| base | from 320px | single column, actions within thumb reach |
| `md` | 640px | wider measure, two-column forms |
| `lg` | 1024px | persistent navigation, side-by-side detail |
| `xl` | 1440px | content capped; whitespace absorbs the rest |

Rules that follow:

- **Primary actions sit low**, within thumb reach, not in a top bar.
- **One row of permanent chrome.** The sticky bar carries navigation and nothing else.
  Anything chosen once and then left alone — language, theme — sits at the end of the page
  instead, where it costs no screen on every other visit.
- **Touch targets are at least 44px**, with at least 8px between them.
- **One column until the content genuinely needs two.** A second column that exists to fill space
  costs scanning speed.
- **Measure is capped at ~68 characters** for prose and step text. A step spanning a 27-inch
  monitor is unreadable.
- **The page body never scrolls horizontally.** Wide things scroll inside their own container.

## Typography

A recipe is a document, so type carries most of the design.

| Role | Use | Token |
| --- | --- | --- |
| Display | Recipe titles, screen headings, the moments that should land | `--font-display` |
| Body | Steps, descriptions, everything read at length | `--font-body` |
| Numeric | Quantities, timers, nutrition — tabular figures so columns align | `--font-numeric` |

The recipe page is where these rules are first tested against real content. Quantities sit in their
own aligned column so the list is *scanned* rather than read; timings and temperatures are chips
rather than sentences, because they were captured as fields; and the yield control is the only thing
on the page shaped like a control, because it is the only thing that is one.

**Tabular figures for every quantity.** Ingredient amounts and timers that jitter as digits change
look broken, and a column of quantities that does not align is harder to scan.

Sizes are a fluid scale from `--text-xs` to `--text-3xl` using `clamp()`, so the same tokens serve a
phone and a worktop tablet without a second set of rules.

**Fonts are self-hosted.** Quookly works offline (NFR-13) and runs on instances with no outbound
internet access; a font that arrives from a CDN is a font that sometimes does not arrive. Subset,
`woff2`, `font-display: swap`, with a real system fallback stack behind every face.

**Only the display face is vendored.** Fraunces (SIL OFL 1.1) at one weight, Latin subsets, ~67 kB
total, of which a browser fetches only the range it needs. Body text uses the platform's own UI
face: nothing to download, native rendering, and already the most legible thing on the device. The
character comes from the headings, which is where it should come from anyway.

## Colour

Colours are referenced by **role**, never by name or hex. Nothing in a component says "blue"; it
says `--primary`. This is what lets a theme be swapped wholesale without auditing every component,
and what makes contrast checkable at the token level rather than the screen level.

Every foreground token is paired with the surface it is intended for, so contrast is a property of
the pair rather than a hope. **Every pair must meet WCAG AA** — 4.5:1 for body text, 3:1 for large
text and meaningful non-text — *in every shipped theme*. A theme that fails this is a bug, not a
style choice.

This is **enforced, not asserted**: `just frontend contrast` checks all 56 pairs across the four
themes and runs as part of `just frontend check`. It reads `src/styles/themes.css` directly, so the
stylesheet stays the single source of truth. Colour tokens must be hex for that reason — a value the
checker cannot parse is reported rather than skipped.

## The token contract

Themes set these; components consume them and nothing else.

```
Surface     --surface  --surface-raised  --surface-sunken  --border  --border-strong  --overlay
Foreground  --on-surface  --on-surface-muted  --on-surface-subtle
Brand       --primary  --on-primary  --primary-hover  --accent  --on-accent
Status      --success  --warning  --danger  --info   (+ --on-* for each)
Type        --font-display  --font-body  --font-numeric
            --text-xs … --text-3xl   --leading-tight  --leading-normal  --leading-loose
Space       --space-1 … --space-8    (4px base, modular)
Shape       --radius-sm  --radius-md  --radius-lg  --radius-full
Depth       --shadow-1  --shadow-2  --shadow-3
Motion      --motion-fast  --motion-base  --motion-slow  --ease-standard  --ease-emphasised
Density     --density                 (1 normal, larger in cooking mode)
```

`--border` and `--border-strong` are separate on purpose. WCAG 1.4.11 requires 3:1 for the visible
**boundary of a control**, and requires nothing of a decorative divider. One token doing both jobs
means either dividers that shout or inputs whose edge cannot be seen. The split was forced by the
contrast check failing on the original single token — the check earning its place on its first run.

**A component that hardcodes a colour, a font, or a spacing value is a defect**, in the same way an
unmigrated model is. The token contract is the seam that makes theming work at all.

## Theming

Themes are **data, not code**: a set of custom-property values applied by a `data-theme` attribute
on the document root. Adding one is writing a block of values — no rebuild, no component changes,
and a self-hoster can add their own.

```css
:root { /* light: the default */ }
[data-theme='dark'] { /* only the values that differ */ }
```

Shipped themes, each with an intent rather than just a palette:

| Theme | Intent |
| --- | --- |
| **Light** | The default. Warm neutral, quiet, maximum legibility in a bright kitchen. |
| **Dark** | Evening cooking. Low glare without the muddy grey that makes text hard at distance. |
| **Playful** | Saturated accents, rounder shapes, more energetic motion. The same information, more character. |
| **Decorative** | Cookbook feel — a display serif, warmer paper surfaces, more ornamental rules. Still content-first. |

Selection follows `prefers-color-scheme` until the cook chooses, and the choice is remembered.
`prefers-reduced-motion` is honoured in every theme, including Playful; motion is a garnish and
comes off on request.

Density is **not** a theme. It is set by context — cooking mode raises `--density` — because a cook
should not have to discover a setting to be able to read a step from a metre away.

## Motion

Motion explains: where something came from, that a thing is loading, that an action landed.
Decorative animation is noise, and noise is the thing this product exists to remove.

- Transitions are 120–240ms. Longer feels sluggish on a phone.
- Entrances move a short distance; things do not fly across the screen.
- Nothing loops. A spinner that outlives its request is a bug.
- Under `prefers-reduced-motion`, transitions become instant — not merely faster.

## Components

**No component library.** Angular Material carries a strong visual identity that would fight the
one described here, it is heavy for something that must work offline on a phone, and we need
roughly a dozen primitives. See
[ADR-024](07-decisions.md#adr-024-own-component-primitives-on-cdk-behaviour).

Behaviour that is genuinely hard and genuinely solved — focus trapping, overlay positioning, live
region announcements — comes from `@angular/cdk`, which ships those without any styling. We supply
the appearance; the CDK supplies the parts that are easy to get subtly, inaccessibly wrong.

The primitive set, added as screens need them: button, input, select, checkbox and radio, form
field with label and error, card, list row, dialog, sheet, toast, tabs, badge, empty state,
skeleton.

Each primitive: one responsibility, tokens only, keyboard-operable, and a visible focus ring that
is never removed without a replacement.

## Accessibility

Non-negotiable, and mostly a consequence of the rest.

- **WCAG AA in every theme**, verified per token pair rather than per screen.
- **Never colour alone** — icon or text always. For dietary warnings this is a safety rule
  ([ADR-006](07-decisions.md#adr-006-allergen-determination-is-structural)), not a preference.
- **Visible focus** on every interactive element.
- **Real semantics**: a button is a `<button>`, a heading hierarchy is real, forms have labels.
- **Errors are announced**, associated with their field, and say what to do.
- **AXE clean**, checked as screens are built rather than retrofitted.

## Cooking mode

The one place the rules deliberately change, because the posture does: standing, hands busy or wet,
screen a metre away, glancing rather than reading.

- `--density` rises: larger type, larger targets, more space.
- One step fills the screen. No scrolling to find the current instruction.
- Timers use the numeric face at display size, legible across a kitchen.
- Controls sit low and are large enough for a knuckle.
- The screen stays awake (NFR-12).

## What to avoid

- Decorative hero imagery that pushes content down.
- Placeholder text standing in for a label.
- Icon-only controls without an accessible name.
- More than one accent colour competing for attention.
- Modals for anything that could be a page or an inline edit.
- Spinners where a skeleton would show the shape of what is coming.
- Toasts for errors that need a decision — put those where the decision is made.
