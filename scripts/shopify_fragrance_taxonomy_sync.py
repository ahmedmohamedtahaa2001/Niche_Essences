#!/usr/bin/env python3
"""Generate and sync namespaced fragrance taxonomy tags to Shopify."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from collections import Counter
from pathlib import Path

from shopify_catalog_organizer import ENV_PATH, ShopifyAdmin, read_env


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "shopify_products_nicheessences_com.csv"
REPORT_PATH = ROOT / "reports" / "fragrance-taxonomy-v1.csv"
MANAGED_PREFIXES = (
    "niche:taxonomy:",
    "niche:audience:",
    "niche:note:",
    "niche:season:",
    "niche:time:",
    "niche:occasion:",
)
BUNDLE_SIGNALS = (
    "bundle", "build your own", "tailor your", "fragrance set", "perfume set",
    "layering set", "trio", "buy 2", "buy 3", "buy 4", "buy 5", "buy 6",
    "complimentary", "gift set", "summer set", "winter set",
)

NOTE_PATTERNS = {
    "aldehydes": ("aldehyde", "aldehydic"),
    "amber": ("amber", "ambery"),
    "ambergris": ("ambergris",),
    "ambroxan": ("ambroxan",),
    "apple": ("apple",),
    "benzoin": ("benzoin",),
    "bergamot": ("bergamot",),
    "black-currant": ("black currant", "blackcurrant", "cassis"),
    "blackberry": ("blackberry", "blackberries"),
    "cardamom": ("cardamom",),
    "caramel": ("caramel",),
    "cedar": ("cedar", "cedarwood"),
    "cherry": ("cherry", "cherries"),
    "cinnamon": ("cinnamon",),
    "citrus-accord": ("citrus",),
    "clove": ("clove",),
    "coconut": ("coconut",),
    "coffee": ("coffee", "café", "cafe"),
    "coumarin": ("coumarin",),
    "fig": ("fig",),
    "floral-accord": ("floral", "florals", "flower bouquet"),
    "fruity-accord": ("fruity", "juicy fruits", "exotic fruits", "red fruits"),
    "gardenia": ("gardenia",),
    "ginger": ("ginger",),
    "grapefruit": ("grapefruit",),
    "green-notes": ("green notes", "green accord", "leafy"),
    "honey": ("honey",),
    "incense": ("incense", "frankincense"),
    "iris": ("iris", "orris"),
    "jasmine": ("jasmine",),
    "lavender": ("lavender",),
    "leather": ("leather", "leathery"),
    "lemon": ("lemon",),
    "lily": ("lily", "water lily"),
    "mandarin": ("mandarin", "tangerine"),
    "mango": ("mango",),
    "marine-accord": ("marine", "sea breeze", "salty", "oceanic", "aquatic"),
    "moss": ("oakmoss", "moss", "mossy"),
    "musk": ("musk", "musky"),
    "neroli": ("neroli", "orange blossom"),
    "oud": ("oud", "agarwood"),
    "patchouli": ("patchouli",),
    "peach": ("peach",),
    "pear": ("pear",),
    "pepper": ("pink pepper", "black pepper", "peppery", "pepper"),
    "pineapple": ("pineapple",),
    "plum": ("plum",),
    "praline": ("praline",),
    "raspberry": ("raspberry", "raspberries"),
    "resins": ("resin", "resinous", "labdanum", "myrrh"),
    "rose": ("rose",),
    "rum": ("rum", "cognac", "boozy"),
    "saffron": ("saffron",),
    "sage": ("sage",),
    "sandalwood": ("sandalwood",),
    "smoke": ("smoky", "smoke"),
    "spicy-accord": ("spicy", "warm spice", "aromatic spices"),
    "sugar-cane": ("sugar cane",),
    "tobacco": ("tobacco",),
    "tonka-bean": ("tonka",),
    "tuberose": ("tuberose",),
    "vanilla": ("vanilla", "vanillic"),
    "vetiver": ("vetiver",),
    "violet": ("violet",),
    "woody-accord": ("woody", "woods", "precious wood", "warm wood"),
    "ylang-ylang": ("ylang ylang", "ylang-ylang"),
}

FRESH_NOTES = {
    "aldehydes", "apple", "bergamot", "citrus-accord", "fig", "grapefruit",
    "green-notes", "lavender", "lemon", "lily", "mandarin", "marine-accord",
    "neroli", "pear", "pineapple", "sage", "vetiver",
}
WARM_NOTES = {
    "amber", "ambergris", "benzoin", "caramel", "cardamom", "cherry", "cinnamon",
    "clove", "coffee", "honey", "incense", "leather", "musk", "oud", "patchouli",
    "pepper", "praline", "resins", "rum", "saffron", "sandalwood", "smoke",
    "spicy-accord", "tobacco", "tonka-bean", "vanilla", "woody-accord",
}


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip().lower()


def contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z]){re.escape(phrase.lower())}(?![a-z])", text))


def is_fragrance(row: dict[str, str]) -> bool:
    if row.get("Type", "").strip().lower() != "eau de parfum":
        return False
    merchant_tags = ", ".join(
        tag for tag in row.get("Tags", "").split(",")
        if not tag.strip().lower().startswith("niche:")
    )
    signal = clean_text(" ".join((row.get("Title", ""), row.get("Handle", ""), merchant_tags)))
    return not any(term in signal for term in BUNDLE_SIGNALS)


def audience(text: str) -> str:
    if contains(text, "unisex"):
        return "unisex"
    female = any(contains(text, phrase) for phrase in ("women's fragrance", "woman's fragrance", "for women", "for her", "feminine fragrance", "femininity", "feminine"))
    male = any(contains(text, phrase) for phrase in ("men's fragrance", "man's fragrance", "for men", "for him", "masculine fragrance", "masculinity", "masculine"))
    if female and not male:
        return "female"
    if male and not female:
        return "male"
    return "unisex"


def notes(text: str) -> list[str]:
    found = []
    for slug, patterns in NOTE_PATTERNS.items():
        if any(contains(text, pattern) for pattern in patterns):
            found.append(slug)
    return found


def seasons(text: str, found_notes: set[str]) -> list[str]:
    explicit = []
    for season in ("spring", "summer", "autumn", "winter"):
        aliases = (season, "fall") if season == "autumn" else (season,)
        if any(contains(text, alias) for alias in aliases):
            explicit.append(season)
    if contains(text, "year round") or contains(text, "all season"):
        return ["all-season"]
    if explicit:
        return explicit[:2]
    if "marine-accord" in found_notes and any(contains(text, phrase) for phrase in ("coastal", "ocean", "open seas", "sea water", "sun-drenched")):
        return ["spring", "summer"]
    fresh = len(found_notes & FRESH_NOTES)
    warm = len(found_notes & WARM_NOTES)
    if fresh >= warm + 2:
        return ["spring", "summer"]
    if warm >= fresh + 2:
        return ["autumn", "winter"]
    return ["all-season"]


def times(text: str, found_notes: set[str]) -> list[str]:
    transition = any(contains(text, phrase) for phrase in ("day to night", "day or night", "day into night"))
    transition = transition or (contains(text, "day") and contains(text, "night") and any(word in text for word in ("transition", "from", "into")))
    if transition:
        return ["day-to-night"]
    explicit = []
    if any(contains(text, phrase) for phrase in ("daytime", "during the day", "day wear", "sunlit days")):
        explicit.append("day")
    if any(contains(text, phrase) for phrase in ("evening", "evenings", "after dark")):
        explicit.append("evening")
    if any(contains(text, phrase) for phrase in ("nighttime", "night out", "nights out", "late night")):
        explicit.append("night")
    if explicit:
        return list(dict.fromkeys(explicit))[:2]
    fresh = len(found_notes & FRESH_NOTES)
    warm = len(found_notes & WARM_NOTES)
    if fresh >= warm + 2:
        return ["day"]
    if warm >= fresh + 2:
        return ["evening", "night"]
    return ["day-to-night"]


def occasions(text: str, found_notes: set[str], time_tags: list[str]) -> list[str]:
    result = []
    patterns = {
        "office": ("office", "professional", "workday", "work wear", "meeting"),
        "everyday": ("everyday", "every day", "daily wear", "daily scent"),
        "casual": ("casual", "relaxed"),
        "date-night": ("date night", "romantic", "seductive", "intimate"),
        "formal": ("formal", "black tie", "business meeting"),
        "party": ("party", "club", "celebration", "nightlife"),
        "special-occasion": ("special occasion", "special moments", "event", "gala"),
        "vacation": ("vacation", "holiday", "beach getaway"),
        "signature-scent": ("signature scent", "signature fragrance"),
    }
    for slug, phrases in patterns.items():
        if any(contains(text, phrase) for phrase in phrases):
            result.append(slug)
    fresh = len(found_notes & FRESH_NOTES)
    warm = len(found_notes & WARM_NOTES)
    if not result:
        if fresh >= warm + 2:
            result.extend(("everyday", "office", "casual"))
        elif warm >= fresh + 2:
            result.extend(("date-night", "special-occasion"))
        else:
            result.extend(("everyday", "signature-scent"))
    elif "everyday" not in result and ("day" in time_tags or "day-to-night" in time_tags) and len(result) < 4:
        result.append("everyday")
    return list(dict.fromkeys(result))[:4]


def profile_key(title: str) -> str:
    value = clean_text(title)
    value = re.sub(r"\s*-\s*(?:5ml travel size|eau de parfum|eau de parfum \d+\s*ml)\s*$", "", value)
    return value.strip()


def profile_source(row: dict[str, str]) -> str:
    return " ".join((row.get("Tags", ""), row.get("Body (HTML)", ""), row.get("SEO Description", "")))


def classify(row: dict[str, str], shared_profile: str = "") -> list[str]:
    text = clean_text(" ".join((row.get("Title", ""), shared_profile or profile_source(row))))
    found_notes = notes(text)
    season_tags = seasons(text, set(found_notes))
    time_tags = times(text, set(found_notes))
    occasion_tags = occasions(text, set(found_notes), time_tags)
    tags = ["niche:taxonomy:v1", f"niche:audience:{audience(text)}"]
    tags.extend(f"niche:note:{value}" for value in found_notes)
    tags.extend(f"niche:season:{value}" for value in season_tags)
    tags.extend(f"niche:time:{value}" for value in time_tags)
    tags.extend(f"niche:occasion:{value}" for value in occasion_tags)
    return tags


def catalog() -> dict[str, dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        products: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(handle):
            handle = row.get("Handle", "").strip()
            if not handle or not row.get("Title"):
                continue
            product = products.setdefault(handle, {})
            for key, value in row.items():
                if value and not product.get(key):
                    product[key] = value
        return products


def write_report(rows: list[dict[str, str]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("handle", "title", "audience", "notes", "seasons", "times", "occasions", "all_tags"))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply generated tags to Shopify")
    args = parser.parse_args()

    products = {handle: row for handle, row in catalog().items() if is_fragrance(row)}
    profiles: dict[str, list[str]] = {}
    for row in products.values():
        profiles.setdefault(profile_key(row["Title"]), []).append(profile_source(row))
    report_rows = []
    generated = {}
    counts = Counter()
    for handle, row in products.items():
        tags = classify(row, " ".join(profiles[profile_key(row["Title"])]))
        generated[handle] = tags
        for tag in tags:
            counts[tag] += 1
        by_prefix = lambda prefix: [tag.removeprefix(prefix) for tag in tags if tag.startswith(prefix)]
        report_rows.append({
            "handle": handle,
            "title": row["Title"],
            "audience": ", ".join(by_prefix("niche:audience:")),
            "notes": ", ".join(by_prefix("niche:note:")),
            "seasons": ", ".join(by_prefix("niche:season:")),
            "times": ", ".join(by_prefix("niche:time:")),
            "occasions": ", ".join(by_prefix("niche:occasion:")),
            "all_tags": ", ".join(tags),
        })
    write_report(report_rows)

    print(f"Individual fragrances classified: {len(products)}")
    print(f"Report: {REPORT_PATH}")
    print("Audience:", {key.removeprefix("niche:audience:"): value for key, value in sorted(counts.items()) if key.startswith("niche:audience:")})
    print("Season:", {key.removeprefix("niche:season:"): value for key, value in sorted(counts.items()) if key.startswith("niche:season:")})
    print("Time:", {key.removeprefix("niche:time:"): value for key, value in sorted(counts.items()) if key.startswith("niche:time:")})
    print("Occasion:", {key.removeprefix("niche:occasion:"): value for key, value in sorted(counts.items()) if key.startswith("niche:occasion:")})
    print(f"Distinct normalized notes: {len([key for key in counts if key.startswith('niche:note:')])}")

    if not args.apply:
        print("AUDIT ONLY: no Shopify data changed. Re-run with --apply after review.")
        return

    env = read_env(ENV_PATH)
    admin = ShopifyAdmin(env["store_url"], env["store_access_token"])
    live = admin.products()
    missing = sorted(set(products) - set(live))
    if missing:
        raise RuntimeError(f"Missing live products: {missing}")

    mutation = """
    mutation UpdateProductTags($product: ProductUpdateInput!) {
      productUpdate(product: $product) {
        product { id handle tags }
        userErrors { field message }
      }
    }
    """
    for index, (handle, desired) in enumerate(generated.items(), start=1):
        product = live[handle]
        preserved = [tag for tag in product["tags"] if not tag.startswith(MANAGED_PREFIXES)]
        final_tags = preserved + desired
        payload = admin.graphql(mutation, {"product": {"id": product["id"], "tags": final_tags}})["productUpdate"]
        if payload["userErrors"]:
            raise RuntimeError(json.dumps(payload["userErrors"], indent=2))
        if index % 20 == 0 or index == len(generated):
            print(f"Updated {index}/{len(generated)} fragrances")
        time.sleep(0.05)
    print("Fragrance taxonomy sync complete")


if __name__ == "__main__":
    main()
