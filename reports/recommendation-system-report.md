# Niche Essences Recommendation System
## Tags, Fragrance Notes, Bundles, Siblings, and Shopify Data Design

**Version:** 1.0
**Date:** 2026-09-22
**Implementation:** `tag-similarity-v1`
**Primary data source:** `shopify_products_nicheessences_com.csv`
**Live platform:** Shopify product tags, product metafields, Liquid templates, and Admin API synchronization

---

## 1. Executive Summary

Niche Essences uses a hybrid recommendation system. It combines:

1. **Normalized fragrance attributes** extracted from product copy:
   - audience
   - notes and accords
   - season
   - time of day
   - occasion

2. **Explicit catalog relationships**:
   - bundle parent to bundle child
   - perfume to sibling perfumes in the same bundle
   - full-size perfume to tester
   - perfume to scored recommendations

3. **Shopify-native storage**:
   - namespaced product tags for filtering and fallback logic
   - typed `custom` product metafields for structured Liquid access
   - CSV reports for auditing and regeneration

The system is designed so product recommendations are explainable. A recommendation is not a black-box result: it can be traced to shared notes, audience, season, time, occasion, or a shared bundle.

The current generated dataset contains:

| Metric | Current value |
|---|---:|
| Normalized fragrance profiles | 75 |
| Recognized bundles | 58 |
| Products linked to bundles | 75 |
| Products with sibling relationships | 51 |
| Full-size recommendation profiles | 63 |
| Distinct normalized notes/accords | 65 |
| Audience values | 42 unisex, 21 female, 12 male |

---

## 2. The Core Idea

A fragrance product is represented as a **profile**. The profile describes what the product smells like and when it is useful.

Example profile:

```text
Product: Regent
Audience: unisex
Notes: amber, citrus-accord, floral-accord, musk, spicy-accord, woody-accord
Seasons: autumn, winter
Times: evening, night
Occasions: everyday, formal
Bundles: The Don Juan Set For Him
Siblings: Halo, Pineapple Express
Testers: Regent 5ml, plus relevant recommendation testers
Recommendations: Pineapple Express, Tonka Prive, Blacklist, Epoch
```

The recommendation engine compares one product profile with other product profiles. It gives higher scores to candidates that share important attributes, then adds a bundle relationship bonus when two perfumes belong to the same bundle.

This creates two complementary discovery paths:

- **Similarity discovery:** “You like this scent, so you may like these similar scents.”
- **Merchandising discovery:** “This perfume belongs to this set, and these other perfumes are sold with it.”

---

## 3. Product Types in the Data Model

The catalog contains more than one kind of product. Treating all rows as interchangeable would create bad recommendations, so the system separates them.

### 3.1 Individual full-size fragrances

These are usually `Type = Eau De Parfum` and do not contain bundle signals. They are the primary recommendation candidates.

Examples:

- `regent-by-niche-eau-de-parfum-inspired-by-pdms-castley`
- `maverick-by-niche-eau-de-parfum-inspired-by-yslss-y`
- `blacklist-by-niche-eau-de-parfum-inspired-by-giorgio-armanis-noir-kogane`

### 3.2 5 ml testers

These are individual fragrance profiles whose handles or titles contain `5ml` or `travel`. They are not used as full-size similarity candidates, but they are used as tester recommendations.

Example:

- `regent-by-niche-eau-de-parfum-inspired-by-pdms-castley`
- `regent-5ml-travel-size-edp`

The two products share a profile identity through `profile_key`, which removes size suffixes from their titles.

### 3.3 Fixed bundles and sets

These are parent products with known members in their product description, title, or merchant tags.

Examples:

- `the-don-juan-set-for-him`
- `the-summer-gift-set-for-her`
- `the-seduction-layering-set-for-him`

A fixed bundle has a stable member list and can safely receive child and sibling relations.

### 3.4 Dynamic build-your-own offers

A Build Your Own offer is not assigned fixed children because the customer chooses the contents at purchase time. It may receive general catalog classification, but it must not claim a permanent fixed relationship to specific perfumes.

### 3.5 Body care and promotional products

Body splashes, lotions, and promotional offers are excluded from the fragrance similarity model unless a separate merchandising rule explicitly includes them.

---

## 4. Source Database: Shopify CSV

The CSV is a Shopify product export with repeated rows. A single product handle can appear multiple times because Shopify exports variants, images, and option combinations as separate rows.

