from uuid import uuid4

import pytest

from mastermind.backup_policy import BackupPolicy, NeptuneError, restored_record

INTENT = {"schema":"exocortex.backup.intent.v1", "archive":{"enabled":True,"intervalHours":17}, "mirror":None, "sourceRevision":4}

def test_newer_restore_cannot_be_cleared_by_previous_resume(service):
    _, store, _, _ = service
    first, second = restored_record(INTENT), restored_record({**INTENT,"archive":{"enabled":False,"intervalHours":31}})
    store.set_backup_policy_pending(first)
    class Client:
        def policy(self, method="GET", body=None, suffix=""):
            if body and body["kind"] == "resume":
                store.set_backup_policy_pending(second)
            return {"schema":"exocortex.backup.policy.v1", "revision":6,"appliedRevision":6,"paused":False}
    policy=BackupPolicy(Client(),store,lambda:True)
    with pytest.raises(NeptuneError,match="newer restore"):
        policy.mutate({"kind":"resume","requestId":str(uuid4()),"expectedRevision":4})
    assert (store.backup_policy_pending())["requestId"] == second["requestId"]
    with pytest.raises(NeptuneError,match="paused"):
        policy.assert_export_ready()

def test_lost_resume_ack_replays_same_durable_identity(service):
    _, store, _, _ = service
    store.set_backup_policy_pending(restored_record(INTENT))
    resumes=[]
    class Client:
        def policy(self, method="GET", body=None, suffix=""):
            if body and body["kind"] == "resume":
                resumes.append(dict(body))
                if len(resumes)==1:
                    raise NeptuneError("lost acknowledgement")
            return {"schema":"exocortex.backup.policy.v1", "revision":6,"appliedRevision":6,"paused":False}
    client=Client()
    with pytest.raises(NeptuneError,match="lost acknowledgement"):
        BackupPolicy(client,store,lambda:True).mutate({"kind":"resume","requestId":str(uuid4()),"expectedRevision":4})
    assert store.backup_policy_pending()
    BackupPolicy(client,store,lambda:True).mutate({"kind":"resume","requestId":str(uuid4()),"expectedRevision":4})
    assert resumes[0] == resumes[1]
    assert store.backup_policy_pending() is None
