# Visual review

A critical pass over every screen, for grading and prioritising. **Nothing here is built.**

Each item has an id so it can be referred to, a proposal, and the reason. Put a grade in the
margin — the third column is empty on purpose.

## How this was made

Screenshots come from the end-to-end suite, which takes them where a test is already standing in
front of something worth looking at. Eight screens had never been captured (the whole Academy, the
registry, the applications queue, the apply form); `e2e/20-gallery.spec.ts` now takes those too, so
this can be repeated rather than reconstructed.

**Looked at directly:** home, recipe list, recipe detail, cooking step, plan, pantry, shopping,
Academy list, Academy page, registry list, apply.

**Not looked at, and so not reviewed below:** settings, setup, bootstrap, sign-in, landing,
household, eater form, import, invent, discovery, meal form, cook prep, cook done, applications
queue, registry entry, Academy write, Academy term chooser. Their screenshots exist; a second pass
should cover them rather than this one guessing.

---

## Cross-cutting

These are worth doing first because each one fixes several screens at once.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **X1** | **Eight components use `.page`, `.action` and `.notice` without importing the partial that defines them.** Add the `@use` line to each. | Not a matter of taste — a defect with a one-line fix per file. `_page.scss` defines all three, Angular scopes component styles, and a component that does not `@use` it gets *nothing*: no page padding, browser-default grey buttons, and cautions rendered as plain bold text. It is why the Academy page has text at the very edge of the screen and why **"Ask to be let in" — the primary action on the apply screen — is a pale grey block** while "Start cooking now" is solid red. Affected: `academy/academy`, `academy/page`, `academy/write-page`, `registry/registry`, `registry/ingredient`, `recipes/recipe-form`, `apply/apply`, `sign-in/sign-in`. | |
| **X2** | Add a lint rule or a test that fails when a template uses a shared class the component does not import. | X1 happened eight times without anybody noticing, which means it will happen a ninth. The check is mechanical: grep the template for the classes, grep the stylesheet for the `@use`. | |
| **X3** | Replace the five navigation glyphs (`◆ ☰ ▤ ✓ ▦`) with real icons. | They are text characters standing in for icons and they read as missing-font fallbacks — particularly the diamond for Home and the grid for Pantry, which mean nothing. This is the single most visible thing on every screen, since the bar is on all of them. | |
| **X4** | Give recipes a picture. | There is no imagery anywhere in the product. The recipe list is a wall of text where every card is the same shape and weight, and a cook scanning for tonight's dinner is reading rather than looking. `MediaAccess` already exists and the Academy already uses it. | |
| **X5** | Decide what a short page does with its space. | Home, Shopping, Pantry, the Academy page and the cooking step all end with 40–60% of the viewport empty. Each currently looks like a page that failed to load. Options: centre the content block, or fill the space with the next useful thing. | |
| **X6** | Structure the long lists. | The Academy is 11,000 px tall on a phone and the registry is 19,000 px — both flat, unstyled, ungrouped, unvirtualised. An alphabet index, sticky letter headings, or paging would all help; doing nothing is not an option once the registry has 900 entries, which it does today. | |
| **X7** | Style destructive actions as destructive, consistently. | "Delete this plan" is plain red text and looks like a link; "Put it away" is an outlined button; "Put this page away" is a browser-default button. Three treatments for the same kind of action. | |
| **X8** | Make absence quiet. | Five identical dashed "Nothing planned" rows on the plan, a full-width grey block on the recipe list saying nobody has been recorded. Absence currently takes more space and weight than presence. | |

---

## Home

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **H1** | Fill the page, or say why it is empty. | One card, then two thirds of the screen empty. Home is supposed to answer *what is happening now* — what wants eating, what is on tonight, what to do next — and only the first of those appears. | |
| **H2** | Give "What can I cook with these" an affordance. | It is bold red text with no chevron, underline or button. It is the card's main action and does not look like one. | |
| **H3** | Consider shrinking the greeting. | "Good evening Emanuel" takes a fifth of the viewport above the fold on a phone, and is the least useful thing on the screen after the first day. | |

## Recipe list

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **R1** | Add a thumbnail per card (see X4). | Three cards of identical grey text is a list that has to be read. | |
| **R2** | Fix the A–Z / Worth cooking control. | The selected half's fill has a rounded outer edge and a hard square inner one against a fully-rounded container. It reads as unfinished rather than as a deliberate segmented control. | |
| **R3** | Lighten the timing metadata. | Two bold lines per card for hands-on and total. On the first card they wrap to two lines because of "at least"; on the others they fit on one. Same information, two shapes. | |
| **R4** | Put the ways of adding a recipe above the fold. | Write, import and *write me a recipe* are the three things this screen exists to start, and none is visible without scrolling past the list. | |

