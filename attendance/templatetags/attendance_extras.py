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
@register.filter
def abs_val(value):
    """Return the absolute value of a number."""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value

@register.filter
def percentage(value, arg):
    """Calculate percentage: (value / arg) * 100."""
    try:
        return min(float(value) / float(arg) * 100, 100)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0
