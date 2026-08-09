import json


result = {
    "changed": False,
    "cell": str(AdminControl.getCell()),
    "connected_node": str(AdminControl.getNode()),
    "applications": sorted([item for item in str(AdminApp.list()).splitlines() if item]),
    "server_mbeans": len([item for item in str(AdminControl.queryNames("type=Server,*")).splitlines() if item]),
    "probe": "genuine-wsadmin-jython",
}
print("ANSIBLE_WAS_RESULT=" + json.dumps(result, sort_keys=True))
