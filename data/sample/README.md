# CatalogOps deterministic sample

This hand-authored, public-safe fixture contains 12 canonical consumer products
and 41 differently formatted seller offers: 22 training rows and 19 held-out
test rows. Six test offers are deliberate no-match products. One deliberately
underspecified known offer should route to review. Three canonical
test products are marked `unseen=true` because their entities have no positive
offer in the classifier's training split; their trusted catalog records remain
available to retrieval.

`offers.jsonl` mirrors WDC multi-class field names (`id`, `brand`, `title`,
`description`, `price`, `priceCurrency`, `cluster_id`, `label`, `unseen`) and
adds `split`, `source`, and structured identifiers for local experimentation.

The fixture is original demo data, not a subset of WDC and not evidence of real
marketplace performance. Use the official benchmark downloader and preserve its
published split protocol before making external benchmark claims.
