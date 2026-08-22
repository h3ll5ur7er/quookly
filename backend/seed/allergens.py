"""Which allergens a published food row contains, and whether we are sure.

Split out from the builder because this is the only part of the bulk import where being
wrong is dangerous, and it should be readable on its own.

**The rule the whole module obeys.** Saying an ingredient *contains* an allergen can only
make a verdict more cautious, so a wrong "contains" costs a cook a dish. Saying it contains
*none* — which is what `classified` with an empty set means — can put an allergen on a
plate. So the two are held to different standards: a keyword is enough to add one, and only
a category whose complete allergen set is knowable from the category alone may be declared
complete ([ADR-006](../../doc/07-decisions.md#adr-006-allergen-determination-is-structural)).

Anything this module is not sure about comes back **unclassified**, which reads as "nobody
has looked" rather than "safe". That is the failure this codebase was built to have.
"""

import re
from typing import NamedTuple

from quookly.contracts.ingredient import Allergen


class Verdict(NamedTuple):
    """What is in it, and whether that list is the whole answer.

    `classified=False` means the set is what we noticed, not what is there. It is stored as
    absence, so suitability says nobody has looked.
    """

    allergens: frozenset[Allergen]
    classified: bool


def _words(*terms: str) -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)


#: Names that name their allergen. Matching one *adds* the allergen; missing one never
#: removes it, so this table is allowed to be incomplete.
NAMED: tuple[tuple[re.Pattern[str], Allergen], ...] = (
    (
        _words(
            "milk",
            "cream",
            "butter",
            "cheese",
            "yogurt",
            "yoghurt",
            "quark",
            "whey",
            "curd",
            "kefir",
            "buttermilk",
            "ghee",
        ),
        Allergen.MILK,
    ),
    (_words("egg", "eggs", "mayonnaise", "meringue"), Allergen.EGGS),
    # Breadcrumbs are wheat unless a label says otherwise, and something breaded has them.
    (_words("breaded", "crumbed", "breadcrumb", "breadcrumbs", "panko"), Allergen.GLUTEN),
    (
        _words(
            "wheat",
            "rye",
            "barley",
            "spelt",
            "oat",
            "oats",
            "semolina",
            "couscous",
            "bulgur",
            "seitan",
            "farro",
            "kamut",
            "malt",
            "bread",
            "pasta",
            "noodle",
            "noodles",
            "durum",
        ),
        Allergen.GLUTEN,
    ),
    (
        _words("soy", "soya", "soybean", "soybeans", "tofu", "tempeh", "edamame", "miso"),
        Allergen.SOYBEANS,
    ),
    (_words("peanut", "peanuts", "groundnut"), Allergen.PEANUTS),
    (
        _words(
            "almond",
            "almonds",
            "hazelnut",
            "hazelnuts",
            "walnut",
            "walnuts",
            "cashew",
            "cashews",
            "pistachio",
            "pistachios",
            "pecan",
            "pecans",
            "macadamia",
            "brazil nut",
            "chestnut",
            "chestnuts",
            "pine nut",
            "pine nuts",
        ),
        Allergen.TREE_NUTS,
    ),
    (_words("sesame", "tahini"), Allergen.SESAME),
    (_words("celery", "celeriac"), Allergen.CELERY),
    (_words("mustard"), Allergen.MUSTARD),
    (_words("lupin", "lupine"), Allergen.LUPIN),
    (
        _words(
            "fish",
            "salmon",
            "tuna",
            "cod",
            "herring",
            "sardine",
            "sardines",
            "anchovy",
            "anchovies",
            "trout",
            "mackerel",
            "perch",
            "pike",
            "plaice",
            "haddock",
            "halibut",
            "sole",
            "eel",
            "carp",
            "pangasius",
            "tilapia",
            "seabream",
            "sea bream",
            "seabass",
            "sea bass",
        ),
        Allergen.FISH,
    ),
    (
        _words(
            "prawn",
            "prawns",
            "shrimp",
            "shrimps",
            "crab",
            "lobster",
            "crayfish",
            "langoustine",
            "scampi",
        ),
        Allergen.CRUSTACEANS,
    ),
    (
        _words(
            "mussel",
            "mussels",
            "oyster",
            "oysters",
            "clam",
            "clams",
            "squid",
            "octopus",
            "cuttlefish",
            "scallop",
            "scallops",
            "snail",
            "snails",
        ),
        Allergen.MOLLUSCS,
    ),
    (
        _words(
            "wine",
            "beer",
            "vinegar",
            "dried apricot",
            "dried apricots",
            "sultana",
            "sultanas",
            "raisin",
            "raisins",
        ),
        Allergen.SULPHITES,
    ),
)