Important consequence:

```text
624 CSV rows != 624 products
624 CSV rows = 208 unique product handles
```

The canonical product identity is the `Handle` column.

The synchronization code merges repeated rows by handle and keeps the first non-empty value for each field. This prevents a later variant/image row with blank title, body, or type from overwriting the real product metadata.

### Required source fields

| CSV field | Use |
|---|---|
| `Handle` | Stable product identifier and Shopify lookup key |
| `Title` | Product name and profile identity |
| `Body (HTML)` | Fragrance description, notes, usage signals, bundle member names |
| `Type` | Distinguishes Eau de Parfum from body care and other products |
| `Tags` | Existing merchant tags and generated taxonomy tags |
| `SEO Description` | Additional descriptive signal when available |
| `Variant SKU` | Variant-level commerce identity |
| `Variant Price` | Display and merchandising data |
| `Image Src` | Product media |
| `Status` / `Published` | Catalog availability |

### Source-of-truth principle

The CSV is an audit and generation source. Shopify is the live serving database. The safe workflow is:

```text
CSV -> classify -> generate reports -> review -> write Shopify tags/metafields -> Liquid reads Shopify
```

The storefront should not parse the CSV directly.

---

## 5. Taxonomy Tags

All generated taxonomy tags use the `niche:` namespace so they can be identified, removed, and regenerated without touching merchant-owned tags.

### 5.1 Version tag

```text
niche:taxonomy:v1
```

Exactly one taxonomy version tag should exist on every classified fragrance.

### 5.2 Audience

Format:

```text
niche:audience:<value>
```

Values:

```text
niche:audience:male
niche:audience:female
niche:audience:unisex
```

Rules:

1. Explicit language wins.
2. “Men’s fragrance”, “for him”, and “masculine fragrance” map to `male`.
3. “Women’s fragrance”, “for her”, and “feminine fragrance” map to `female`.
4. Explicit `unisex` maps to `unisex`.
5. If no reliable gender language exists, default to `unisex` rather than inventing a gender claim.

### 5.3 Notes and accords

Format:

```text
niche:note:<normalized-slug>
```

Examples:

```text
niche:note:bergamot
niche:note:rose
niche:note:vanilla
niche:note:oud
niche:note:woody-accord
niche:note:floral-accord
niche:note:fruity-accord
niche:note:marine-accord
```

The classifier uses a canonical alias table. For example:

| Source language | Canonical tag |
|---|---|
| `cedar`, `cedarwood` | `cedar` |
| `black currant`, `blackcurrant`, `cassis` | `black-currant` |
| `oakmoss`, `moss`, `mossy` | `moss` |
| `tonka`, `tonka bean` | `tonka-bean` |
| `woody`, `woods`, `precious wood` | `woody-accord` |
| `floral`, `florals`, `flower bouquet` | `floral-accord` |
| `marine`, `oceanic`, `aquatic`, `sea breeze` | `marine-accord` |

The normalization prevents spelling and wording differences from fragmenting the recommendation graph.

### 5.4 Season

Format:

```text
niche:season:<value>
```

Values:

```text
spring
summer
autumn
winter
all-season
```

Rules:

1. Explicit season statements override inference.
2. `year round` and `all season` map to `all-season`.
3. Fresh notes lean toward spring/summer.
4. Amber, vanilla, oud, tobacco, and spicy notes lean toward autumn/winter.
5. Balanced profiles receive `all-season`.
6. Maximum cardinality is two season tags.

### 5.5 Time of day

Format:

```text
niche:time:<value>
```

Values:

```text
day
evening
night
day-to-night
```

Explicit copy such as “day wear”, “evening”, and “night out” is preferred. Otherwise, fresh profiles lean day, warm profiles lean evening/night, and balanced profiles become `day-to-night`.

### 5.6 Occasion

Format:

```text
niche:occasion:<value>
```

Values currently include:

```text
everyday
office
casual
date-night
formal
party
special-occasion
vacation
signature-scent
```

Occasions are derived from explicit copy first. When copy does not state an occasion, the system uses fragrance profile inference:

- fresh profile: everyday, office, casual
- warm profile: date-night, special-occasion
- balanced profile: everyday, signature-scent

Maximum cardinality is four occasions.

---

## 6. Relationship Graph

The relationship model is a directed graph with reciprocal edges where appropriate.

### 6.1 Bundle parent -> child

A bundle is the parent. Its included perfumes are children.

