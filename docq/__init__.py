"""doc-query (docq): local, index-and-search retrieval over office documents.

Currently supports PDF only (see `docq.extractor_pdf`); the generic core
(store/search/tokenize/tokens) is format-agnostic so pptx/xlsx support can
be added as sibling extractor modules without duplicating it.
"""
