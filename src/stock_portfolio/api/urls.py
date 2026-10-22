from django.urls import path

from stock_portfolio.api.views import api

urlpatterns = [path("api/", api.urls)]
