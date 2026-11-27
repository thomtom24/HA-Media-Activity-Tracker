"""Application option normalisation; accept existing comma-separated settings."""


def app_list(value):
    if isinstance(value, str):
        value = value.split(",")
    return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))


def alias_rows(value):
    if isinstance(value, str):
        value = [{"key": key.strip(), "label": label.strip()}
                 for item in value.split(",") for key, sep, label in [item.partition("=")]
                 if sep and key.strip() and label.strip()]
    return value


def aliases(value):
    return {row["key"].strip().casefold(): row["label"].strip()
            for row in alias_rows(value) if row.get("key") and row.get("label")}


def valid_application_settings(data):
    for field, maximum in (("excluded", 100), ("app_sensors", 40)):
        rows = app_list(data.get(field, []))
        if len(rows) > maximum or any(len(item) > 255 for item in rows):
            return False
    rows = alias_rows(data.get("aliases", []))
    if len(rows) > 100:
        return False
    keys = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        key, label = row.get("key"), row.get("label")
        if not all(isinstance(item, str) and 0 < len(item.strip()) <= 255 for item in (key, label)):
            return False
        if key.strip().casefold() in keys:
            return False
        keys.add(key.strip().casefold())
    return True