```text
Bundle: The Don Juan Set For Him
  ├── Pineapple Express
  ├── Halo
  └── Regent
```

Stored as:

```text
Bundle product:
  niche:bundle-role:bundle
  niche:bundle:the-don-juan-set-for-him
  custom.bundle_member_handles = [member handles]

Child perfume:
  niche:bundle-role:member
  niche:bundle:the-don-juan-set-for-him
  custom.bundle_handles = [parent bundle handles]
```

The relation is intentionally represented in both directions. This allows Liquid to start from either a bundle or a perfume.

### 6.2 Perfume -> sibling perfumes

Siblings are the other perfumes in the same fixed bundle.

```text
The Don Juan Set For Him
  Pineapple Express <-> Halo
  Pineapple Express <-> Regent
  Halo <-> Regent
```

Stored as:

```text
niche:sibling:<sibling-product-handle>
```

and, in the structured data model:

```text
custom.sibling_handles = [sibling product handles]
```

Sibling links must be reciprocal:

```text
If A lists B as a sibling,
B must list A as a sibling.
```

Sibling links are created only from a verified fixed bundle member list. They should not be inferred from similar notes alone.

### 6.3 Perfume -> tester

A full-size perfume points to its 5 ml tester counterpart. A product can also inherit testers for its bundle co-members and scored recommendations.

```text
custom.tester_handles = [5ml product handles]
```

This relation supports a low-risk conversion path: sample before buying full size.

### 6.4 Perfume -> scored recommendation

A full-size perfume receives up to four candidates from the similarity engine:

```text
custom.recommendation_handles = [top four full-size handles]
```

The candidate’s own product and same-profile size variants are excluded.

### 6.5 Relation tags as fallback

Metafields are the primary structured data source. Tags remain useful for:

- Shopify Search & Discovery filters
- automated collections
- Liquid fallback logic
- audits and manual inspection
- systems that cannot read list metafields

---

## 7. Shopify Database Schema

### 7.1 Product tags

Tags are a denormalized index. They are easy to filter but not ideal for complex relationship traversal.

#### Taxonomy tags

```text
niche:taxonomy:v1
niche:audience:unisex
niche:note:bergamot
niche:note:woody-accord
niche:season:summer
niche:time:day-to-night
niche:occasion:everyday
```

#### Relationship tags

```text
niche:bundle:<bundle-handle>
niche:bundle-role:bundle
niche:bundle-role:member
niche:sibling:<product-handle>
```

Merchant-owned tags such as brand inspiration tags are preserved.

### 7.2 Product metafields

All definitions live in the `custom` namespace and are owned by `PRODUCT`.

| Namespace | Key | Type | Meaning |
|---|---|---|---|
| `custom` | `bundle_handles` | `list.single_line_text_field` | Parent bundles containing this product |
| `custom` | `bundle_member_handles` | `list.single_line_text_field` | Child perfumes in this bundle |
| `custom` | `sibling_handles` | `list.single_line_text_field` | Other perfumes in the same bundle |
| `custom` | `tester_handles` | `list.single_line_text_field` | Relevant 5 ml tester products |
| `custom` | `recommendation_handles` | `list.single_line_text_field` | Top four scored recommendations |
| `custom` | `recommendation_algorithm` | `single_line_text_field` | Algorithm version, currently `tag-similarity-v1` |

The values are JSON lists when written through the Admin API:

```json
["halo-by-niche-eau-de-parfum-inspired-by-rojas-elysium", "pineapple-express-by-niche-eau-de-parfum"]
```

In Liquid, Shopify exposes list metafields through `.value`:

```liquid
{% assign siblings = product.metafields.custom.sibling_handles.value %}
{% for handle in siblings %}
  {% assign sibling = all_products[handle] %}
{% endfor %}
```

### 7.3 Product identity and lookup

Use Shopify handles as foreign keys:

```text
product handle -> all_products[handle] -> product object
```

Do not store product titles as relationship keys. Titles change; handles are the stable catalog identifier.

---

## 8. Recommendation Algorithm

The current model is a weighted similarity score.

For target product $t$ and candidate product $c$:

$$
S(t,c) = 8A(t,c) + 2\min(N(t,c),8) + 3Y(t,c) + 2T(t,c) + O(t,c) + 7B(t,c)
$$

Where:

