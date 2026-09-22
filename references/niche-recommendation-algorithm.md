# Niche Essences recommendation model v1

## Data relationships

- A bundle is identified from its title, handle, or merchant bundle/set tags.
- Bundle copy is matched against the canonical fragrance names in the CSV.
- Each matched bundle receives a stable relation tag: `niche:bundle:<bundle-handle>`.
- The bundle receives `niche:bundle-role:bundle`; each component receives
  `niche:bundle-role:member`.
- Each component receives `niche:sibling:<product-handle>` tags for the other
  perfumes in the same bundle. Sibling relations are reciprocal.
- Dynamic “Build Your Own” offers are not assigned fixed members because their
  contents are selected by the customer.
- A product’s tester recommendations are its 5 ml variant counterparts and the
  5 ml counterparts of its bundle co-members.

## Similarity score

For a target individual fragrance and each full-size individual candidate:

```text
score = audience_match * 8
      + min(shared_notes, 8) * 2
      + shared_seasons * 3
      + shared_times * 2
      + shared_occasions * 1
      + shared_bundle * 7
```

The candidate’s own full-size product and its 5 ml counterpart are excluded. The
highest four scores become `custom.recommendation_handles` as a Shopify list
metafield. Bundle co-members receive the bundle bonus, so the model supports both
discovery and AOV-oriented cross-sell.

## Shopify fields

| Namespace/key | Type | Meaning |
|---|---|---|
| `custom.bundle_handles` | list.single_line_text_field | Bundles containing this product |
| `custom.bundle_member_handles` | list.single_line_text_field | Members of a bundle product |
| `custom.sibling_handles` | list.single_line_text_field | Perfumes in the same bundle |
| `custom.tester_handles` | list.single_line_text_field | Relevant 5 ml testers |
| `custom.recommendation_handles` | list.single_line_text_field | Scored top four full-size recommendations |
| `custom.recommendation_algorithm` | single_line_text_field | `tag-similarity-v1` |

The relation tags remain on the products as a fallback for Shopify Search &
Discovery filters and Liquid logic. Existing merchant tags are preserved.

To export the current bundle, child, and sibling relations to every matching
row in the Shopify product CSV, run:

```text
python3 scripts/shopify_recommendations_sync.py --export-csv
```
