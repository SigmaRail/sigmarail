from django.contrib import admin

from .models import MCPUserIdentity


@admin.register(MCPUserIdentity)
class MCPUserIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "issuer", "subject", "email", "last_seen_at")
    search_fields = ("user__email", "issuer", "subject", "email")
    readonly_fields = ("linked_at", "last_seen_at")
