import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path
    public_url: str = "http://127.0.0.1:18390"
    runtime_url: str | None = None
    worker_url: str | None = None
    runtime_mode: str = "supervised"
    kernel_url: str | None = None
    kernel_token_file: Path | None = None
    trust_ca_file: Path | None = None
    secret_backend: str = "kernel"
    neptune_socket: str | None = None
    neptune_token_file: Path | None = None
    neptune_export_token_file: Path | None = None
    neptune_export_url: str = "http://127.0.0.1:18390/api/internal/neptune/backup"
    updater_socket: str | None = None
    updater_token_file: Path | None = None
    updater_head_id: str = "mastermind"
    secret_directory: Path | None = None
    bridge_artifacts: Path | None = None
    max_note_bytes: int = 8 * 1024**2
    max_share_bytes: int = 1024**2
    max_upload_bytes: int = 2 * 1024**3
    max_backup_bytes: int = 8 * 1024**3
    max_expanded_bytes: int = 32 * 1024**3
    max_archive_entries: int = 100_000
    spool_quota: int = 96 * 1024**3
    incoming_quota: int = 16 * 1024**3
    test_mode: bool = False
    timezone: str = "UTC"
    credential_directory: Path | None = None

    def __post_init__(self):
        if self.runtime_mode not in ("supervised", "offline"):
            raise ValueError("Unsupported Runtime coordination mode")
        if self.runtime_mode == "offline" and not self.test_mode:
            raise ValueError("Offline coordination is available only to isolated test fixtures")
        if self.secret_backend not in ("kernel", "development-files"):
            raise ValueError("Unsupported shell secret backend")

    @property
    def vault(self) -> Path:
        # Both containers mount the vault parent, so a generation switch is visible
        # when the stopped Runtime reopens current. Runtime never mounts Core state.
        return self.home / "vault" / "current"

    @property
    def state(self) -> Path:
        return self.home / "state"

    @classmethod
    def environment(cls):
        def path(name):
            value = os.environ.get(name)
            return Path(value) if value else None
        return cls(
            home=Path(os.environ.get("MASTERMIND_HOME", "/var/lib/mastermind")),
            public_url=os.environ.get("MASTERMIND_PUBLIC_URL", "http://127.0.0.1:18390"),
            runtime_url=os.environ.get("MASTERMIND_RUNTIME_URL"),
            worker_url=os.environ.get("MASTERMIND_WORKER_URL"),
            runtime_mode=os.environ.get("MASTERMIND_RUNTIME_MODE", "supervised"),
            kernel_url=os.environ.get("MASTERMIND_KERNEL_URL"),
            kernel_token_file=path("MASTERMIND_KERNEL_TOKEN_FILE"),
            trust_ca_file=path("MASTERMIND_TRUST_CA_FILE"),
            secret_backend=os.environ.get("MASTERMIND_SECRET_BACKEND", "kernel"),
            neptune_socket=os.environ.get("MASTERMIND_NEPTUNE_SOCKET"),
            neptune_token_file=path("MASTERMIND_NEPTUNE_TOKEN_FILE"),
            neptune_export_token_file=path("MASTERMIND_NEPTUNE_EXPORT_TOKEN_FILE"),
            neptune_export_url=os.environ.get("MASTERMIND_NEPTUNE_EXPORT_URL", "http://127.0.0.1:18390/api/internal/neptune/backup"),
            updater_socket=os.environ.get("MASTERMIND_UPDATER_SOCKET"),
            updater_token_file=path("MASTERMIND_UPDATER_TOKEN_FILE"),
            updater_head_id=os.environ.get("MASTERMIND_UPDATER_HEAD_ID", "mastermind"),
            secret_directory=path("MASTERMIND_SECRET_DIRECTORY"),
            bridge_artifacts=Path(os.environ.get("MASTERMIND_BRIDGE_ARTIFACTS", "/app/bridge")),
            timezone=os.environ.get("MASTERMIND_TIMEZONE", "UTC"),
            credential_directory=path("MASTERMIND_CREDENTIAL_DIRECTORY"),
        )