## Recipe detail

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **D1** | Do not print hands-on and total when they are the same number. | "at least 30 min HANDS-ON / at least 30 min TOTAL" reads as a mistake. | |
| **D2** | Make the yield stepper symmetrical. | The `+` is a filled circle and the `−` is bare text. They do the same kind of thing in opposite directions. | |
| **D3** | Move nutrition below the method. | It is the longest block on the page and sits between the ingredients and the thing the cook came for. Nutrition is reference; the method is the recipe. | |
| **D4** | The "make a version" input clips its own placeholder. | "Dairy-free, without the eggs" is cut off mid-word — the field is too narrow beside its button on a phone. | |
| **D5** | Match the widths of "Correct this recipe" and "Put it away". | They are stacked, both outlined, and different widths, which reads as accidental. | |

## Cooking mode

The strongest screen in the product. Large type, clear progress, one obvious next action.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **C1** | Close the gap between the instruction and the timer. | On a short step there is a third of a screen of nothing between them. Centring the instruction in the space above the timer would keep both in the same glance. | |
| **C2** | Give the temperature the weight the timer has. | For a baking step, 160 °C matters as much as 40:00 and is a small grey chip beside a very large clock. | |

## Plan

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **P1** | Move "Show recipe" inside its meal card, or make the card itself the link. | It currently sits outside and below the card, attached to nothing. | |
| **P2** | Make an empty day tappable, and say so. | Five dashed rows reading "Nothing planned" are the obvious place to add a meal, and the only way to add one is a button at the bottom of the page. | |
| **P3** | Decide whether the shopping list belongs here. | It is embedded at the foot of the plan *and* has its own tab in the navigation. One of the two should win. | |
| **P4** | Style "Delete this plan" as destructive (see X7). | | |

## Pantry

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **N1** | Stop showing the same lot twice. | "USE THESE SOON" repeats, word for word, the lot displayed immediately below it — including the "Use within 2 days" flag. On a shelf with one thing on it, the screen says everything twice. | |
| **N2** | Grade the urgency visually. | "Use within 2 days" and "use within 20 days" differ only in the words. A colour ramp or a bar would let the shelf be scanned rather than read. | |

## Shopping

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **S1** | The empty state is two lines at the top of a blank screen. | The sentence is good ("Everything this week needs is already in your kitchen"). It is floating in 80% nothing, and it is the state a well-stocked kitchen sees most often. | |

## Academy

Every problem here is downstream of **X1** — none of these three components imports the shared
styles, so the section is effectively unstyled.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **A1** | Apply X1 first, then look again. | Text currently starts at x=0 with no page padding, buttons are browser-default grey rectangles with square corners, and the "Take care" caution — the one piece of safety copy on the page — renders as plain bold text instead of a warning notice. | |
| **A2** | Structure the list (see X6). | Fifty entries, flat, alphabetical, each a link plus a grey line. Nothing distinguishes a technique from an ingredient, which matters now that both sections exist. | |
| **A3** | Give the lookup and the section filter room and a selected state. | The three section buttons are unstyled and crowded against the search field; nothing shows which is active. | |
| **A4** | Style "Write a page" as an action. | It is a plain underlined link above the list, and it is the only way to contribute. | |
| **A5** | Style the spelling chips. | "Also written blanched blanches blanching" is a run of grey words, not the chips the recipe screen uses for the same idea. | |

## Registry

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **G1** | Apply X1. | No page padding; the filter bar bleeds to both screen edges with no rounding; the search field is a plain full-bleed box. | |
| **G2** | Structure 900 entries (see X6). | 19,000 px of flat rows, three cramped lines each, with a "Show more" at the bottom. | |
| **G3** | Reconsider the default sort. | The first screen is entirely "11 vol% wine white", "12 vol% wine red", "12.5 vol% wine white" — an alphabetical sort putting numeric-prefixed entries first means the registry's first impression is a wine list. | |
| **G4** | Tighten the row. | Name, then "Solid · No density", then "Not checked for allergens" — three lines per entry, all the same weight, most of it saying what is *absent*. | |

## Apply

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| **Y1** | Apply X1 — the primary button is unstyled. | "Ask to be let in" is a pale grey block. It is the only action on the page and it looks disabled. | |
| **Y2** | Align the language and theme selects. | Two native selects of different widths with right-aligned labels at different x positions, adrift at the bottom of the page. | |

---

## What this review did not cover

- **Themes.** Everything above is the light theme. Dark, playful and decorative have screenshots and
  have not been looked at.
- **Wider viewports.** Phone only, which is the design target — but the laptop and tablet
  screenshots exist and the layouts may simply be stretched.
- **Motion, focus states, and loading.** None of it is visible in a screenshot. The registry's first
  capture was of the word "Loading…", which is the only reason it came up at all.
