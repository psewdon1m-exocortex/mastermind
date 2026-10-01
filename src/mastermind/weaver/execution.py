"""Weaver placement execution through the single canonical mutation coordinator.

Crusher supplies validated content and its existing durable checkpoint adapter.
No alternate writer, new job format or replay semantics are introduced.
"""
import json
import re
import time
from pathlib import PurePosixPath

from ..errors import DomainError
from ..extractors import scrub
from ..fs import name_key, sha_bytes
from .template import render as render_template


class PlacementExecutor:
    def __init__(self, weaver):
        self.weaver = weaver

    def commit(self, job, validated, placement):
        if job.service is not self.weaver.service:
            raise DomainError('PLACEMENT_SCOPE', 'The job belongs to another Vault.', 403)
        vault = job.service.vault
        if time.time() >= job.record["deadline"]:
            raise DomainError("JOB_DEADLINE", "No commit may start after the accepted job deadline.", 408)
        with job.service.coordinator.boundary() as operation_id:
            job.service.data_ready()
            current = job.state.one("SELECT * FROM jobs WHERE id=?", (job.row["id"],))
            if current["state"] == "COMPLETED":
                return {'schema': 'weaver.placement.v1', 'operation_id': job.row['id'],
                        **json.loads(current['record']).get('commit', {})}
            placement = self.weaver.policy.revalidate(placement, job.record["context_snapshot"])
            anchor = placement["anchor"]
            if anchor and any(c in PurePosixPath(anchor).stem for c in "[]#^|"):
                raise DomainError("FALLBACK_INVALID", "The selected graph reference is unsupported.", 422)
            directory = "root/crusher"
            names = {row["name_key"] for row in job.state.rows("SELECT name_key FROM notes")}
            title = validated["title"]
            candidate = title
            for number in range(2, 100002):
                if name_key(candidate) not in names:
                    break
                candidate = f"{title} ({number})"
            else:
                raise DomainError("FILENAME_LIMIT", "A unique filename could not be allocated.", 409)
            relative = str(PurePosixPath(directory) / (candidate+".md"))
            vault.validate_destination(relative)
            snapshot = job.record["context_snapshot"]
            source_label = re.sub(r"([\\`*_{}\[\]()#+.!<>|@])", r"\\\1", scrub(job.record["source_label"]))
            body = render_template(snapshot["template"], validated, sources=source_label,
                link="[["+PurePosixPath(anchor).stem+"]]", timestamp=snapshot["timestamp"], timezone=snapshot["timezone"])
            body += job.provenance(placement)
            data = body.encode("utf-8")
            if len(data) > job.service.config.max_note_bytes:
                raise DomainError("GENERATED_NOTE_INVALID", "The rendered note exceeds its supported size.", 413)
            job.record["commit"] = {"path": relative, "sha256": sha_bytes(data), "placement": placement}
            job.save()
            job.fault("before-commit")
            job.service.coordinator.commit({relative: data}, {relative: None},
                {"job_id": job.row["id"], "committed_path": relative, "committed_sha": sha_bytes(data)},
                inside_boundary=True, operation_id=operation_id)
            job.fault("after-commit")
            vault.index()
            job.row = job.state.one("SELECT * FROM jobs WHERE id=?", (job.row["id"],))
            job.record = json.loads(job.row["record"])
            job.service.audit.emit("crusher.commit", target=job.row["id"], context={"outcome": "durable"})
            return {'schema': 'weaver.placement.v1', 'operation_id': job.row['id'], **job.record['commit']}

