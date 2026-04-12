from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get dict item by key (supports int/str keys)."""
    if isinstance(dictionary, dict):
        # try int key first, then str key
        if key in dictionary:
            return dictionary.get(key)
        try:
            return dictionary.get(int(key))
        except (ValueError, TypeError):
            return dictionary.get(str(key))
    return None


@register.filter(name='list')
def to_list(value):
    """Convert a set/queryset to a list for JSON serialization in templates."""
    try:
        return sorted(list(value))
    except Exception:
        return list(value)
