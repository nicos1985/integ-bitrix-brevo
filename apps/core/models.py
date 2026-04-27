from django.db import models


class CoreModel(models.Model):
    """Abstract base model with timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
