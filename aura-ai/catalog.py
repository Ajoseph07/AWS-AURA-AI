"""Reference data for AURA AI: the item catalog and the food bank directory.

All quantities in AURA AI are expressed in one common unit — CASES — so that
totals across items and categories are meaningful (see "never add up different
units" in the metrics spec). Every chart labels its values as cases.
"""
from __future__ import annotations

import re

UNIT = "cases"

# --------------------------------------------------------------------------- #
# Item catalog — category -> items
# --------------------------------------------------------------------------- #
CATALOG: dict[str, list[str]] = {
    "Grains and Starches": [
        "Rice", "Pasta", "Oatmeal", "Cereal", "Cornmeal", "Flour", "Quinoa",
        "Couscous", "Crackers", "Bread",
    ],
    "Protein Foods": [
        "Canned tuna", "Canned chicken", "Canned salmon", "Peanut butter",
        "Almond butter", "Beef jerky", "Canned ham", "Canned turkey",
        "Protein bars", "Powdered protein mix",
    ],
    "Beans and Legumes": [
        "Black beans", "Pinto beans", "Kidney beans", "Navy beans", "Chickpeas",
        "Lentils", "Split peas", "Refried beans", "Baked beans", "Canned chili beans",
    ],
    "Fruits": [
        "Canned peaches", "Canned pears", "Canned pineapple", "Applesauce",
        "Fruit cocktail", "Raisins", "Dried cranberries", "Dried apricots",
        "Dried mango", "Canned mandarin oranges",
    ],
    "Vegetables": [
        "Canned corn", "Canned green beans", "Canned peas", "Canned carrots",
        "Canned tomatoes", "Canned spinach", "Canned mushrooms", "Canned potatoes",
        "Mixed vegetables", "Tomato sauce",
    ],
    "Dairy and Alternatives": [
        "Shelf-stable milk", "Powdered milk", "Evaporated milk", "Condensed milk",
        "Cheese", "Yogurt", "String cheese", "Soy milk", "Almond milk", "Coconut milk",
    ],
    "Soups and Prepared Meals": [
        "Chicken noodle soup", "Tomato soup", "Vegetable soup", "Lentil soup",
        "Bean soup", "Minestrone soup", "Canned ravioli", "Canned spaghetti",
        "Macaroni and cheese", "Shelf-stable meal kits",
    ],
    "Breakfast Foods": [
        "Granola", "Breakfast bars", "Pancake mix", "Waffle mix", "Grits",
        "Cream of wheat", "Instant breakfast drinks", "Bagels", "Muffin mix",
        "Breakfast pastries",
    ],
    "Snacks": [
        "Popcorn", "Trail mix", "Pretzels", "Granola bars", "Fruit snacks",
        "Rice cakes", "Tortilla chips", "Potato chips", "Pudding cups", "Cookies",
    ],
    "Beverages and Pantry Staples": [
        "Bottled water", "Fruit juice", "Vegetable juice", "Coffee", "Tea",
        "Hot chocolate mix", "Cooking oil", "Salt", "Sugar", "Jelly or jam",
    ],
}

CATEGORIES: list[str] = list(CATALOG)

# Short labels for compact chart axes.
CATEGORY_SHORT: dict[str, str] = {
    "Grains and Starches": "Grains",
    "Protein Foods": "Protein",
    "Beans and Legumes": "Beans",
    "Fruits": "Fruits",
    "Vegetables": "Veg",
    "Dairy and Alternatives": "Dairy",
    "Soups and Prepared Meals": "Soups/Meals",
    "Breakfast Foods": "Breakfast",
    "Snacks": "Snacks",
    "Beverages and Pantry Staples": "Bev/Pantry",
}

ITEM_CATEGORY: dict[str, str] = {
    item: cat for cat, items in CATALOG.items() for item in items
}

# Extra phrasings people actually type, mapped to a catalog item.
_ALIASES: dict[str, str] = {
    "tuna": "Canned tuna",
    "salmon": "Canned salmon",
    "ham": "Canned ham",
    "turkey": "Canned turkey",
    "jerky": "Beef jerky",
    "pb": "Peanut butter",
    "garbanzo": "Chickpeas",
    "chili beans": "Canned chili beans",
    "chili": "Canned chili beans",
    "peaches": "Canned peaches",
    "pears": "Canned pears",
    "pineapple": "Canned pineapple",
    "mandarin": "Canned mandarin oranges",
    "cranberries": "Dried cranberries",
    "apricots": "Dried apricots",
    "mango": "Dried mango",
    "corn": "Canned corn",
    "green beans": "Canned green beans",
    "carrots": "Canned carrots",
    "tomatoes": "Canned tomatoes",
    "spinach": "Canned spinach",
    "mushrooms": "Canned mushrooms",
    "potatoes": "Canned potatoes",
    "veggies": "Mixed vegetables",
    "vegetables": "Mixed vegetables",
    "uht milk": "Shelf-stable milk",
    "shelf stable milk": "Shelf-stable milk",
    "milk": "Shelf-stable milk",
    "meal kits": "Shelf-stable meal kits",
    "meal kit": "Shelf-stable meal kits",
    "mac and cheese": "Macaroni and cheese",
    "mac & cheese": "Macaroni and cheese",
    "ravioli": "Canned ravioli",
    "spaghetti": "Canned spaghetti",
    "noodle soup": "Chicken noodle soup",
    "water": "Bottled water",
    "juice": "Fruit juice",
    "oil": "Cooking oil",
    "jam": "Jelly or jam",
    "jelly": "Jelly or jam",
    "oats": "Oatmeal",
    "chips": "Tortilla chips",
}

