"""Dataset ingestion and baseline training pipelines."""

from .ingest import (
    PairExample,
    build_catalog_from_clusters,
    load_canonical_products,
    load_product_listings,
    load_wdc_pairs,
    sha256_file,
)

__all__ = [
    "PairExample",
    "build_catalog_from_clusters",
    "load_canonical_products",
    "load_product_listings",
    "load_wdc_pairs",
    "sha256_file",
]
