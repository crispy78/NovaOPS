from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return ''
    if key in mapping:
        return mapping[key]
    return mapping.get(str(key), '')
