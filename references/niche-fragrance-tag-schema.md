# Niche Essences fragrance tag schema v1

This additive Shopify taxonomy is generated from the first-party product title,
description, type, and existing tags in `shopify_products_nicheessences_com.csv`.
It applies to individual Eau de Parfum products, including their 5 ml travel-size
counterparts. Bundles, build-your-own products, body care, and promotional products
are excluded.

## Namespaces

| Dimension | Format | Examples | Cardinality |
|---|---|---|---|
| Taxonomy version | `niche:taxonomy:v1` | `niche:taxonomy:v1` | Exactly 1 |
| Audience | `niche:audience:<value>` | `male`, `female`, `unisex` | Exactly 1 |
| Notes | `niche:note:<note>` | `bergamot`, `rose`, `vanilla`, `oud` | One or more |
| Season | `niche:season:<value>` | `spring`, `summer`, `autumn`, `winter`, `all-season` | 1–2 |
| Time | `niche:time:<value>` | `day`, `evening`, `night`, `day-to-night` | 1–2 |
| Occasion | `niche:occasion:<value>` | `everyday`, `office`, `date-night`, `formal`, `party`, `special-occasion`, `signature-scent` | 1–4 |

## Interpretation rules

- Audience is derived from explicit catalog language first. If the description does
  not gender a fragrance, it is tagged `unisex`; this avoids inventing a gender claim.
- Notes are normalized from exact note mentions and broad accords in the description.
  Plurals and common variants map to one canonical slug.
- Explicit season, time, and occasion statements override profile inference.
- When usage language is absent, fresh/citrus/aquatic profiles lean day and
  spring/summer; amber/vanilla/oud/tobacco/spicy profiles lean evening/night and
  autumn/winter; balanced profiles receive `all-season` and `day-to-night`.
- Existing merchant tags are never removed or rewritten.
- Managed taxonomy tags can be regenerated safely: the sync removes only previous
  `niche:audience:`, `niche:note:`, `niche:season:`, `niche:time:`,
  `niche:occasion:`, and `niche:taxonomy:` tags before applying the current result.

## Shopify usage

These tags are suitable for Search & Discovery filters, automated collections,
finder logic, product recommendations, and future metafield migration. Customer-facing
labels should be formatted in the theme rather than exposing raw tag strings.