- $A(t,c)$ = 1 when audience matches, otherwise 0
- $N(t,c)$ = number of shared normalized notes/accords
- $Y(t,c)$ = number of shared seasons
- $T(t,c)$ = number of shared times of day
- $O(t,c)$ = number of shared occasions
- $B(t,c)$ = 1 when the products share at least one bundle, otherwise 0

### Component explanations

#### Audience match: 8 points

Audience is a strong merchandising signal. A male-targeted scent should generally recommend male or unisex candidates, while a female-targeted scent should generally recommend female or unisex candidates.

#### Shared notes: 2 points each, capped at 8 notes

Notes are the main olfactory similarity signal. The cap prevents products with very long descriptions from winning solely because they contain more note words.

Examples:

```text
Shared notes = 4
Note score = 4 * 2 = 8
```

```text
Shared notes = 10
Note score = min(10, 8) * 2 = 16
```

#### Shared seasons: 3 points each

Season overlap captures use-case compatibility. A summer fragrance and a winter fragrance may share notes but are less interchangeable than two summer/day fragrances.

#### Shared times: 2 points each

Time overlap distinguishes day, evening, night, and transitional scents.

#### Shared occasions: 1 point each

Occasion is a useful but softer signal. It should influence ranking without overpowering actual scent similarity.

#### Shared bundle: 7 points

A shared bundle is a strong merchandising signal because the merchant has already grouped the products together. It also supports cross-selling and discovery within the same curated story.

### Candidate restrictions

The engine compares full-size individual fragrances only.

Excluded candidates:

- the target product itself
- the target’s 5 ml counterpart
- products with the same profile identity, such as full-size vs travel size
- bundle products
- body care products
- products without a usable taxonomy profile

### Tie-breaking

Candidates are sorted by:

1. descending score
2. ascending handle for deterministic ordering

The first four candidates become `custom.recommendation_handles`.

Deterministic sorting matters because it prevents recommendation order from changing randomly between sync runs.

---

## 9. Bundle Detection and Member Matching

### 9.1 Bundle detection

A row is treated as a bundle when its title, handle, or merchant-owned tags contain signals such as:

```text
bundle
set
trio
layering
build your
maxbundle
```

Managed `niche:*` tags are excluded from the detection signal. This is important because a perfume can have a tag such as `niche:bundle:the-don-juan-set-for-him` without being a bundle itself.

### 9.2 Member matching

The system builds canonical names from individual fragrance titles, then searches bundle copy for those names.

The matching process:

1. Normalize HTML and Unicode.
2. Remove size suffixes such as `5ml travel size`.
3. Normalize punctuation and accents.
4. Sort names longest-first to reduce partial collisions.
5. Match with word boundaries.
6. Exclude 5 ml/travel handles from fixed bundle members.
7. Require at least two matched full-size members.

Example:

```text
Bundle copy contains:
  Pineapple Express, Halo, Regent

Generated member handles:
  pineapple-express-by-niche-eau-de-parfum
  halo-by-niche-eau-de-parfum-inspired-by-rojas-elysium
  regent-by-niche-eau-de-parfum-inspired-by-pdms-castley
```

### 9.3 Build Your Own exception

A dynamic bundle with customer-selected contents must not be assigned fixed children. Otherwise the database would claim a false relationship.

---

## 10. Synchronization Pipeline

### 10.1 Taxonomy pipeline

Script:

```text
scripts/shopify_fragrance_taxonomy_sync.py
```

Flow:

```text
Read CSV
  -> merge duplicate rows by Handle
  -> identify Eau de Parfum fragrances
  -> remove managed tags from classification input
  -> combine title, merchant tags, body, SEO description
  -> extract audience, notes, seasons, times, occasions
  -> write reports/fragrance-taxonomy-v1.csv
  -> optional --apply writes Shopify taxonomy tags
```

The script removes only managed taxonomy prefixes before applying regenerated tags:

```text
niche:taxonomy:
niche:audience:
niche:note:
niche:season:
niche:time:
niche:occasion:
```

### 10.2 Relationship pipeline

Script:

```text
scripts/shopify_recommendations_sync.py
```

Flow:

```text
Read merged catalog
  -> classify individual fragrances
  -> classify bundle products
  -> match bundle members
  -> create product_bundles index
  -> create reciprocal sibling graph
  -> load taxonomy profiles
  -> score full-size candidates
  -> find testers
  -> write reports/recommendation-relations-v1.json
  -> --apply ensures metafield definitions exist
  -> update relation tags
  -> update relation metafields
```

