#!/usr/bin/env python3
"""Build bundle relations and tag-scored recommendation metafields."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from shopify_catalog_organizer import ENV_PATH, ShopifyAdmin, read_env
from shopify_fragrance_taxonomy_sync import catalog, clean_text, is_fragrance, profile_key


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "recommendation-relations-v1.json"
RELATION_PREFIXES = ("niche:bundle:", "niche:bundle-role:", "niche:sibling:")
PROMO_ONLY = ("buy ", "complimentary", "build your")


def plain(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return clean_text(value)


def is_bundle(row: dict[str, str]) -> bool:
    merchant_tags = ", ".join(
        tag for tag in row.get("Tags", "").split(",")
        if not tag.strip().lower().startswith("niche:")
    )
    signal = plain(" ".join((row.get("Title", ""), row.get("Handle", ""), merchant_tags)))
    return (
        any(token in signal for token in ("bundle", "set", "trio", "layering", "build your"))
        or "maxbundle" in signal
    )


def canonical_name(title: str) -> str:
    return plain(profile_key(title))


def source_text(row: dict[str, str]) -> str:
    return plain(" ".join((row.get("Title", ""), row.get("Tags", ""), row.get("Body (HTML)", ""))))


def match_bundle_members(bundle: dict[str, str], names: list[str], name_to_handles: dict[str, list[str]]) -> list[str]:
    body = source_text(bundle)
    members: list[str] = []
    for name in sorted(names, key=len, reverse=True):
        if len(name) < 4:
            continue
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", body):
            full = [handle for handle in name_to_handles[name] if "5ml" not in handle and "travel" not in handle]
            if full:
                members.append(full[0])
    return list(dict.fromkeys(members))


def load_taxonomy() -> dict[str, dict[str, set[str]]]:
    path = ROOT / "reports" / "fragrance-taxonomy-v1.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        result = {}
        for row in rows:
            result[row["handle"]] = {
                "audience": {row["audience"]},
                "notes": set(filter(None, row["notes"].split(", "))),
                "seasons": set(filter(None, row["seasons"].split(", "))),
                "times": set(filter(None, row["times"].split(", "))),
                "occasions": set(filter(None, row["occasions"].split(", "))),
            }
    return result


def build_model() -> dict:
    rows = catalog()
    individual = {handle: row for handle, row in rows.items() if is_fragrance(row)}
    bundles = {handle: row for handle, row in rows.items() if is_bundle(row)}
    name_to_handles: dict[str, list[str]] = defaultdict(list)
    profile_handles: dict[str, list[str]] = defaultdict(list)
    for handle, row in individual.items():
        name_to_handles[canonical_name(row["Title"])].append(handle)
        profile_handles[profile_key(row["Title"])].append(handle)

    names = list(name_to_handles)
    bundle_members: dict[str, list[str]] = {}
    for bundle_handle, bundle in bundles.items():
        if any(token in plain(bundle["Title"]) for token in PROMO_ONLY):
            continue
        members = match_bundle_members(bundle, names, name_to_handles)
        if len(members) >= 2:
            bundle_members[bundle_handle] = members

    product_bundles: dict[str, set[str]] = defaultdict(set)
    for bundle_handle, members in bundle_members.items():
        for member in members:
            product_bundles[member].add(bundle_handle)

    sibling_handles: dict[str, set[str]] = defaultdict(set)
    for members in bundle_members.values():
        for member in members:
            sibling_handles[member].update(other for other in members if other != member)

    full_handles = [handle for handle, row in individual.items() if "5ml" not in handle and "travel" not in handle]
    travel_by_profile: dict[str, list[str]] = defaultdict(list)
    for handle, row in individual.items():
        if "5ml" in handle or "travel" in handle:
            travel_by_profile[profile_key(row["Title"])].append(handle)

    taxonomy = load_taxonomy()
    recommendation_handles: dict[str, list[str]] = {}
    tester_handles: dict[str, list[str]] = {}
    for handle in individual:
        if handle not in taxonomy:
            continue
        target = taxonomy[handle]
        target_profile = profile_key(individual[handle]["Title"])
        if "5ml" not in handle and "travel" not in handle:
            scored = []
            for candidate in full_handles:
                if candidate == handle or profile_key(individual[candidate]["Title"]) == target_profile:
                    continue
                profile = taxonomy.get(candidate)
                if not profile:
                    continue
                score = 0
                score += 8 if target["audience"] & profile["audience"] else 0
                score += min(len(target["notes"] & profile["notes"]), 8) * 2
                score += len(target["seasons"] & profile["seasons"]) * 3
                score += len(target["times"] & profile["times"]) * 2
                score += len(target["occasions"] & profile["occasions"])
                if product_bundles[handle] & product_bundles[candidate]:
                    score += 7
                scored.append((score, candidate))
            scored.sort(key=lambda item: (-item[0], item[1]))
            recommendation_handles[handle] = [candidate for _, candidate in scored[:4]]

        tester_pool: list[str] = []
        for bundle_handle in product_bundles[handle]:
            for member in bundle_members[bundle_handle]:
                tester_pool.extend(travel_by_profile[profile_key(individual[member]["Title"])])
        for candidate in recommendation_handles.get(handle, []):
            tester_pool.extend(travel_by_profile[profile_key(individual[candidate]["Title"])])
        tester_handles[handle] = list(dict.fromkeys(tester_pool))[:4]

    record = {
        "bundles": bundle_members,
        "product_bundles": {handle: sorted(value) for handle, value in product_bundles.items()},
        "sibling_handles": {handle: sorted(value) for handle, value in sibling_handles.items()},
        "recommendation_handles": recommendation_handles,
        "tester_handles": tester_handles,
    }
    return {
        "rows": rows,
        "individual": individual,
        "bundles": bundles,
        "bundle_members": bundle_members,
        "product_bundles": product_bundles,
        "sibling_handles": sibling_handles,
        "recommendation_handles": recommendation_handles,
        "tester_handles": tester_handles,
        "record": record,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--export-csv", action="store_true", help="Export bundle and sibling relation tags to the product CSV")
    args = parser.parse_args()
    model = build_model()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(model["record"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Bundle relations: {len(model['bundle_members'])}")
    print(f"Individual products: {len(model['individual'])}")
    print(f"Similarity profiles: {len(model['recommendation_handles'])}")
    print(f"Relations report: {REPORT_PATH}")
    for bundle, members in list(model["bundle_members"].items())[:8]:
        print(f"  {bundle}: {', '.join(members)}")
    if args.export_csv:
        relation_tags: dict[str, set[str]] = defaultdict(set)
        for bundle_handle, members in model["bundle_members"].items():
            relation_tags[bundle_handle].update((f"niche:bundle:{bundle_handle}", "niche:bundle-role:bundle"))
            for member in members:
                relation_tags[member].update((f"niche:bundle:{bundle_handle}", "niche:bundle-role:member"))
        for handle, siblings in model["sibling_handles"].items():
            relation_tags[handle].update(f"niche:sibling:{sibling}" for sibling in siblings)

        csv_path = ROOT / "shopify_products_nicheessences_com.csv"
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            csv_rows = list(reader)
            fieldnames = reader.fieldnames
        exported_rows = 0
        for row in csv_rows:
            desired = relation_tags.get(row["Handle"])
            if not desired:
                continue
            preserved = [tag.strip() for tag in row["Tags"].split(",") if tag.strip() and not tag.strip().startswith(RELATION_PREFIXES)]
            row["Tags"] = ", ".join(preserved + sorted(desired))
            exported_rows += 1
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"Exported relation tags to {exported_rows} CSV rows")
    if not args.apply:
        print("AUDIT ONLY: no Shopify data changed. Re-run with --apply after review.")
        return

    env = read_env(ENV_PATH)
    admin = ShopifyAdmin(env["store_url"], env["store_access_token"])
    live = admin.products()
    missing = sorted((set(model["rows"]) & (set(model["individual"]) | set(model["bundles"]))) - set(live))
    if missing:
        raise RuntimeError(f"Missing live products: {missing}")

    all_relations: dict[str, set[str]] = defaultdict(set)
    for bundle_handle, members in model["bundle_members"].items():
        all_relations[bundle_handle].add(f"niche:bundle:{bundle_handle}")
        all_relations[bundle_handle].add("niche:bundle-role:bundle")
        for member in members:
            all_relations[member].add(f"niche:bundle:{bundle_handle}")
            all_relations[member].add("niche:bundle-role:member")
    for handle, siblings in model["sibling_handles"].items():
        all_relations[handle].update(f"niche:sibling:{sibling}" for sibling in siblings)

    update_mutation = """
    mutation UpdateRecommendationTags($product: ProductUpdateInput!) {
      productUpdate(product: $product) {
        product { id handle tags }
        userErrors { field message }
      }
    }
    """
    metafield_mutation = """
    mutation SetRecommendationMetafields($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { namespace key value }
        userErrors { field message code }
      }
    }
    """
    handles_to_update = sorted(set(model["individual"]) | set(model["bundle_members"]))
    for index, handle in enumerate(handles_to_update, start=1):
        product = live[handle]
        preserved = [tag for tag in product["tags"] if not tag.startswith(RELATION_PREFIXES)]
        final_tags = preserved + sorted(all_relations[handle])
        tag_result = admin.graphql(update_mutation, {"product": {"id": product["id"], "tags": final_tags}})["productUpdate"]
        if tag_result["userErrors"]:
            raise RuntimeError(json.dumps(tag_result["userErrors"], indent=2))

        bundle_handles = sorted(model["product_bundles"].get(handle, set()))
        member_handles = model["bundle_members"].get(handle, [])
        metafields = [
            {"ownerId": product["id"], "namespace": "custom", "key": "bundle_handles", "type": "list.single_line_text_field", "value": json.dumps(bundle_handles)},
            {"ownerId": product["id"], "namespace": "custom", "key": "bundle_member_handles", "type": "list.single_line_text_field", "value": json.dumps(member_handles)},
            {"ownerId": product["id"], "namespace": "custom", "key": "sibling_handles", "type": "list.single_line_text_field", "value": json.dumps(sorted(model["sibling_handles"].get(handle, set())))},
            {"ownerId": product["id"], "namespace": "custom", "key": "tester_handles", "type": "list.single_line_text_field", "value": json.dumps(model["tester_handles"].get(handle, []))},
            {"ownerId": product["id"], "namespace": "custom", "key": "recommendation_handles", "type": "list.single_line_text_field", "value": json.dumps(model["recommendation_handles"].get(handle, []))},
            {"ownerId": product["id"], "namespace": "custom", "key": "recommendation_algorithm", "type": "single_line_text_field", "value": "tag-similarity-v1"},
        ]
        meta_result = admin.graphql(metafield_mutation, {"metafields": metafields})["metafieldsSet"]
        if meta_result["userErrors"]:
            raise RuntimeError(json.dumps(meta_result["userErrors"], indent=2))
        if index % 20 == 0 or index == len(handles_to_update):
            print(f"Updated relations {index}/{len(handles_to_update)}")
        time.sleep(0.04)
    print("Recommendation relation sync complete")


if __name__ == "__main__":
    main()