#: Categories whose complete allergen set follows from the category itself, given the
#: names table above. Only these may be declared classified.
#:
#: Each is a single-substance food group: a raw vegetable is a vegetable, and the only
#: declarable allergens that appear among them — celery, mustard, lupin — are named in the
#: name. A *sausage* is not on this list, and neither is a sauce or a ready mix: what else
#: went in is not knowable from "Sausages and cold meats".
COMPLETE: tuple[str, ...] = (
    "Vegetables/Fresh vegetables",
    "Vegetables/Frozen vegetables",
    "Vegetables/Mushrooms",
    "Vegetables/Herbs",
    "Vegetables/Sprouts and shoots",
    "Vegetables/Vegetable juices",
    "Fruit/Fresh fruit",
    "Fruit/Fruit juices",
    "Nuts, seeds and oleaginous fruit",
    "Eggs",
    "Milk and dairy products/Milk",
    "Milk and dairy products/Yogurt and curdled milk",
    "Milk and dairy products/Hard cheese",
    "Milk and dairy products/Soft cheese",
    "Milk and dairy products/Fresh cheese and curds",
    "Fats and oils/Oils",
    "Fats and oils/Cream",
    "Meat and offal/Beef",
    "Meat and offal/Veal",
    "Meat and offal/Pork",
    "Meat and offal/Poultry",
    "Meat and offal/Lamb, mutton",
    "Meat and offal/Game",
    "Meat and offal/Other animal species",
    "Fish/Sea fish",
    "Fish/Fresh water fish",
    "Fish/Seafood, crustaceans and shellfish",
    "Cereal products, pulses and potatoes/Rice",
    "Cereal products, pulses and potatoes/Corn",
    "Cereal products, pulses and potatoes/Potatoes and other starchy tubers",
    "Cereal products, pulses and potatoes/Pulses",
    "Sweets/Sugar and sweeteners",
    "Non-alcoholic beverages/Drinking water",
)

#: Groups where an allergen is present whatever the name says, because the group *is* the
#: allergen. A hard cheese with a name that mentions no milk is still milk.
BY_CATEGORY: tuple[tuple[str, Allergen], ...] = (
    ("Milk and dairy products/", Allergen.MILK),
    ("Fats and oils/Cream", Allergen.MILK),
    ("Eggs", Allergen.EGGS),
    ("Fish/Sea fish", Allergen.FISH),
    ("Fish/Fresh water fish", Allergen.FISH),
)


#: Words that say a food was put together from other foods. A terrine is filed under
#: "Meat and offal/Game" and a breaded escalope under "Veal", and neither is a cut of meat:
#: what else went into them is not knowable from the category. Found here, the row is
#: never declared complete — only ever *more* cautious.
COMPOSED = _words(
    "terrine",
    "pâté",
    "pate",
    "paté",
    "breaded",
    "crumbed",
    "stuffed",
    "filled",
    "prepared",
    "marinated",
    "seasoned",
    "sausage",
    "burger",
    "patty",
    "cordon bleu",
    "nugget",
    "nuggets",
    "ready",
    "mix",
    "mixture",
    "spread",
    "dumpling",
    "roulade",
    "gratin",
    "pie",
    "tart",
    "cake",
    "biscuit",
    "cookie",
    "bar",
    "dessert",
)


def _categories(category: str | None) -> list[str]:
    """A row's categories. The table writes several, separated by semicolons."""
    return [part.strip() for part in str(category or "").split(";") if part.strip()]


def of(name: str, category: str | None) -> Verdict:
    """What this row contains, and whether that is the whole answer."""
    found = {allergen for pattern, allergen in NAMED if pattern.search(name)}
    for prefix, allergen in BY_CATEGORY:
        if any(one.startswith(prefix) for one in _categories(category)):
            found.add(allergen)

    # Every category has to be one we can answer completely. A row filed under both
    # "Fresh fruit" and "Sauces" is a sauce as well, and we cannot say what is in a sauce.
    parts = _categories(category)
    complete = (
        bool(parts)
        and all(one in COMPLETE for one in parts)
        # A composed food filed under a plain category is still composed.
        and not COMPOSED.search(name)
    )
    return Verdict(frozenset(found), complete)
