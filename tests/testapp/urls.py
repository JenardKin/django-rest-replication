from django.urls import include, path

urlpatterns = [
    path("replication/", include("django_rest_replication.api.urls")),
]
