"""Read-only runtime secret boundary. Provisioning and rotation belong to Kernel/Volt."""
import re

from .errors import DomainError
from .fs import open_under


def read_credential_file(path):
    try:
        with open_under(path.parent, path.name) as stream:
            value = stream.read(128 * 1024 + 1)
        if len(value) > 128 * 1024:
            raise ValueError
        return value.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        raise DomainError("SECRET_UNAVAILABLE", "The required shell secret is unavailable.", 503) from None


class SecretStore:
    def __init__(self, directory):
        self.directory = directory

    def read(self, name):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or self.directory is None:
            raise DomainError("SECRET_UNAVAILABLE", "The required shell secret is unavailable.", 503)
        # Files contain exact values. No trimming of Access Keys or other opaque credentials.
        return read_credential_file(self.directory / name)

    def available(self, name):
        try:
            self.read(name)
            return True
        except (DomainError, OSError, UnicodeError):
            return False


# Versioned bindings are a Mastermind extension to the deployment Register profile.
# Provision them through Volt/Kernel; never infer an unrelated existing record.
SHELL_BINDINGS = {
    "ai_provider_key": "services.mastermind.secrets.ai_provider_key",
    "chronos_service_token": "services.mastermind.secrets.chronos_service_token",
    "share_pepper_v1": "services.mastermind.secrets.share_pepper_v1",
    "recovery_identity": "services.mastermind.secrets.recovery_identity_v1",
    "recovery_recipient": "services.mastermind.secrets.recovery_recipient_v1",
    "backup_signing_private": "services.mastermind.secrets.backup_signing_private_v1",
    "backup_signing_public": "services.mastermind.secrets.backup_signing_public_v1",
}


class ShellSecrets(SecretStore):
    def __init__(self, directory, kernel, *, development=False):
        super().__init__(directory)
        self.kernel, self.development = kernel, development

    def read(self, name):
        if name in SHELL_BINDINGS and not self.development:
            key = SHELL_BINDINGS[name]
            return self.kernel.resolve([key])[key]
        return super().read(name)
