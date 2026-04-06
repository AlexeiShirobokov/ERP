from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),

    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("maintenance/", include("maintenance.urls")),
    path("", include("main.urls")),
    path("", include("main.debitor_urls")),
    path("taskmanager/", include("taskmanager.urls")),
    #path("logistics/", include("logistics.urls")),

]