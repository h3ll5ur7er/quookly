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
| ~~**X1**~~ **done** | **Eight components use `.page`, `.action` and `.notice` without importing the partial that defines them.** Add the `@use` line to each. | Not a matter of taste — a defect with a one-line fix per file. `_page.scss` defines all three, Angular scopes component styles, and a component that does not `@use` it gets *nothing*: no page padding, browser-default grey buttons, and cautions rendered as plain bold text. It is why the Academy page has text at the very edge of the screen and why **"Ask to be let in" — the primary action on the apply screen — is a pale grey block** while "Start cooking now" is solid red. Affected: `academy/academy`, `academy/page`, `academy/write-page`, `registry/registry`, `registry/ingredient`, `recipes/recipe-form`, `apply/apply`, `sign-in/sign-in`. | A |
| ~~**X2**~~ **done** | Add a lint rule or a test that fails when a template uses a shared class the component does not import. | X1 happened eight times without anybody noticing, which means it will happen a ninth. The check is mechanical: grep the template for the classes, grep the stylesheet for the `@use`. | A |
| ~~**X3**~~ **done** | Replace the five navigation glyphs (`◆ ☰ ▤ ✓ ▦`) with real icons. | They are text characters standing in for icons and they read as missing-font fallbacks — particularly the diamond for Home and the grid for Pantry, which mean nothing. This is the single most visible thing on every screen, since the bar is on all of them. | B |
| ~~**X4**~~ **done** | Give recipes a picture. | There is no imagery anywhere in the product. The recipe list is a wall of text where every card is the same shape and weight, and a cook scanning for tonight's dinner is reading rather than looking. `MediaAccess` already exists and the Academy already uses it. | A |
| ~~**X5**~~ **partly** | Decide what a short page does with its space. Home now asks four questions rather than hiding the ones it has no answer to, and the shopping list's empty state is centred in its space with the next thing to do under it. The cooking step and the Academy page are unchanged — both are short because their content is short, which is not the same failure. | Home, Shopping, Pantry, the Academy page and the cooking step all end with 40–60% of the viewport empty. Each currently looks like a page that failed to load. Options: centre the content block, or fill the space with the next useful thing. | C |
| ~~**X6**~~ **done, in the flat sense** | Structure the long lists. Sticky letter headings on the registry, and the Academy grouped by section and then by letter. **Not** the hierarchy — `Academy > Ingredients > Vegetables > Carrot` needs a food taxonomy the registry does not have, and that is a feature rather than a pass over the styling. | The Academy is 11,000 px tall on a phone and the registry is 19,000 px — both flat, unstyled, ungrouped, unvirtualised. An alphabet index, sticky letter headings, or paging would all help; doing nothing is not an option once the registry has 900 entries, which it does today. | B |
| ~~**X7**~~ **done** | Style destructive actions as destructive, consistently. | "Delete this plan" is plain red text and looks like a link; "Put it away" is an outlined button; "Put this page away" is a browser-default button. Three treatments for the same kind of action. | A |
| ~~**X8**~~ **done** | Make absence quiet. The plan's dashed rows say what they do — "Put something on" — rather than what is missing; the registry stopped spending a line per row on "No density"; home answers its empty questions in a muted line. | Five identical dashed "Nothing planned" rows on the plan, a full-width grey block on the recipe list saying nobody has been recorded. Absence currently takes more space and weight than presence. | C |

---

## Home

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**H1**~~ **done** | Fill the page, or say why it is empty. | One card, then two thirds of the screen empty. Home is supposed to answer *what is happening now* — what wants eating, what is on tonight, what to do next — and only the first of those appears. | B |
| ~~**H2**~~ **done** | Give "What can I cook with these" an affordance. | It is bold red text with no chevron, underline or button. It is the card's main action and does not look like one. | B |
| ~~**H3**~~ **done** | Consider shrinking the greeting. | "Good evening Emanuel" takes a fifth of the viewport above the fold on a phone, and is the least useful thing on the screen after the first day. | B|

