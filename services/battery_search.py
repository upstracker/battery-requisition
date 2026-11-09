import re


def parse_battery_quick_entry(text):
    """Split a quick entry such as ``Q100*2``, ``FB N100 4``, or ``46b24*2*เทิร์นเก่า``."""
    text = text.strip()
    if not text:
        return "", None, ""

    # 1. Separator (*, ×, or spaced x/X) with quantity and optional remark
    # e.g. "46b24*2*เทิร์นเก่า", "46b24*2 เทิร์นเก่า", "q100*2", "q100 x 4"
    sep_match = re.search(r"(?:\s*[*×]\s*|\s+[xX]\s*)(\d+)(?:(?:\s*[*×]\s*|\s+)(.*))?$", text)
    if sep_match:
        keyword = text[:sep_match.start()].strip()
        qty = int(sep_match.group(1))
        remark = (sep_match.group(2) or "").strip()
        if keyword:
            return keyword, qty, remark

    # 2. Spaced quantity with optional remark
    # e.g. "FB N100 3 แบตใหม่", "FB N100 3"
    spaced_match = re.search(r"\s+(\d+)(?:\s+(.*))?$", text)
    if spaced_match:
        keyword = text[:spaced_match.start()].strip()
        qty = int(spaced_match.group(1))
        remark = (spaced_match.group(2) or "").strip()
        if keyword:
            return keyword, qty, remark

    return text, None, ""


def _compact_search_text(value):
    """Normalize punctuation/spacing so 55D-23 also finds 55D23."""
    return re.sub(r"[^0-9A-Z\u0E00-\u0E7F]+", "", str(value or "").upper())


def prepare_inventory_item(item):
    """Pre-compute normalized compact search fields to avoid repeated regex substitutions."""
    if "_compact_fields" not in item:
        code = _compact_search_text(item.get("item_code"))
        brand = _compact_search_text(item.get("brand"))
        name = _compact_search_text(item.get("item_name"))
        capacity = _compact_search_text(item.get("capacity"))
        item["_compact_fields"] = (code, brand, name, capacity)
    return item


def prepare_inventory_items_for_search(items):
    """Pre-compute search fields for a list of items for instant live search."""
    for item in items:
        prepare_inventory_item(item)
    return items


def inventory_match_score(item, query):
    """Return a lower-is-better match score, or None when not matched."""
    query = query.strip()
    compact_query = _compact_search_text(query)
    if not compact_query:
        return None

    fields = item.get("_compact_fields")
    if fields is None:
        fields = prepare_inventory_item(item)["_compact_fields"]
    code = fields[0]

    if code == compact_query:
        return 0
    if code.startswith(compact_query):
        return 1
    if compact_query in code:
        return 2
    if any(field == compact_query for field in fields[1:]):
        return 3
    if any(field.startswith(compact_query) for field in fields[1:]):
        return 4
    if any(compact_query in field for field in fields[1:]):
        return 5

    # Multiple words may live in different columns, e.g. "FB Q100".
    tokens = [
        _compact_search_text(token)
        for token in re.split(r"\s+", query)
        if _compact_search_text(token)
    ]
    if len(tokens) > 1 and all(any(token in field for field in fields) for token in tokens):
        return 6
    return None


def find_inventory_matches(items, query):
    scored = []
    for item in items:
        score = inventory_match_score(item, query)
        if score is not None:
            scored.append((score, item))
    scored.sort(key=lambda pair: (
        pair[0],
        len(str(pair[1].get("item_code", ""))),
        str(pair[1].get("brand", "")).upper(),
        str(pair[1].get("item_code", "")).upper(),
    ))
    return scored
