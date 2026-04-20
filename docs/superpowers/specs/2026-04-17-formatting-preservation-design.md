# Formatting Preservation Design

## Goal

Preserve the paragraph structure already present on source novel pages so exported `EPUB`, `HTML`, `MD`, and `TXT` files remain visually close to the web reading experience instead of collapsing into dense text blocks.

## Problem

The current exporters already render one text `ContentItem` as one paragraph/block in each output format. The denser-than-web reading experience is therefore caused earlier in the pipeline, during source extraction, where source adapters normalize text aggressively with calls like `get_text(strip=True)` and `p.strip()`.

That behavior can remove meaningful spacing and flatten paragraph presentation before export even begins. Once the source text has already been flattened, the exporters cannot reconstruct the original pacing reliably.

## Scope

This change applies to the source extraction layer for currently supported custom sources that feed text exports:

- `vvr_scraper/sources/truyenfull.py`
- `vvr_scraper/sources/lnhako.py`

The change should improve all downstream text-based exports that consume `ContentItem(type="text")` without adding export-specific formatting heuristics.

## Non-Goals

- Do not invent new paragraph breaks heuristically based on punctuation, quotes, or sentence length.
- Do not add exporter-only logic that tries to guess dialogue boundaries.
- Do not redesign EPUB/CSS styling as the primary fix.
- Do not change image handling.

## Design

### 1. Preserve source paragraph boundaries

Each HTML paragraph from the source page should continue to map to exactly one text `ContentItem` whenever possible.

### 2. Reduce destructive trimming

Source adapters should stop using the most aggressive text normalization patterns when reading chapter paragraphs.

Expected behavior:

- keep the existing paragraph list structure
- normalize obvious surrounding whitespace only
- avoid collapsing intentional internal line rhythm inside a paragraph more than necessary

### 3. Keep exporters simple

No structural change is needed in the exporters if source adapters continue returning one `ContentItem(type="text")` per intended paragraph. Existing output code can continue mapping each text item to one block:

- EPUB: one `<p>` per text item
- HTML: one `<p>` per text item
- Markdown/TXT: one paragraph block separated by blank lines per text item

## Implementation Notes

### TruyenFull

Replace paragraph extraction that uses `element.get_text(strip=True)` with a less destructive text read that preserves paragraph content more faithfully while still ignoring empty paragraphs.

### LnHako

Keep one extracted browser paragraph per text item, but avoid trimming in a way that unnecessarily destroys source spacing.

## Testing Strategy

Add regression tests that prove:

1. Source extraction preserves paragraph separation for representative chapter markup.
2. Exporters continue producing multiple paragraph blocks when given multiple text items.
3. No heuristic dialogue splitting is introduced.

## Success Criteria

- Exported chapters retain paragraph separation closer to the website view.
- Dialogue that is already separated on the source page remains separated in EPUB/HTML/MD/TXT.
- Existing tests continue to pass, with new regression coverage for paragraph preservation.
