#!/usr/bin/env python3
"""Add namespaced catalog tags and create tag-driven Shopify collections.

Existing product tags are preserved. Credentials are read from the workspace .env.
Run with --dry-run to audit the planned changes without mutating Shopify.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "shopify_products_nicheessences_com.csv"
ENV_PATH = ROOT / ".env"
API_VERSION = "2026-07"

COLLECTIONS = (
    ("Eau de Parfum", "eau-de-parfum", "niche:format:eau-de-parfum"),
    ("5ml Travel Sizes", "5ml-travel-sizes", "niche:size:5ml"),
    ("Body Splashes", "body-splashes", "niche:format:body-splash"),
    ("Perfumed Body Lotions", "perfumed-body-lotions", "niche:format:body-lotion"),
    ("Fragrance Sets", "fragrance-sets", "niche:category:set"),
    ("Layering Sets", "layering-sets", "niche:set-type:layering"),
    ("For Him", "for-him", "niche:audience:him"),
    ("For Her", "for-her", "niche:audience:her"),
    ("Unisex", "unisex", "niche:audience:unisex"),
    ("Summer Edit", "summer-edit", "niche:season:summer"),
    ("Winter Edit", "winter-edit", "niche:season:winter"),
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_csv_products(path: Path) -> dict[str, dict[str, str]]:
    products: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            product_handle = row.get("Handle", "").strip()
            if product_handle and product_handle not in products:
                products[product_handle] = row
    return products


def classify(row: dict[str, str]) -> list[str]:
    title = row.get("Title", "").strip()
    handle = row.get("Handle", "").strip()
    product_type = row.get("Type", "").strip().lower()
    source_tags = {tag.strip().lower() for tag in row.get("Tags", "").split(",") if tag.strip()}
    signal = f"{title} {handle}".lower()
    tags = {"niche:catalog:managed"}

    is_travel = "5ml" in signal or "travel size" in signal
    is_body_splash = product_type == "body splash" or "body splash" in signal
    is_body_lotion = "body lotion" in product_type or "body lotion" in signal
    is_set = any(term in signal for term in (" set", "-set", "trio", "build your own")) or "bundle" in source_tags

    if is_body_splash:
        tags.update(("niche:category:body-care", "niche:format:body-splash"))
    elif is_body_lotion:
        tags.update(("niche:category:body-care", "niche:format:body-lotion", "niche:size:120ml"))
    elif is_set:
        tags.add("niche:category:set")
    else:
        tags.add("niche:category:fragrance")

    if not is_set and (product_type == "eau de parfum" or "eau de parfum" in signal or is_travel):
        tags.add("niche:format:eau-de-parfum")
    if is_travel:
        tags.add("niche:size:5ml")
    if "layering" in signal:
        tags.add("niche:set-type:layering")
    if "gift" in signal:
        tags.add("niche:set-type:gift")
    if "trio" in signal:
        tags.add("niche:set-type:trio")
    if "build your own" in signal:
        tags.add("niche:set-type:build-your-own")

    has_him = bool(re.search(r"\bfor him\b", signal))
    has_her = bool(re.search(r"\bfor her\b", signal))
    if "unisex" in signal or (has_him and has_her):
        tags.add("niche:audience:unisex")
    elif has_him:
        tags.add("niche:audience:him")
    elif has_her:
        tags.add("niche:audience:her")
    elif not is_set:
        tags.add("niche:audience:unisex")

    if "summer" in signal or "sahel" in signal or "sa7el" in signal:
        tags.add("niche:season:summer")
    if "winter" in signal:
        tags.add("niche:season:winter")

    return sorted(tags)


class ShopifyAdmin:
    def __init__(self, domain: str, token: str) -> None:
        clean_domain = domain.removeprefix("https://").rstrip("/")
        self.endpoint = f"https://{clean_domain}/admin/api/{API_VERSION}/graphql.json"
        self.token = token

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "X-Shopify-Access-Token": self.token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(error.read().decode()) from error
        if result.get("errors"):
            raise RuntimeError(json.dumps(result["errors"], indent=2))
        return result["data"]

    def products(self) -> dict[str, dict]:
        query = """
        query Products($cursor: String) {
          products(first: 250, after: $cursor) {
            nodes { id handle title tags }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        items: dict[str, dict] = {}
        cursor = None
        while True:
            connection = self.graphql(query, {"cursor": cursor})["products"]
            items.update({node["handle"]: node for node in connection["nodes"]})
            if not connection["pageInfo"]["hasNextPage"]:
                return items
            cursor = connection["pageInfo"]["endCursor"]

    def collections(self) -> dict[str, dict]:
        query = """
        query Collections {
          collections(first: 250) { nodes { id handle title } }
        }
        """
        return {node["handle"]: node for node in self.graphql(query)["collections"]["nodes"]}

    def add_tags(self, product_id: str, tags: list[str]) -> None:
        mutation = """
        mutation AddTags($id: ID!, $tags: [String!]!) {
          tagsAdd(id: $id, tags: $tags) { userErrors { field message } }
        }
        """
        errors = self.graphql(mutation, {"id": product_id, "tags": tags})["tagsAdd"]["userErrors"]
        if errors:
            raise RuntimeError(json.dumps(errors))

    def create_collection(self, title: str, handle: str, tag: str) -> str:
        mutation = """
        mutation CreateCollection($input: CollectionInput!) {
          collectionCreate(input: $input) {
            collection { id handle title }
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "title": title,
                "handle": handle,
                "ruleSet": {
                    "appliedDisjunctively": False,
                    "rules": [{"column": "TAG", "relation": "EQUALS", "condition": tag}],
                },
            }
        }
        payload = self.graphql(mutation, variables)["collectionCreate"]
        if payload["userErrors"]:
            raise RuntimeError(json.dumps(payload["userErrors"]))
        return payload["collection"]["id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = read_env(ENV_PATH)
    api = ShopifyAdmin(env["store_url"], env["store_access_token"])
    csv_products = load_csv_products(CSV_PATH)
    live_products = api.products()
    live_collections = api.collections()

    missing_live = sorted(set(csv_products) - set(live_products))
    missing_csv = sorted(set(live_products) - set(csv_products))
    if missing_live or missing_csv:
        raise RuntimeError(
            f"Catalog mismatch; refusing mutation. Missing live={missing_live}, missing CSV={missing_csv}"
        )

    planned: list[tuple[dict, list[str]]] = []
    tag_counts: dict[str, int] = {}
    for handle, row in csv_products.items():
        desired = classify(row)
        existing = set(live_products[handle]["tags"])
        additions = [tag for tag in desired if tag not in existing]
        if additions:
            planned.append((live_products[handle], additions))
        for tag in desired:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    print(f"CSV products: {len(csv_products)}; live products: {len(live_products)}")
    print(f"Products requiring new tags: {len(planned)}")
    for tag, count in sorted(tag_counts.items()):
        print(f"  {tag}: {count}")
    new_collections = [item for item in COLLECTIONS if item[1] not in live_collections]
    print(f"Collections to create: {len(new_collections)}")
    for title, handle, tag in new_collections:
        print(f"  {title} ({handle}) <- {tag}")

    if args.dry_run:
        print("DRY RUN: no Shopify data changed")
        return

    for index, (product, additions) in enumerate(planned, start=1):
        api.add_tags(product["id"], additions)
        if index % 25 == 0 or index == len(planned):
            print(f"Tagged {index}/{len(planned)} products")
        time.sleep(0.03)

    for title, handle, tag in new_collections:
        collection_id = api.create_collection(title, handle, tag)
        print(f"Created {title}: {collection_id}")

    print("Catalog organization complete")


if __name__ == "__main__":
    main()
