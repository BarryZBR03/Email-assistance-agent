def sanitize_filename_part(value: str, default: str) -> str:
    parts = []
    last_was_separator = False
    for char in value.strip().lower():
        if char.isalnum():
            parts.append(char)
            last_was_separator = False
        elif not last_was_separator:
            parts.append("_")
            last_was_separator = True

    normalized = "".join(parts).strip("_")
    return normalized or default