Live write targets:

- 75 individual fragrance products
- 58 fixed bundle relationships
- 133 relation-bearing products
- 6 typed product metafield definitions

### 10.3 CSV relation export

Use:

```bash
python3 scripts/shopify_recommendations_sync.py --export-csv
```

This writes relation tags to every matching duplicate CSV row while preserving merchant tags.

### 10.4 Audit mode vs apply mode

Audit mode:

```bash
python3 scripts/shopify_recommendations_sync.py
```

No Shopify mutation occurs. It rebuilds the JSON report and prints model counts.

Apply mode:

```bash
python3 scripts/shopify_recommendations_sync.py --apply
```

It provisions missing metafield definitions, updates product tags, and writes metafield values.

---

## 11. Storefront Rendering Model

The product page uses `sections/niche-product-relations.liquid`.

It reads:

```liquid
product.metafields.custom.bundle_handles.value
product.metafields.custom.bundle_member_handles.value
product.metafields.custom.sibling_handles.value
product.metafields.custom.tester_handles.value
product.metafields.custom.recommendation_handles.value
```

For each handle it resolves the real product:

```liquid
{% assign related_product = all_products[handle] %}
```

Then it renders the existing theme product card so the relationship section uses the same:

- product image behavior
- variant controls
- price output
- add-to-cart behavior
- product URL
- global design system styles

The section is installed in both product templates:

```text
templates/product.json
templates/product.layout-2.json
```

It groups products into:

1. Bundles containing this fragrance
2. More from this collection / sibling perfumes
3. Try it in discovery size
4. You may also like

Products are deduplicated during rendering so the same handle does not appear repeatedly across relation groups.

---

## 12. Database Integrity Rules

These rules should be tested after every regeneration.

### Product identity

- Every relationship handle must exist in Shopify.
- Every relationship handle must exist in the CSV or be intentionally excluded.
- Handles, not titles, are the only relationship keys.

### Taxonomy

- Exactly one audience tag per classified product.
- At least one note for a normal fragrance profile.
- One or two seasons.
- One or two times.
- One to four occasions.
- Exactly one taxonomy version tag.

### Bundle graph

- A fixed bundle must have at least two full-size members.
- A bundle child must list its parent bundle.
- A bundle parent must list its children.
- Sibling edges must be reciprocal.
- No 5 ml product should become a fixed bundle child.
- Build-your-own offers must not get fixed children.

### Recommendation graph

- Full-size product does not recommend itself.
- Full-size product does not recommend its own 5 ml counterpart as a full-size candidate.
- A recommendation candidate has a valid taxonomy profile.
- Maximum four scored recommendations per full-size product.
- Recommendation order is deterministic.

### Shopify data

- Metafield type must match the definition.
- List values must be valid JSON arrays.
- `recommendation_algorithm` must identify the generation version.
- Existing merchant tags must survive regeneration.

---

## 13. Example End-to-End Record

### Target

```text
Regent — Eau de Parfum
handle: regent-by-niche-eau-de-parfum-inspired-by-pdms-castley
```

### Taxonomy profile

```text
audience: unisex
notes: amber, citrus-accord, floral-accord, musk, spicy-accord, woody-accord
seasons: autumn, winter
times: evening, night
occasions: everyday, formal
```

### Bundle graph

```text
Parent bundle:
  The Don Juan Set For Him

Children:
  Pineapple Express
  Halo
  Regent

Sibling handles:
  pineapple-express-by-niche-eau-de-parfum
  halo-by-niche-eau-de-parfum-inspired-by-rojas-elysium
```

### Tester graph

```text
regent-5ml-travel-size-edp
halo-5ml-travel-size-eau-de-parfum
blacklist-5ml-travel-size-edp
epoch-5ml-travel-size-edp
```

### Recommendation graph

```text
Pineapple Express
Tonka Prive
Blacklist
Epoch
```

### Product-page result

The product page can show:

- the bundle containing Regent
- Halo and Pineapple Express as sibling perfumes
- Regent’s 5 ml tester
- scored recommendation cards
- normalized note pills

---

## 14. Why This Model Works

### Explainability

Every result can be explained through shared attributes or a known merchandising relationship.

### Maintainability

The classifier has controlled vocabularies and managed prefixes. Re-running the pipeline is safe and repeatable.

### Shopify compatibility

Tags work with native filters and collections. Metafields work with Liquid and structured theme sections.

