from django.urls import include, path

urlpatterns = [
    path("replication/", include("django_replication.api.urls")),
]
