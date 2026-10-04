"""MongoDB aggregate usage with idempotent update-event records."""
from utils import storage

def seed(targets):
    # Audience counts come directly from the broadcast-target collection.
    pass

def record(update_id, user=None, group=None, active=None, command=False, inline=False, migrate=None):
    from pymongo.errors import DuplicateKeyError
    try:
        storage.database()["usage_events"].insert_one({"_id": int(update_id), "command": bool(command), "inline": bool(inline)})
    except DuplicateKeyError:
        return []
    return []

def totals():
    baseline = storage.read("statistics", {"counts": {}, "since": "installation"})
    events = storage.database()["usage_events"]
    targets = storage.read("broadcast_targets", {"users": {}, "groups": {}})
    result = {key: int(baseline.get("counts", {}).get(key, 0)) + events.count_documents({field: True})
              for key,field in (("commands", "command"), ("inline", "inline"))}
    result.update(users=len(targets["users"]), groups=len(targets["groups"]), unknown_groups=0, since=baseline.get("since", "installation"))
    return result
