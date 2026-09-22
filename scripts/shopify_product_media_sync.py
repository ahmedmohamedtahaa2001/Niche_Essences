#!/usr/bin/env python3
"""Publish Midnight Apothecary imagery as primary product media.

Existing product images are retained as secondary media. Re-running the script
reuses the generated image when its managed alt text already exists.
"""

from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from shopify_catalog_organizer import API_VERSION, ENV_PATH, ShopifyAdmin, read_env


ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = ROOT / "assets" / "product-image-redesign" / "generated"
PRODUCT_MEDIA = (
    (
        "tonka-prive-by-niche-eau-de-parfum-inspired-by-montales-arabians-tonka",
        "tonka-prive-midnight-apothecary-v1.png",
        "Tonka Prive Eau de Parfum — Midnight Apothecary product image",
    ),
    (
        "le-rouge-by-niche-100-ml",
        "le-rouge-midnight-apothecary-v1.png",
        "Le Rouge Eau de Parfum — Midnight Apothecary product image",
    ),
    (
        "vanille-intense-by-niche-eau-de-parfum-inspired-by-montales-dark-vanilla",
        "vanille-intense-midnight-apothecary-v1.png",
        "Vanille Intense Eau de Parfum — Midnight Apothecary product image",
    ),
    (
        "the-yachter-by-niche-eau-de-parfum",
        "the-yachter-midnight-apothecary-v1.png",
        "The Yachter Eau de Parfum — Midnight Apothecary product image",
    ),
    (
        "flesh-flame-by-niche-eau-de-parfum-inspired-by-stephane-humbert-lucass-god-of-fire",
        "flesh-flame-midnight-apothecary-v1.png",
        "Flesh and Flame Eau de Parfum — Midnight Apothecary product image",
    ),
    (
        "vanilla-cigar-by-niche-eau-de-parfum-inspired-by-tom-fords-tobacco-vanille",
        "vanilla-cigar-midnight-apothecary-v1.png",
        "Vanilla Cigar Eau de Parfum — Midnight Apothecary product image",
    ),
)


def request_json(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode()) from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    missing_files = [filename for _, filename, _ in PRODUCT_MEDIA if not (IMAGE_ROOT / filename).is_file()]
    if missing_files:
        raise RuntimeError(f"Missing generated files: {missing_files}")

    env = read_env(ENV_PATH)
    admin = ShopifyAdmin(env["store_url"], env["store_access_token"])
    products = admin.products()
    missing_products = [handle for handle, _, _ in PRODUCT_MEDIA if handle not in products]
    if missing_products:
        raise RuntimeError(f"Missing Shopify products: {missing_products}")

    domain = env["store_url"].removeprefix("https://").rstrip("/")
    base = f"https://{domain}/admin/api/{API_VERSION}"
    token = env["store_access_token"]

    for handle, filename, alt_text in PRODUCT_MEDIA:
        product = products[handle]
        product_id = int(product["id"].rsplit("/", 1)[-1])
        images_url = f"{base}/products/{product_id}/images.json"
        images = request_json(images_url, token).get("images", [])
        managed = next((image for image in images if image.get("alt") == alt_text), None)

        if args.dry_run:
            action = "reorder existing" if managed else "upload new"
            print(f"DRY RUN: {product['title']}: {action} {filename} at position 1")
            continue

        if managed:
            image_id = managed["id"]
            result = request_json(
                f"{base}/products/{product_id}/images/{image_id}.json",
                token,
                "PUT",
                {"image": {"id": image_id, "position": 1, "alt": alt_text}},
            )["image"]
            action = "Reordered"
        else:
            encoded = base64.b64encode((IMAGE_ROOT / filename).read_bytes()).decode("ascii")
            result = request_json(
                images_url,
                token,
                "POST",
                {
                    "image": {
                        "attachment": encoded,
                        "filename": filename,
                        "alt": alt_text,
                        "position": 1,
                    }
                },
            )["image"]
            action = "Uploaded"

        verified = request_json(images_url, token).get("images", [])
        if not verified or verified[0]["id"] != result["id"]:
            raise RuntimeError(f"Primary image verification failed for {product['title']}")
        print(f"{action}: {product['title']} -> image {result['id']} at position 1; {len(verified)} media retained")


if __name__ == "__main__":
    main()
