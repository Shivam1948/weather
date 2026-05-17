from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("today/", views.today, name="today"),
    path("10-day/", views.ten_day, name="ten_day"),
    path("radar/", views.radar, name="radar"),
    path("air-quality/", views.air_quality, name="air_quality"),
    path("health/", views.health, name="health"),
]