# Longest phrase first so "chicken noodle soup" wins over "chicken".
_PHRASES: list[tuple[str, str]] = sorted(
    [(i.lower(), i) for i in ITEM_CATEGORY] + list(_ALIASES.items()),
    key=lambda p: len(p[0]),
    reverse=True,
)


def find_item(text: str) -> str | None:
    """Return the catalog item mentioned in free text, or None."""
    lower = text.lower()
    for phrase, item in _PHRASES:
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lower):
            return item
    return None


# --------------------------------------------------------------------------- #
# Food bank directory — organization -> city
# --------------------------------------------------------------------------- #
ORGANIZATIONS: dict[str, str] = {
    "Second Harvest of Silicon Valley": "San Jose",
    "Our Lady Star of the Sea Church": "Alviso",
    "Campbell United Methodist Church": "Campbell",
    "LifeSTEPS – Rincon Gardens": "Campbell",
    "St. Lucy Catholic Parish": "Campbell",
    "The Home Church": "Campbell",
    "West Valley Community Services": "Cupertino",
    "Union Church of Cupertino": "Cupertino",
    "West Valley Presbyterian Church": "Cupertino",
    "De Anza College Food Pantry": "Cupertino",
    "South County Community Services": "Gilroy",
    "The Salvation Army – Gilroy": "Gilroy",
    "Gavilan College Food Pantry": "Gilroy",
    "Rebekah Children’s Services": "Gilroy",
    "Christian Worship Center": "Milpitas",
    "Mt. Olive Ministries": "Milpitas",
    "Crosspoint Church of Silicon Valley": "Milpitas",
    "Muslim Sisters Helping": "Milpitas",
    "St. Catherine Church – Reachout": "Morgan Hill",
    "Community Solutions – La Casa del Puente": "Morgan Hill",
    "Community Services Agency": "Mountain View",
    "Hope’s Corner": "Mountain View",
    "Mountain View Senior Center": "Mountain View",
    "Alta Housing": "Palo Alto",
    "South Palo Alto Food Closet": "Palo Alto",
    "Downtown Food Closet of Palo Alto": "Palo Alto",
    "St. Andrew’s United Methodist Church": "Palo Alto",
    "Sacred Heart Community Service": "San Jose",
    "The Jerry Larson Food Basket": "San Jose",
    "FISH of South Valley": "San Jose",
    "True Vine Food Pantry": "San Jose",
    "CityTeam in the Neighborhood": "San Jose",
    "El Buen Pastor Food Pantry": "San Jose",
    "Loaves & Fishes Family Kitchen": "San Jose",
    "Martha’s Kitchen": "San Jose",
    "St. Justin Community Ministry": "Santa Clara",
    "Mission Market Pantry": "Santa Clara",
    "River of Life Foundation": "Santa Clara",
    "Sunnyvale Community Services": "Sunnyvale",
    "The Salvation Army – Sunnyvale": "Sunnyvale",
    "Our Daily Bread": "Sunnyvale",
    "Corner Pantry": "Sunnyvale",
    "Coastside Hope": "Half Moon Bay",
    "Pacifica Resource Center – Buel": "Pacifica",
    "Ecumenical Hunger Program": "East Palo Alto",
    "WeHOPE": "East Palo Alto",
    "Daly City Partnership": "Daly City",
    "St. Vincent de Paul – St. Pius": "Redwood City",
    "The Salvation Army – Redwood City": "Redwood City",
    "St. Francis Center": "Redwood City",
}


def _norm(name: str) -> str:
    """Normalize an org name: lowercase, unify dashes/apostrophes, drop punctuation."""
    n = name.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


_ORG_INDEX: dict[str, str] = {_norm(o): o for o in ORGANIZATIONS}


def resolve_org(name: str) -> tuple[str, str]:
    """Map a typed org name to (canonical name, city). Unknown orgs keep their name."""
    canonical = _ORG_INDEX.get(_norm(name))
    if canonical:
        return canonical, ORGANIZATIONS[canonical]
    return name.strip() or "Unknown organization", "Unknown"