## Recipe list

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**R1**~~ **done, with X4** | Add a thumbnail per card (see X4). | Three cards of identical grey text is a list that has to be read. | C |
| ~~**R2**~~ **done** | Fix the A–Z / Worth cooking control. | The selected half's fill has a rounded outer edge and a hard square inner one against a fully-rounded container. It reads as unfinished rather than as a deliberate segmented control. | D |
| ~~**R3**~~ **done** | Lighten the timing metadata. | Two bold lines per card for hands-on and total. On the first card they wrap to two lines because of "at least"; on the others they fit on one. Same information, two shapes. | B |
| ~~**R4**~~ **done** | Put the ways of adding a recipe above the fold. | Write, import and *write me a recipe* are the three things this screen exists to start, and none is visible without scrolling past the list. | A |

## Recipe detail

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**D1**~~ **done** | Do not print hands-on and total when they are the same number. | "at least 30 min HANDS-ON / at least 30 min TOTAL" reads as a mistake. | C |
| ~~**D2**~~ **done, though not as reported** | Make the yield stepper symmetrical. **Both halves were already the same rule** — a transparent circle that fills on hover — so what the screenshot caught was almost certainly the `+` under the pointer. What was actually wrong is that at rest *neither* looked like a button. Both are a filled circle now. | The `+` is a filled circle and the `−` is bare text. They do the same kind of thing in opposite directions. | C |
| ~~**D3**~~ **done** | Move nutrition below the method. | It is the longest block on the page and sits between the ingredients and the thing the cook came for. Nutrition is reference; the method is the recipe. | B |
| ~~**D4**~~ **done** | The "make a version" input clips its own placeholder. | "Dairy-free, without the eggs" is cut off mid-word — the field is too narrow beside its button on a phone. | D |
| ~~**D5**~~ **done** | Match the widths of "Correct this recipe" and "Put it away". | They are stacked, both outlined, and different widths, which reads as accidental. | C |
| ~~**D7**~~ **done** | **The nutrition table is wider than a phone.** | Measured, not eyeballed: `.nutrition__table` ends at **429 px in a 412 px viewport**, so the right-hand column is clipped off-screen and the two figures run together — *"1460 kJ / 347 kcal5840 kJ / 1389 kcal"*. It happens whenever a recipe has both a per-serving and a whole-recipe column. **In English as well**, which I only found by capturing an English control: I had assumed it was translation length and it is not. French is worse (447 px) because *RECETTE ENTIÈRE* is longer, so translation exposes it rather than causing it. `e2e/21-translated-layouts.spec.ts` measures this and carries it as a known exception; delete the exception when this is fixed. | |
| ~~**D6**~~ **done** | "Start cooking now" shall transfer the number of servings instead of always taking the default saved in the recipe. | The cook has just changed the yield and expects that to be reflected in the cooking step. | B |
## Cooking mode

The strongest screen in the product. Large type, clear progress, one obvious next action.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**C1**~~ **done** | Close the gap between the instruction and the timer. | On a short step there is a third of a screen of nothing between them. Centring the instruction in the space above the timer would keep both in the same glance. | B |
| ~~**C2**~~ **done** | Give the temperature the weight the timer has. | For a baking step, 160 °C matters as much as 40:00 and is a small grey chip beside a very large clock. | B |

## Plan

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**P1**~~ **done** | Move "Show recipe" inside its meal card, or make the card itself the link. | It currently sits outside and below the card, attached to nothing. | B |
| ~~**P2**~~ **done — half of it already was** | Make an empty day tappable, and say so. **The whole row has been a link** since P1; what was missing was anything on it saying so. It now says "Put something on" and carries a `+`. | Five dashed rows reading "Nothing planned" are the obvious place to add a meal, and the only way to add one is a button at the bottom of the page. | D |
| ~~**P3**~~ **done, your way** | Decide whether the shopping list belongs here. Kept and folded away, with a count in the summary. | It is embedded at the foot of the plan *and* has its own tab in the navigation. One of the two should win. | D |
| ~~**P4**~~ **done, with X7** | Style "Delete this plan" as destructive (see X7). | | B|

