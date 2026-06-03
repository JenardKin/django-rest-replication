from django.apps import AppConfig


class DjangoRESTReplicationConfig(AppConfig):
    name = "django_rest_replication"
    verbose_name = "Django Replication"
    default_auto_field = "django.db.models.UUIDField"

    def ready(self) -> None:
        # Signals are registered here — never at module level — to avoid
        # AppRegistryNotReady errors and to respect Django's app loading order.
        from django_rest_replication.capture.signals import connect_signals

        connect_signals()
