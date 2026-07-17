import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ComplexPasswordValidator:
    """Require at least one uppercase, one lowercase, and one special character."""

    SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")

    def validate(self, password, user=None):
        errors = []
        if not any(c.isupper() for c in password):
            errors.append(_("Password must contain at least one uppercase letter."))
        if not any(c.islower() for c in password):
            errors.append(_("Password must contain at least one lowercase letter."))
        if not self.SPECIAL_RE.search(password):
            errors.append(_("Password must contain at least one special character."))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, "
            "one lowercase letter, and one special character."
        )
  