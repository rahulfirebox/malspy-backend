from django.core.cache import cache
from django.db.models.signals import post_delete, post_save

_SIGNATURES_CACHE_KEY = "static_signatures_compiled"


def _invalidate_signature_cache(**kwargs):
    cache.delete(_SIGNATURES_CACHE_KEY)


def connect_signature_signals():
    from .models import MalwareSignature

    post_save.connect(
        _invalidate_signature_cache,
        sender=MalwareSignature,
        dispatch_uid="scans.malware_signature.post_save",
    )
    post_delete.connect(
        _invalidate_signature_cache,
        sender=MalwareSignature,
        dispatch_uid="scans.malware_signature.post_delete",
    )
