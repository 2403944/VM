import json
import os
import sys
from datetime import datetime, timedelta, timezone
 
from langsmith import Client
from langsmith.run_trees import RunTree
 
DATA_FILE = sys.argv[1] if len(sys.argv) > 1 else "data.json"
 
 
# --------------------------------------------------------------------------- #
# Virtual clock -- gives the trace realistic, strictly-increasing timestamps
# and durations without sleeping in real time.
# --------------------------------------------------------------------------- #
class Clock:
    def __init__(self, start):
        self.t = start
 
    def now(self):
        """Current time; nudged forward so every run gets a unique start."""
        t = self.t
        self.t += timedelta(milliseconds=50)
        return t
 
    def advance(self, seconds):
        self.t += timedelta(seconds=float(seconds))
        return self.t
 
 
# --------------------------------------------------------------------------- #
# Walk the data tree and emit runs depth-first.
# --------------------------------------------------------------------------- #
def emit(node, parent, clock, project, client):
    extra = {"metadata": node["metadata"]} if node.get("metadata") else None
    common = dict(
        name=node["name"],
        run_type=node["run_type"],
        inputs=node.get("inputs", {}),
        start_time=clock.now(),
        tags=node.get("tags", []),
        extra=extra,
    )
 
    if parent is None:
        rt = RunTree(project_name=project, client=client, **common)
    else:
        rt = parent.create_child(**common)
    rt.post()
 
    # Children run *before* this node ends, so they nest inside its time span.
    for child in node.get("children", []):
        emit(child, rt, clock, project, client)
 
    rt.end(outputs=node.get("outputs", {}),
           end_time=clock.advance(node.get("duration", 0.5)))
    rt.patch()
    return rt
 
 
def main():
    if not (os.getenv("LANGSMITH_API_KEY")):
        sys.exit(
            "ERROR: set LANGSMITH_API_KEY before running.\n"
            "  PowerShell:  $env:LANGSMITH_API_KEY = 'lsv2_...'"
        )
 
    if not os.path.exists(DATA_FILE):
        sys.exit(f"ERROR: data file not found: {DATA_FILE}")
 
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
 
    project = os.getenv("LANGSMITH_PROJECT") or data.get("project", "default")
 
    start_dt = datetime.now(timezone.utc)
    clock = Clock(start_dt)
 
    client = Client()  # reads LANGSMITH_API_KEY / LANGSMITH_ENDPOINT from env
    root = emit(data["trace"], None, clock, project, client)
 
    # Flush before exit so nothing is lost to the background sender.
    try:
        client.flush()
    except Exception:
        import time
        time.sleep(3)
 
    print("Trace logged to LangSmith.")
    print(f"  Data file : {DATA_FILE}")
    print(f"  Project   : {project}")
    print(f"  Trace id  : {root.id}")
    try:
        print(f"  View      : {root.get_url()}")
    except Exception:
        pass
 
 
if __name__ == "__main__":
    main()