## Pantry

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**N1**~~ **done** | Stop showing the same lot twice. The strip is gone; the shelf sorts by what wants eating instead, which is the same answer without a second copy of it — and one fewer request, since every lot already carries the server's verdict on its own date. | "USE THESE SOON" repeats, word for word, the lot displayed immediately below it — including the "Use within 2 days" flag. On a shelf with one thing on it, the screen says everything twice. | D |
| ~~**N2**~~ **done, with the sort you asked for** | Grade the urgency visually. Four bands down the leading edge of a packet, and "Use first / A–Z" on the shelf. | "Use within 2 days" and "use within 20 days" differ only in the words. A colour ramp or a bar would let the shelf be scanned rather than read. | B |

## Shopping

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**S1**~~ **done** | The empty state is two lines at the top of a blank screen. | The sentence is good ("Everything this week needs is already in your kitchen"). It is floating in 80% nothing, and it is the state a well-stocked kitchen sees most often. | D |
| ~~**S2**~~ **done** | Shopping list shall be grouped by category. The blocker is gone: the food tree now exists, taken from the column the Swiss table always carried ([ADR-067](07-decisions.md#adr-067-where-a-food-sits-is-a-tree-taken-from-the-table-it-was-already-in)). The list is in aisles with sticky headings, named in the cook's language, and what nobody has placed goes last under a heading the *screen* writes — the server does not invent one. |
| ~~**S3**~~ **done** | There should be a "add ticked to pantry" action. One lot per ticked line, and the line is unticked once its lot exists — so an interrupted unpack leaves the basket holding what is still in a bag. | The list is a checklist, but the only way to act on it is to go to the pantry and add each item manually. | D |
| ~~**S4**~~ **done** | There should be a "trashcan" action. "Empty the basket" — the list itself is derived from the plan and cannot be deleted, so what it clears is the ticks. | There should be a way to remove the list without adding it to the pantry. | D |


## Academy

Every problem here is downstream of **X1** — none of these three components imports the shared
styles, so the section is effectively unstyled.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**A1**~~ **done, with X1** | Apply X1 first, then look again. | Text currently starts at x=0 with no page padding, buttons are browser-default grey rectangles with square corners, and the "Take care" caution — the one piece of safety copy on the page — renders as plain bold text instead of a warning notice. | A  |
| ~~**A2**~~ **done** | Structure the list (see X6). | Fifty entries, flat, alphabetical, each a link plus a grey line. Nothing distinguishes a technique from an ingredient, which matters now that both sections exist. | B |
| ~~**A3**~~ **done, and it had got worse** | Give the lookup and the section filter room and a selected state. Since X1 added `@use controls`, the three bare buttons had become three *filled red* buttons in a row — three of the screen's action. They are a segmented control now. The lookup row had no rules at all. | The three section buttons are unstyled and crowded against the search field; nothing shows which is active. | B |
| ~~**A4**~~ **done** | Style "Write a page" as an action. | It is a plain underlined link above the list, and it is the only way to contribute. | B |
| ~~**A5**~~ **done, with X1** | Style the spelling chips. | "Also written blanched blanches blanching" is a run of grey words, not the chips the recipe screen uses for the same idea. | B |

## Wider viewports

Reviewed at laptop width. The layout is **not** a stretched phone — there is a real sidebar and a
three-column card grid, and the recipe list at that width is the best-looking screen in the product.
Three things are wrong with it.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**W1**~~ **done, and half of it was wrong** | Put the Academy in the sidebar. **Settings was already there** — the account row at the foot of the column is a link to it, so the claim that neither was reachable held for the Academy only. | It has five items, the same five as the phone's tab bar, and roughly half its height is empty. The Academy and the settings screens are not reachable from the navigation at all on a laptop, on a column that has room for them and nothing else to do. | |
| ~~**W2**~~ **done** | Match card heights within a grid row. | "American Pancakes" is twice the height of the "Buttermilk Waffles" beside it, so each row ends ragged. | |
| ~~**W3**~~ **done** | Home is worse on a laptop than on a phone. Four cards in a two-column grid across the page's full measure. What is left is vertical space under a dashboard that has little on it yet, which fills as the week does — not something to pad. | One phone-width card in the top-left corner of a 2000×1250 canvas — about 90% empty, and the card does not use the width it has been given. This is X5, and the wide viewport is where it looks worst. | |
| ~~**W4**~~ **done with R4** | Bring the three ways of adding a recipe up out of the basement. | R4 on a phone; on a laptop they sit below a nine-card grid with an empty sidebar sitting beside the top of the page. | |

## Registry

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**G1**~~ **done, with X1** | Apply X1. | No page padding; the filter bar bleeds to both screen edges with no rounding; the search field is a plain full-bleed box. | A |
| ~~**G2**~~ **done** | Structure 900 entries (see X6). | 19,000 px of flat rows, three cramped lines each, with a "Show more" at the bottom. | B |
| ~~**G3**~~ **done** | Reconsider the default sort. A name opening with a digit now sorts after the ones opening with a letter — server-side, since the list is paged. | The first screen is entirely "11 vol% wine white", "12 vol% wine red", "12.5 vol% wine white" — an alphabetical sort putting numeric-prefixed entries first means the registry's first impression is a wine list. | D |
| ~~**G4**~~ **done** | Tighten the row. | Name, then "Solid · No density", then "Not checked for allergens" — three lines per entry, all the same weight, most of it saying what is *absent*. | B |
| ~~**G5**~~ **done** | We imported the swiss food table, that contains allergens. For each item in the registry that has no allergens, it says "Not checked for allergens". This is confusing. | The states of "not checked" and "no allergens" has to be clearly distinguished. | A |


## Apply

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**Y1**~~ **done, with X1** | Apply X1 — the primary button is unstyled. | "Ask to be let in" is a pale grey block. It is the only action on the page and it looks disabled. | B |
| ~~**Y2**~~ **done** | Align the language and theme selects. | Two native selects of different widths with right-aligned labels at different x positions, adrift at the bottom of the page. | C |

---

## Themes

Four themes ship: light, dark, playful, decorative. **Three of them are the same theme.**

Measured as CIELAB ΔE between the token values — under ~2.3 is *the same colour* to the eye, under
~5 is *a shade of the same colour*:

| token | light↔playful | light↔decorative | playful↔decorative |
| --- | --- | --- | --- |
| `--surface` (the page) | 3.1 | 5.1 | 3.2 |
| `--surface-raised` (every card) | **0.0** | 4.1 | 4.1 |
| `--on-surface` (all text) | 7.4 | 4.6 | 6.9 |
| `--primary` (every filled button) | 17.3 | 20.5 | 36.6 |

The ground a cook looks at for the whole session is the same warm off-white in all three, and
`--surface-raised` is *literally the same value* in light and playful — both `#ffffff`. Text is a
warm near-black in all three. Only `--primary` moves, and it stays in the rust family.

What actually differs: **corner radius** (0.5 / 1 / 0.25 rem), **motion** (playful alone has a
springy `cubic-bezier(0.34, 1.4, 0.64, 1)` and slower durations), and **one font** (decorative alone
sets a serif body). Side by side, the sign-in screens differ in how round the button is.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**T1**~~ **done** | Give playful and decorative grounds of their own. | Changing `--surface` and `--surface-raised` is what a person actually perceives as "a different theme". Today the only page-sized surface is the same colour in all three, so switching feels like nothing happened. | B |
| ~~**T2**~~ **done** | Make the names true, or change the names. | *Playful* is a rounder rust button on cream. *Decorative* is a squarer rust button on cream with a serif. Neither is playful or decorative; both are the default with one knob turned. Either commit to the personality the name promises — playful gets colour and energy, decorative gets ornament, rules, a patterned surface — or rename them to what they are ("Soft", "Sharp"). | B |
| ~~**T3**~~ **answered: the theme owns it** | Decide whether `--primary` is the brand or the theme. | Rust is the filled-button colour in all three light themes and the most-seen colour in the product. A theme that cannot change it cannot look different. If rust is the brand, then themes must differentiate on ground and type instead — which is T1 and T4. | B |
| ~~**T4**~~ **done** | Let decorative's serif do more, and playful's motion be seen. | Decorative sets a serif for *body as well as display*, which flattens hierarchy rather than decorating: on the sign-in form the field labels now look like headings. Playful's real distinction is its spring easing, which no screenshot can show — worth a short screen recording before judging it. | B |
| ~~**T5**~~ **now capturable** | Dark is the only theme that is genuinely a second theme, and it has not been reviewed. | It inverts the ground properly. It is also the only one of the four whose contrast pairs have not been checked here at all. | C |

## Language

Three catalogues ship complete — `just frontend check` fails when one is not — so this is about
whether the translations are *right*, not whether they exist. Almost all of them are good: the
allergen names are the legally correct EU/Swiss terms in both languages (*Schalenfrüchte*, *Fruits à
coque*, *Anhydride sulfureux et sulfites*), and Swiss orthography is respected — not one `ß` in the
German catalogue.

Three things are wrong.

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**L1**~~ **done** | **The Swiss French meal names are shifted by one meal.** `mealBreakfast` → *Petit-déjeuner*, `mealLunch` → *Déjeuner*, `mealDinner` → *Dîner*. | Those are the **France** French names. In Switzerland the three meals are **déjeuner, dîner, souper** — so this catalogue labels the evening slot *Dîner*, which a Swiss French cook reads as **lunch**. This is a meal planner: it is not a nicety, it is the wrong meal on the wrong day, and it is wrong in the one locale the file is named for. | B |
| ~~**L2**~~ **German done; French is a question below** | Settle on one form of address in German. **Answered: informal — *du*.** So it is the 57 formal strings that change, not the 6 informal ones. | 57 strings address the reader formally and 6 informally. The six informal ones are `academyAskFailed`, `academyWaitingWhat`, `academyWriteFailed`, `academyWriteSlugHint`, `academyWriteWhat` and `recipeTranslated` — every one added in Phase 7 or 8b, and all mine. The rest of the product says *Sie brauchen es*, *Wählen Sie einen Eintrag*, *Ihre Bewerbung*; the Academy says *versuche es noch einmal* and *Für dich übersetzt*. This is now the larger job of the two — 57 strings — and it needs French checking at the same time, which is consistently *vous* and would want *tu*. | B |
| ~~**L3**~~ **done** | Look at the app in German and French, which nobody has. Seven screens in each, captured by `e2e/20-gallery.spec.ts`. Looking at them is what found L1, L2 and L6 — and what showed the timer buttons do *not* wrap. | There is exactly **one** non-English screenshot in the suite — `sign-in-de-CH` — and none in French. German and French labels are routinely two to three times longer than the English (*Reset* → *Réinitialiser*, *Use by* → *Zu verbrauchen bis*, *Add* → *Hinzufügen*), and the tightest place in the product is the pair of timer buttons in cooking mode, which is the screen a cook reads at arm's length. Nobody has seen it wrap. | B |

| ~~**L6**~~ **done** | **The interface language and the content language come from different places, and they disagree.** **Fixed: the account wins, always** ([ADR-066](07-decisions.md#adr-066-the-language-is-the-accounts-and-the-browser-answers-only-for-strangers)). Signing in adopts the account's language; where the account has none — which is every account until somebody opens the picker — the one being read is written to it, which is what closes the gap rather than papering over it. Signing out forgets the device's choice, because it belonged to the person. `e2e/22-the-language-you-chose.spec.ts` signs a German account in on an English browser and asserts **both** halves: the furniture *and* the food. Either alone passes while the product still contradicts itself. |

Smaller, and worth a second opinion from a native speaker rather than from me:

| id | Proposal | Why | Grade |
| --- | --- | --- | --- |
| ~~**L4**~~ **done** | `attentionWaiting` DE — *"Sie können weggehen"*. | Literally *you may leave*, which reads as permission to depart rather than *this looks after itself*. Something like *läuft von allein* carries what the English does. | C |
| ~~**L5**~~ **done** | `entryNoneIsAnAnswer` FR — *"ce qui diffère de personne n'ayant vérifié"*. **On the suggested *"pas encore vérifié"*:** that says *not yet checked*, which is one of the two states the sentence exists to tell apart — it would name the wrong one. Something like *"…, ce qui n'est pas la même chose que si personne n'avait vérifié"* keeps both halves. | Grammatical but stilted, and it is the sentence that distinguishes *checked and found nothing* from *nobody checked* — the one piece of allergen copy where being understood matters most (ADR-006). | C |

---

## What was checked and is fine

Recorded because a review that only lists faults cannot be used to tell whether anything is holding
up.

- **Contrast, all four themes.** Every foreground/background pair the product renders meets WCAG AA:
  body, muted and subtle text on every surface; labels on filled, accent, danger, success, warning
  and info. The only pair below 3:1 is `--border` on `--surface`, which is a decorative hairline and
  the disabled-field outline — both exempt.
- **Focus rings.** There is a global `:focus-visible` outline, and it is visible on every ground in
  every theme: between 4.9:1 and 8.2:1. I expected to find buttons without one and was wrong.
- **Layout under translation.** Nothing runs off the side of a phone in German or French except the
  nutrition table — and that one is broken in English too (D7). I specifically predicted the
  cooking-mode timer buttons would wrap; they do not. *Démarrer* and *Réinitialiser* sit side by side
  with room to spare.
- **Swiss orthography.** Not one `ß` in the German catalogue.
- **Allergen vocabulary.** The legally correct EU/Swiss terms in both languages — *Schalenfrüchte*,
  *Fruits à coque*, *Anhydride sulfureux et sulfites*. This is the one place a wrong word is a safety
  problem, and it is right.
- **The laptop layout.** A real sidebar and a real grid, not a stretched phone.

## Corrections to this review

- I reported the nutrition-table overflow as a translation problem. **It is not** — the English
  control breaks identically. It is D7, in the recipe-detail section where it belongs.
- I predicted the timer buttons would wrap in French. **They do not.**
- I nearly reported five catalogue keys as orphans. They are used from inline component templates
  that my extractor did not scan.
- `--ease-emphasised` — playful's spring curve, which I called "its only real distinction" — is
  **declared in the theme and used nowhere in the application**. So playful differs from light in
  corner radius and a slightly warmer ground, and in nothing else. That makes T1 and T2 stronger, and
  the second half of T4 moot until something animates.

## The one thing three findings wanted — built

S2, X6's hierarchy and half of A2 all needed the same missing thing: **something that knows a carrot
is a vegetable**. `IngredientKind` is `liquid / powder / solid / countable` and says in its own
docstring that it exists to choose a unit, not to classify food.

**It was in the reference table the whole time.** Every row of the Swiss Food Composition Database
names a category hierarchically — *Vegetables/Fresh vegetables* — and the three published editions
carry it against identical row ids, so it arrives translated: *Gemüse/Gemüse frisch*, *Légumes/Légumes
frais*. 120 nodes, 19 sections, all 864 shipped foods placed, nobody translated a word
([ADR-067](07-decisions.md#adr-067-where-a-food-sits-is-a-tree-taken-from-the-table-it-was-already-in)).

What it unblocked: the shopping list is in aisles (S2), and the registry can be narrowed to one part
of the shelf, which is what nine hundred entries needed beyond letters (X6, G2).

**Still not the Academy hierarchy.** The tree describes *foods*, and the Academy is pages — a
technique page has no category, and an ingredient page's category is the food's rather than the
page's. Reading the Academy as `Academy > Ingredients > Vegetables > Carrot` is now possible and is
its own piece of work. Nothing is blocking it any more.

## What this review still does not cover

All four gaps from the first pass are closed, and what they turned up is above. What is left:

- **The dark theme, looked at rather than measured.** `e2e/20-gallery.spec.ts` now captures seven
  screens in it, through a device that asks for dark — which is the state most of its readers get.
  The pictures exist; a second pass has to look at them.
- **Tablet width.** Phone and laptop are covered; the middle is not, and it is where a sidebar has to
  decide whether it exists.
- **Motion in use.** Not judgeable from a still, and moot for now — playful's spring curve is dead
  code (see Corrections). Worth a screen recording once something animates.
- **The sixteen screens listed at the top**, still: settings, setup, bootstrap, landing, household,
  eater form, import, invent, discovery, meal form, cook prep, cook done, applications, registry
  entry, Academy write, Academy term chooser.
- **A native speaker's read.** L4 and L5 are as far as I can usefully go on wording, and your answers
  to both are recorded in those rows.

## Found while fixing

- **`cook.component.scss` is at the style budget ceiling.** The build errors above 8 kB and warns
  above 4 kB; that file is 8.02 kB, so it has been sitting on the error threshold and any new rule
  fails the build. C1 was fitted into a rule that already existed rather than raising the budget or
  shaving bytes off unrelated rules. It is one stylesheet holding the prep list, the step view, the
  timer area, the finished screen and the offline states — worth splitting, and worth an item of its
  own next time. **Since split:** the finished screen is now `app-cook-finished`, which is where the
  room for C2 came from. 7.85 kB, which is still not much of a margin.
- **The shared partials emit CSS, and `@use` copies it into every component.** Growing
  `_page.scss` by one rule failed the build in `cook.component.scss`, a file nothing had
  touched — because that component carries its own copy of every shared rule and sits on the
  8 kB ceiling. The `:active` press for T4 went into the global stylesheet instead, where it
  exists once. Worth knowing before anybody adds to a partial.
- **`.field__hint` is used fifteen times and defined nowhere.** The shared class is `.hint`. Five
  templates — both Academy screens, the registry entry, the recipe form and the recipe page — carried
  a class that has never had a rule, so every one of those hints rendered as an ordinary paragraph
  instead of the quiet line under a field it was written to be. Renamed.
- **`.field` was defined nowhere either, and that one is a spacing bug.** `_form.scss` spaces labels
  with `form > label`, a *direct-child* selector — which does not match a label wrapped in
  `<div class="field">`. Five screens wrap their fields, so five screens quietly lost the rhythm the
  partial exists to give them. `.field` is now defined in the partial that owns the shape.
- **Three components printed their screen-reader-only text on the page.** `.visually-hidden` lives in
  `_a11y.scss`, and cooking mode, the recipe form and the registry never imported it — so five hidden
  labels in the recipe form and one in the registry were visible. This is X1 exactly, eight months
  after X1, and **the X2 checker said they were fine**: its class list was hand-written and had three
  classes on it. It now reads the partials themselves, which is how it found these plus `.hint` and
  `.error` unstyled on sign-in, apply and bootstrap. A hand-written list of what to check is a list
  that goes stale.
- **Five screens had each grown their own segmented control.** The recipe list's ordering and its
  have/put-away pair, the nutrition panel's plate-or-tray, the Academy's sections and the registry's
  filter. Three were the same fifteen lines with the same R2 flaw in them; one was three filled red
  buttons. `styles/_segmented.scss` now holds the shape, and the check above enforces the import.
- **The contrast checker was not checking links.** `--primary` is a link as well as a button
  fill, and only the button pair was listed — so playful passed `just frontend contrast` and
  failed axe on every link it drew, at 4.47:1. Two pairs added; the check went from 92 to 100.
- **`.week__show` was coloured with `--colour-muted`, which this application does not define.** The
  declaration had been doing nothing since it was written. Fixed with P1.
- **W1 was half wrong.** Settings *is* reachable from the laptop sidebar — the account row at the
  foot of the column is a link to it, and has been. What was missing from the navigation was the
  Academy, on a phone as well as on a laptop; its only ways in were an underlined word inside a
  recipe step and a row inside Settings. It is now the sixth section, shown where there is a column
  to show it in. A phone bar holds five: a sixth costs the others a whole word.
- **The nav glyphs were the smallest fix with the widest reach.** Five characters on every screen in
  the product, replaced by six drawn icons on one grid and one stroke weight (X3).

## One question back

**Should French go informal too?** — **answered: leave it, a native speaker will decide.** German is now *du* across 99 strings — four were left formal
because their "Sie"/"Ihr" is *she/it* rather than the reader ("Sie verlässt die Akademie" is the page
leaving). French is *vous* in 89 strings.

I have not converted them, because unlike the German this is not obviously the same decision. German
*du* with French *vous* is a defensible pairing rather than an inconsistency: French carries a
stronger T–V distinction, and plenty of products that say *du* in German say *vous* in French.
Converting is a cultural call, and 89 strings of French prose from somebody who is not a native
speaker — for a reviewer who has said the same — is a lot of surface to get subtly wrong at once.

Say the word and I will convert them; it is an afternoon, not a redesign.
