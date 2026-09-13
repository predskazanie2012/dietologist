import re


def fix_text(value: str) -> str:
    """Repair Russian text accidentally stored as UTF-8 decoded through cp1251."""
    if not isinstance(value, str):
        return value
    try:
        data = bytearray()
        for char in value:
            try:
                data.extend(char.encode("cp1251"))
            except UnicodeEncodeError:
                if ord(char) < 256:
                    data.append(ord(char))
                else:
                    return value
        fixed = bytes(data).decode("utf-8")
    except (UnicodeError, ValueError):
        return value
    return fixed if _looks_better(fixed, value) else value


def _looks_better(fixed: str, original: str) -> bool:
    bad_markers = ("Р", "С", "Ð", "Ñ", "\ufffd", "\x98")
    original_bad = sum(original.count(marker) for marker in bad_markers)
    fixed_bad = sum(fixed.count(marker) for marker in bad_markers)
    return fixed_bad < original_bad


def normalize_public_nutrition_terms(value: str) -> str:
    """Make AI nutrition wording clearer for non-medical user-facing text."""
    if not isinstance(value, str):
        return value
    text = fix_text(value)
    replacements = (
        (r"\bгликемия\s+высокая\b", "высокий уровень сахара"),
        (r"\bгликемия\s+низкая\b", "низкий уровень сахара"),
        (r"\bгликемия\s+стабильная\b", "стабильный уровень сахара"),
        (r"\bгликемия\s+нестабильная\b", "нестабильный уровень сахара"),
        (r"\bгликемия\s+ровная\b", "ровный уровень сахара"),
        (r"\bстабильнее\s+гликеми[яиюеей]\b", "более стабильный уровень сахара"),
        (r"\bстабилизировать\s+гликеми[яиюеей]\b", "стабилизировать уровень сахара"),
        (r"\bснизить\s+гликеми[яиюеей]\b", "уменьшить скачки сахара"),
        (r"\bулучшить\s+гликеми[яиюеей]\b", "улучшить стабильность сахара"),
        (r"\bгликемия\b", "уровень сахара"),
        (r"\bгликемию\b", "уровень сахара"),
        (r"\bгликемии\b", "уровня сахара"),
        (r"\bгликемией\b", "уровнем сахара"),
        (r"\bгликемие\b", "уровне сахара"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
