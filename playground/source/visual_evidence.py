"""Focus-gated PDF visual metadata. No pixel-based numerical interpretation."""

from dataclasses import replace

from playground.source.document import SourceElementType
from playground.source.structure import CAPTION, reference_keys


def relevant_caption(text: str, focus: str, section_text: str = "") -> bool:
    caption = CAPTION.match(text)
    if not caption:
        return False
    kind = "table" if caption.group(1).lower() == "table" else "figure"
    key = (kind, caption.group(2).lower())
    import re
    terms = set(re.findall(r"[\w]+", focus.lower())) - {"the", "in", "of", "a", "shown", "figure", "table"}
    lexical = bool(terms & set(re.findall(r"[\w]+", text.lower())))
    section_match = bool(terms & set(re.findall(r"[\w]+", section_text.lower())))
    return key in reference_keys(focus) or lexical or (section_match and key in reference_keys(section_text))


def enrich_figure(element, page, settings):
    """Retain nearby extracted labels and drawing bounds; never load linked resources."""
    import pymupdf
    rect = pymupdf.Rect(element.bbox)
    # Region above a caption, restricted to its column.
    region = pymupdf.Rect(rect.x0, max(0, rect.y0 - page.rect.height * .35), rect.x1, rect.y0)
    words = page.get_text("words", clip=region)[:settings.max_visual_items]
    labels = [{"text": w[4], "bbox": list(w[:4])} for w in words]
    drawings = []
    for drawing in page.get_drawings():
        if drawing["rect"].intersects(region):
            drawings.append({"bbox": list(drawing["rect"]), "item_types": [item[0] for item in drawing["items"]][:16]})
            if len(drawings) >= settings.max_visual_items:
                break
    images = [list(info["bbox"]) for info in page.get_image_info() if pymupdf.Rect(info["bbox"]).intersects(region)]
    return replace(element, metadata={**element.metadata, "visual_region": list(region),
        "region_precision": "heuristic_caption_neighborhood", "labels": labels,
        "vector_shapes": drawings, "image_bounds": images[:settings.max_visual_items],
        "richly_processed": True, "numeric_values_from_pixels": False})
