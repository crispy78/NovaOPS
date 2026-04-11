import uuid

from django.db import models, transaction

# Common ISO 4217 currency choices shown in the site-settings picker
CURRENCY_CHOICES = [
    ('GBP', 'GBP — British Pound'),
    ('EUR', 'EUR — Euro'),
    ('USD', 'USD — US Dollar'),
    ('CHF', 'CHF — Swiss Franc'),
    ('SEK', 'SEK — Swedish Krona'),
    ('NOK', 'NOK — Norwegian Krone'),
    ('DKK', 'DKK — Danish Krone'),
    ('PLN', 'PLN — Polish Zloty'),
    ('AUD', 'AUD — Australian Dollar'),
    ('CAD', 'CAD — Canadian Dollar'),
]


class UUIDPrimaryKeyModel(models.Model):
    """Base for domain models: primary key is a non-editable UUID v4."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class ReferenceSequence(models.Model):
    """Serialised per-prefix-per-year counter for human-readable reference numbers.

    A single row per (prefix, year) key is locked with SELECT FOR UPDATE before
    incrementing, which prevents duplicate reference numbers under concurrent requests.
    """

    key = models.CharField(max_length=32, unique=True)
    last_n = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'reference sequence'
        verbose_name_plural = 'reference sequences'

    def __str__(self) -> str:
        return f'{self.key} (last={self.last_n})'


class SiteSettings(models.Model):
    """Singleton table that stores site-wide configuration (always pk=1)."""

    currency = models.CharField(
        max_length=3,
        default='GBP',
        choices=CURRENCY_CHOICES,
        verbose_name='default currency',
        help_text='ISO 4217 code used across all products and documents.',
    )

    class Meta:
        verbose_name = 'site settings'

    def __str__(self) -> str:
        return f'Site settings (currency={self.currency})'

    @classmethod
    def get(cls) -> 'SiteSettings':
        """Return the single settings row, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def next_reference(prefix: str, year: int, pad: int = 5) -> str:
    """Return the next sequential reference string, e.g. 'Q-2026-00001'.

    Atomically increments a counter row using SELECT FOR UPDATE so that two
    concurrent requests can never receive the same number.
    """
    key = f'{prefix}-{year}'
    with transaction.atomic():
        seq, _ = ReferenceSequence.objects.select_for_update().get_or_create(
            key=key, defaults={'last_n': 0}
        )
        seq.last_n += 1
        seq.save(update_fields=['last_n'])
    return f'{prefix}-{year}-{seq.last_n:0{pad}d}'
