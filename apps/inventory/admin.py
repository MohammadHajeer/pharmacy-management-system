from django.contrib import admin

from .models import MedicineBatch, StockMovement


admin.site.register([MedicineBatch, StockMovement])
