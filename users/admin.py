from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from . import models
from django.contrib.auth.models import Group


@admin.register(models.UserEmailVerification)
class UserEmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    list_filter = ("expires_at", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_at", "updated_at")
    search_fields = ("name", "description")
    list_filter = ("created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(models.User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "active_role",
        "is_active",
    )  # noqa
    list_filter = ("is_active", "active_role", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200

    # Specify that email is the username field
    username_field = "email"

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {
         "fields": ("first_name", "last_name", "phone_number")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "roles",
                    "active_role",
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",  # noqa
                    "user_permissions",
                ),
            },
        ),
        (
            _("Important dates"),
            {"fields": ("last_login", "date_joined",
                        "created_at", "updated_at")},
        ),
        (
            _("Track Login"),
            {"fields": ("failed_login_attempts",
                        "locked_until", "last_failed_login")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "roles",
                    "active_role",
                ),  # noqa
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    actions = ["unlock_accounts"]

    def unlock_accounts(self, request, queryset):
        updated = queryset.update(locked_until=None, failed_login_attempts=0)
        self.message_user(
            request, f"{updated} accounts unlocked" " successfully.")

    unlock_accounts.short_description = "Unlock selected accounts"


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("user__email", "message")
    autocomplete_fields = ("user",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.MerchantProfile)
class MerchantProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cac_number",
        "business_address",
        "location",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__email", "cac_number", "business_address")
    list_filter = ("created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.MechanicProfile)
class MechanicProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_approved", "created_at", "updated_at")
    search_fields = ("user__email",)
    list_filter = ("is_approved", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "phone_number",
        "vehicle_type",
        "is_approved",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__email", "phone_number",
                     "vehicle_registration_number")
    list_filter = ("vehicle_type", "is_approved", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user",)
    list_per_page = 25  # Enable pagination, 25 per page by default
    list_max_show_all = 200  # Optional: limit max "Show all" to 200


@admin.register(models.BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "account_name",
        "bank_name",
        "account_number",
        "is_verified",
        "is_active",
        "created_at",
    )
    list_filter = ("is_verified", "is_active", "bank_name", "created_at")
    search_fields = ("user__email", "account_name",
                     "account_number", "bank_name")
    readonly_fields = ("created_at", "updated_at", "paystack_recipient_code")
    ordering = ("-created_at",)

    fieldsets = (
        ("User Information", {"fields": ("user",)}),
        (
            "Bank Account Details",
            {"fields": ("account_number", "account_name",
                        "bank_code", "bank_name")},
        ),
        (
            "Verification Status",
            {"fields": ("is_verified", "is_active",
                        "paystack_recipient_code")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(models.Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "balance",
        "currency",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "currency", "created_at")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("User Information", {"fields": ("user",)}),
        ("Wallet Details", {"fields": ("balance", "currency", "is_active")}),
        ("Transaction Limits", {"fields": ("daily_limit", "monthly_limit")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(models.Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "amount",
        "transaction_type",
        "status",
        "reference",
        "created_at",
    )
    list_filter = ("transaction_type", "status", "created_at")
    search_fields = ("wallet__user__email", "reference", "description")
    readonly_fields = ("created_at", "updated_at", "fee", "metadata")
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Transaction Details",
            {"fields": ("wallet", "amount", "transaction_type", "status")},
        ),
        ("Reference Information", {"fields": ("reference", "description")}),
        ("Financial Details", {"fields": ("fee", "metadata")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("wallet__user")


@admin.register(models.SecureDocument)
class SecureDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "document_type",
        "verification_status",
        "file_size",
        "uploaded_at",
        "is_encrypted",
    )
    list_filter = (
        "document_type",
        "verification_status",
        "is_encrypted",
        "uploaded_at",
    )
    search_fields = ("user__email", "original_filename", "secure_filename")
    readonly_fields = (
        "file_hash",
        "access_count",
        "last_accessed",
        "uploaded_at",
        "updated_at",
    )
    ordering = ("-uploaded_at",)

    fieldsets = (
        (
            "Document Information",
            {
                "fields": (
                    "user",
                    "document_type",
                    "original_filename",
                    "secure_filename",
                    "file_path",
                )
            },
        ),
        (
            "File Details",
            {"fields": ("file_size", "file_hash",
                        "mime_type", "is_encrypted")},
        ),
        (
            "Verification Status",
            {
                "fields": (
                    "verification_status",
                    "verified_by",
                    "verified_at",
                    "verification_notes",
                )
            },
        ),
        (
            "Access Tracking",
            {"fields": ("access_count", "last_accessed", "extracted_info")},
        ),
        (
            "Timestamps",
            {
                "fields": ("uploaded_at", "updated_at", "expires_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "verified_by") # noqa


@admin.register(models.DocumentVerificationLog)
class DocumentVerificationLogAdmin(admin.ModelAdmin):
    list_display = ("document", "action", "performed_by",
                    "timestamp", "ip_address")
    list_filter = ("action", "timestamp")
    search_fields = ("document__user__email", "performed_by__email", "notes")
    readonly_fields = ("timestamp",)
    ordering = ("-timestamp",)

    fieldsets = (
        (
            "Log Information",
            {"fields": ("document", "action", "performed_by", "notes")},
        ),
        ("Request Details", {
         "fields": ("ip_address", "user_agent", "timestamp")}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("document__user", "performed_by")
        )


@admin.register(models.FileSecurityAudit)
class FileSecurityAuditAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "audit_type",
        "file_path",
        "success",
        "timestamp",
        "ip_address",
    )
    list_filter = ("audit_type", "success", "timestamp")
    search_fields = ("user__email", "file_path", "file_hash")
    readonly_fields = ("timestamp",)
    ordering = ("-timestamp",)

    fieldsets = (
        (
            "Audit Information",
            {"fields": ("user", "audit_type", "file_path",
                        "file_hash", "success")},
        ),
        (
            "Request Details",
            {"fields": ("ip_address", "user_agent",
                        "session_id", "error_message")},
        ),
        ("Metadata", {"fields": ("metadata", "timestamp"),
         "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


admin.site.unregister(Group)
admin.site.site_header = "OGAMECHANIC Administration"
admin.site.site_title = "OGAMECHANIC Admin Portal"
admin.site.index_title = "Welcome to Your OGAMECHANIC Admin"


# Register all other models from mechanics app that are not already registered above  # noqa
already_registered = {
    models.UserEmailVerification,
    models.Role,
    models.User,
    models.Notification,
    models.MerchantProfile,
    models.MechanicProfile,
    models.DriverProfile,
    models.BankAccount,
    models.Wallet,
    models.Transaction,
    models.SecureDocument,
    models.DocumentVerificationLog,
    models.FileSecurityAudit,
}

for model in vars(models).values():
    try:
        if (
            isinstance(model, type)
            and issubclass(model, models.models.Model)
            and model not in already_registered
        ):
            admin.site.register(model)
    except Exception:
        continue