### Commercial usefulness

The graph supports more than abstract similarity:

- sibling discovery increases basket breadth
- bundle parents expose curated sets
- testers reduce purchase risk
- recommendations support cross-sell
- shared bundle scoring rewards merchant curation

### Graceful degradation

If a metafield is missing, relation tags remain available for audits and future fallback logic. If a product has no relationships, its product page simply hides the empty relation groups.

---

## 15. Current Limitations

1. The current note extraction is copy-based. It does not yet use a dedicated perfumer-maintained note pyramid.
2. Broad accord tags such as `floral-accord` and `woody-accord` are useful but less precise than structured top/heart/base notes.
3. Bundle member matching depends on bundle copy containing recognizable product names.
4. The current model uses a fixed weighted score rather than learned customer behavior.
5. It does not yet include conversion rate, click-through rate, add-to-cart rate, inventory, margin, or purchase history.
6. Products with incomplete descriptions may receive conservative defaults such as `unisex`, `all-season`, or `day-to-night`.
7. The theme renders a bounded number of relation cards to protect page performance.

These are intentional v1 tradeoffs. The current system is a deterministic catalog intelligence layer, not a machine-learning personalization system.

---

## 16. Recommended Future Versions

### v1.1: Better note structure

Add separate list metafields:

```text
custom.top_notes
custom.heart_notes
custom.base_notes
custom.fragrance_families
```

Keep normalized tags for filters, but use structured note positions for better similarity.

### v1.2: Relationship confidence

Add:

```text
custom.relation_confidence
custom.bundle_match_source
```

Example values:

```text
bundle_match_source = description_exact_name
relation_confidence = 0.95
```

### v1.3: Behavioral ranking

Blend catalog similarity with observed customer behavior:

```text
final_score = catalog_score * 0.70
             + click_affinity * 0.10
             + add_to_cart_affinity * 0.10
             + purchase_affinity * 0.10
```

Behavioral signals should be anonymized and aggregated.

### v2: Graph-based recommendations

Represent the catalog as a graph:

- product nodes
- bundle nodes
- tester nodes
- note nodes
- audience/season/occasion nodes
- sibling edges
- contains edges
- similar-to edges
- tester-of edges

Then use graph traversal to explain recommendations:

```text
Regent
  -> member of Don Juan Set
  -> sibling of Halo
  -> shares woody accord with Pineapple Express
  -> tester available
```

### v3: Hybrid personalization

Use the deterministic catalog graph as the safe fallback and layer customer preferences on top:

- preferred audience
- favorite notes
- disliked notes
- preferred intensity
- season preference
- occasion preference
- price range
- purchase history

The system should never recommend an item solely because of a weak behavioral correlation if its fragrance profile is incompatible.

---

## 17. Operational Commands

Generate taxonomy report only:

```bash
python3 scripts/shopify_fragrance_taxonomy_sync.py
```

Apply taxonomy tags to Shopify:

```bash
python3 scripts/shopify_fragrance_taxonomy_sync.py --apply
```

Generate recommendation and bundle report only:

```bash
python3 scripts/shopify_recommendations_sync.py
```

Apply bundle, sibling, tester, recommendation tags and metafields:

```bash
python3 scripts/shopify_recommendations_sync.py --apply
```

Export relation tags into the CSV:

```bash
python3 scripts/shopify_recommendations_sync.py --export-csv
```

The apply command is schema-aware and creates missing product metafield definitions before writing values.

---

## 18. Final Architecture Summary

```text
Shopify CSV
  |
  |  title, body, type, merchant tags
  v
Taxonomy classifier
  |
  |  audience, notes, seasons, times, occasions
  v
fragrance-taxonomy-v1.csv
  |
  v
Bundle matcher
  |
  |  parent -> children
  |  child -> parent
  |  sibling <-> sibling
  |  product -> tester
  v
recommendation-relations-v1.json
  |
  v
Weighted similarity engine
  |
  |  top four full-size recommendations
  v
Shopify Admin API
  |
  |  product tags
  |  typed product metafields
  v
Shopify Liquid product templates
  |
  |  bundles
  |  siblings
  |  testers
  |  recommendations
  |  note pills
  v
Customer discovery experience
```

The important design decision is to keep **classification**, **relationship generation**, **storage**, and **rendering** as separate stages. That separation makes the system auditable, rerunnable, and safe to improve without rewriting the storefront.
