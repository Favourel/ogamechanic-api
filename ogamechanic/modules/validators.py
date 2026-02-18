from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .email_validation import DisposableEmailValidator


class CustomEmailValidator(EmailValidator):
    """
    Custom email validator that includes disposable email detection.
    """
    def __init__(self, allow_disposable: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.allow_disposable = allow_disposable
        self.disposable_validator = DisposableEmailValidator()

    def __call__(self, value):
        super().__call__(value)

        if not self.allow_disposable:
            if not self.disposable_validator.validate_email(value):
                raise ValidationError(
                    _('Disposable email addresses are not allowed.'),
                    code='disposable_email'
                )
