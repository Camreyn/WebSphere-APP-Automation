# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type


BRIDGE = r'''from __future__ import print_function

import json
import sys
import time


RESULT_PREFIX = "ANSIBLE_WAS_RESULT="
ERROR_PREFIX = "ANSIBLE_WAS_ERROR="


def lines(value):
    if not value:
        return []
    return [item for item in str(value).splitlines() if item]


def emit(value):
    print(RESULT_PREFIX + json.dumps(value, sort_keys=True))


def fail(message):
    print(ERROR_PREFIX + str(message))
    sys.exit(1)


def cluster_id(name):
    return AdminConfig.getid("/ServerCluster:%s/" % name)


def cluster_runtime(name):
    return AdminControl.completeObjectName("type=Cluster,name=%s,*" % name)


def runtime_state(object_name):
    if not object_name:
        return "unavailable"
    try:
        return str(AdminControl.getAttribute(object_name, "state"))
    except Exception:
        return "unknown"


def member_id(config_id, node_name, member_name):
    for item in lines(AdminConfig.list("ClusterMember", config_id)):
        if (AdminConfig.showAttribute(item, "nodeName") == node_name and
                AdminConfig.showAttribute(item, "memberName") == member_name):
            return item
    return ""


def server_runtime(node_name, server_name):
    return AdminControl.completeObjectName(
        "type=Server,node=%s,process=%s,*" % (node_name, server_name)
    )


def wait_for(predicate, wanted, attempts, delay):
    for unused in range(attempts):
        if bool(predicate()) == wanted:
            return True
        time.sleep(delay)
    return False


def operation_info(payload):
    result = {
        "cell": str(AdminControl.getCell()),
        "connected_node": str(AdminControl.getNode()),
        "applications": sorted(lines(AdminApp.list())),
        "clusters": [],
    }
    for item in lines(AdminConfig.list("ServerCluster")):
        name = str(AdminConfig.showAttribute(item, "name"))
        members = []
        for member in lines(AdminConfig.list("ClusterMember", item)):
            node_name = str(AdminConfig.showAttribute(member, "nodeName"))
            member_name = str(AdminConfig.showAttribute(member, "memberName"))
            members.append({
                "node": node_name,
                "name": member_name,
                "state": runtime_state(server_runtime(node_name, member_name)),
            })
        result["clusters"].append({
            "name": name,
            "state": runtime_state(cluster_runtime(name)),
            "members": members,
        })
    return {"changed": False, "facts": result}


def object_name_details(object_name):
    raw = str(object_name)
    details = {"object_name": raw}
    properties = raw.split(":", 1)[-1]
    for token in properties.split(","):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        details[str(key)] = str(value).strip('"')
    return details


def application_view(name, option):
    try:
        value = AdminApp.view(name, option)
        return {"available": True, "lines": lines(value), "raw": str(value or "")}
    except Exception as exc:
        # Some traditional WAS fix packs expose fewer AdminApp.view options.
        # Discovery must remain useful even when one optional view is absent.
        return {"available": False, "lines": [], "raw": "", "error": str(exc)}


def operation_application_info(payload):
    name = payload["name"]
    installed = name in lines(AdminApp.list())
    if not installed:
        return {
            "changed": False,
            "application": {
                "name": name,
                "installed": False,
                "running": False,
                "modules": [],
                "runtime_instances": [],
                "configuration": {},
            },
        }

    runtime_names = lines(AdminControl.queryNames("type=Application,name=%s,*" % name))
    return {
        "changed": False,
        "application": {
            "name": name,
            "installed": True,
            "running": bool(runtime_names),
            "modules": sorted(lines(AdminApp.listModules(name))),
            "runtime_instances": [object_name_details(item) for item in runtime_names],
            "configuration": {
                "module_targets": application_view(name, "-MapModulesToServers"),
                "context_roots": application_view(name, "-CtxRootForWebMod"),
                "virtual_hosts": application_view(name, "-MapWebModToVH"),
            },
        },
    }


def operation_application_export(payload):
    name = payload["name"]
    destination = payload["destination"]
    if name not in lines(AdminApp.list()):
        raise Exception("Application is not installed: " + name)
    if not bool(payload.get("check_mode", False)):
        AdminApp.export(name, destination)
    return {
        "changed": True,
        "application": name,
        "destination": destination,
    }


def operation_cluster(payload):
    name = payload["name"]
    desired = payload["state"]
    check = bool(payload.get("check_mode", False))
    configured = bool(cluster_id(name))
    runtime = runtime_state(cluster_runtime(name))
    before = {"configured": configured, "runtime_state": runtime}
    changed = False

    if desired == "present" and not configured:
        changed = True
        if not check:
            AdminTask.createCluster(
                "[-clusterConfig [-clusterName %s -preferLocal %s]]" %
                (name, str(payload.get("prefer_local", True)).lower())
            )
            AdminConfig.save()
    elif desired == "absent" and configured:
        changed = True
        if not check:
            AdminConfig.remove(cluster_id(name))
            AdminConfig.save()
    elif desired in ("started", "stopped"):
        if not configured:
            raise Exception("Cluster is not configured: " + name)
        is_running = "running" in runtime.lower()
        wants_running = desired == "started"
        changed = is_running != wants_running
        if changed and not check:
            mbean = cluster_runtime(name)
            if not mbean:
                raise Exception("Cluster runtime MBean is unavailable: " + name)
            AdminControl.invoke(mbean, "start" if wants_running else "stop")

    after_configured = configured
    after_runtime = runtime
    if not check:
        after_configured = bool(cluster_id(name))
        after_runtime = runtime_state(cluster_runtime(name))
    elif changed:
        if desired == "present":
            after_configured = True
        elif desired == "absent":
            after_configured = False
        elif desired == "started":
            after_runtime = "STARTED (check mode)"
        elif desired == "stopped":
            after_runtime = "STOPPED (check mode)"
    return {
        "changed": changed,
        "before": before,
        "after": {"configured": after_configured, "runtime_state": after_runtime},
    }


def operation_cluster_member(payload):
    cluster_name = payload["cluster"]
    node_name = payload["node"]
    member_name = payload["name"]
    desired = payload["state"]
    check = bool(payload.get("check_mode", False))
    config = cluster_id(cluster_name)
    if not config:
        raise Exception("Cluster is not configured: " + cluster_name)
    member = member_id(config, node_name, member_name)
    running = bool(server_runtime(node_name, member_name))
    before = {"configured": bool(member), "running": running}
    changed = False

    if desired == "present" and not member:
        changed = True
        if not check:
            AdminTask.createClusterMember(
                "[-clusterName %s -memberConfig [-memberNode %s -memberName %s "
                "-memberWeight %s -genUniquePorts %s -replicatorEntry false]]" % (
                    cluster_name,
                    node_name,
                    member_name,
                    str(payload.get("weight", 2)),
                    str(payload.get("generate_unique_ports", False)).lower(),
                )
            )
            AdminConfig.save()
    elif desired == "absent" and member:
        changed = True
        if not check:
            AdminTask.deleteClusterMember(
                "[-clusterName %s -memberNode %s -memberName %s]" %
                (cluster_name, node_name, member_name)
            )
            AdminConfig.save()
    elif desired in ("started", "stopped", "restarted"):
        if not member:
            raise Exception("Cluster member is not configured: %s/%s" % (node_name, member_name))
        if desired == "started":
            changed = not running
            if changed and not check:
                AdminControl.startServer(member_name, node_name)
        elif desired == "stopped":
            changed = running
            if changed and not check:
                AdminControl.stopServer(member_name, node_name)
        else:
            changed = True
            if not check:
                if running:
                    AdminControl.stopServer(member_name, node_name)
                    wait_for(lambda: server_runtime(node_name, member_name), False, 60, 2)
                AdminControl.startServer(member_name, node_name)
                if not wait_for(lambda: server_runtime(node_name, member_name), True, 90, 2):
                    raise Exception("Cluster member did not return after restart")

    after_member = bool(member_id(cluster_id(cluster_name), node_name, member_name)) if not check else bool(member)
    after_running = bool(server_runtime(node_name, member_name)) if not check else running
    if check and changed:
        if desired == "present":
            after_member = True
        elif desired == "absent":
            after_member = False
            after_running = False
        elif desired == "started":
            after_running = True
        elif desired == "stopped":
            after_running = False
    return {
        "changed": changed,
        "before": before,
        "after": {"configured": after_member, "running": after_running},
    }


def operation_jvm_heap(payload):
    cluster_name = payload["cluster"]
    requested_initial = str(payload["initial_heap_mb"])
    requested_maximum = str(payload["maximum_heap_mb"])
    check = bool(payload.get("check_mode", False))
    config = cluster_id(cluster_name)
    if not config:
        raise Exception("Cluster is not configured: " + cluster_name)
    changed = False
    members_result = []
    for member in lines(AdminConfig.list("ClusterMember", config)):
        node_name = str(AdminConfig.showAttribute(member, "nodeName"))
        member_name = str(AdminConfig.showAttribute(member, "memberName"))
        server = AdminConfig.getid("/Node:%s/Server:%s/" % (node_name, member_name))
        jvms = lines(AdminConfig.list("JavaVirtualMachine", server))
        if not jvms:
            continue
        jvm = jvms[0]
        old_initial = str(AdminConfig.showAttribute(jvm, "initialHeapSize"))
        old_maximum = str(AdminConfig.showAttribute(jvm, "maximumHeapSize"))
        member_changed = old_initial != requested_initial or old_maximum != requested_maximum
        if member_changed and not check:
            AdminConfig.modify(jvm, [
                ["initialHeapSize", requested_initial],
                ["maximumHeapSize", requested_maximum],
            ])
        changed = changed or member_changed
        members_result.append({
            "node": node_name,
            "member": member_name,
            "before": {"initial": old_initial, "maximum": old_maximum},
            "after": {"initial": requested_initial, "maximum": requested_maximum},
            "changed": member_changed,
        })
    if changed and not check:
        AdminConfig.save()
    return {"changed": changed, "members": members_result}


def operation_node_sync(payload):
    check = bool(payload.get("check_mode", False))
    requested = payload.get("nodes") or []
    if not requested:
        requested = []
        for node in lines(AdminConfig.list("Node")):
            name = str(AdminConfig.showAttribute(node, "name"))
            if name != str(AdminControl.getNode()):
                requested.append(name)
    synced = []
    unavailable = []
    for node_name in requested:
        mbean = AdminControl.completeObjectName("type=NodeSync,node=%s,*" % node_name)
        if not mbean:
            unavailable.append(node_name)
        elif not check:
            synced.append({"node": node_name, "result": str(AdminControl.invoke(mbean, "sync"))})
        else:
            synced.append({"node": node_name, "result": "check mode"})
    return {"changed": bool(synced), "synced": synced, "unavailable": unavailable}


def operation_application(payload):
    name = payload["name"]
    desired = payload["state"]
    check = bool(payload.get("check_mode", False))
    installed = name in lines(AdminApp.list())
    runtime_names = lines(AdminControl.queryNames("type=Application,name=%s,*" % name))
    running = bool(runtime_names)
    before = {"installed": installed, "running": running}
    changed = False

    if desired == "present":
        update = bool(payload.get("update", False))
        if not installed:
            changed = True
            if not check:
                options = "[-appname %s" % name
                if payload.get("cluster"):
                    options += " -cluster %s" % payload["cluster"]
                if payload.get("context_root"):
                    options += " -contextroot %s" % payload["context_root"]
                if payload.get("virtual_host"):
                    options += " -usedefaultbindings -defaultbinding.virtual.host %s" % payload["virtual_host"]
                options += "]"
                AdminApp.install(payload["archive"], options)
                AdminConfig.save()
        elif update:
            changed = True
            if not check:
                AdminApp.update(name, "app", "[-operation update -contents %s]" % payload["archive"])
                AdminConfig.save()
    elif desired == "absent" and installed:
        changed = True
        if not check:
            AdminApp.uninstall(name)
            AdminConfig.save()
    elif desired in ("started", "stopped"):
        if not installed:
            raise Exception("Application is not installed: " + name)
        wants_running = desired == "started"
        changed = running != wants_running
        if changed and not check:
            for manager in lines(AdminControl.queryNames("type=ApplicationManager,*")):
                AdminControl.invoke(manager, "startApplication" if wants_running else "stopApplication", name)

    after_installed = name in lines(AdminApp.list()) if not check else installed
    after_running = bool(lines(AdminControl.queryNames("type=Application,name=%s,*" % name))) if not check else running
    if check and changed:
        if desired == "present":
            after_installed = True
        elif desired == "absent":
            after_installed = False
            after_running = False
        elif desired == "started":
            after_running = True
        elif desired == "stopped":
            after_running = False
    return {
        "changed": changed,
        "before": before,
        "after": {"installed": after_installed, "running": after_running},
    }


try:
    operation = sys.argv[-2]
    payload_path = sys.argv[-1]
    with open(payload_path, "r") as payload_stream:
        payload = json.load(payload_stream)
    handlers = {
        "info": operation_info,
        "application_info": operation_application_info,
        "application_export": operation_application_export,
        "cluster": operation_cluster,
        "cluster_member": operation_cluster_member,
        "jvm_heap": operation_jvm_heap,
        "node_sync": operation_node_sync,
        "application": operation_application,
    }
    if operation not in handlers:
        raise Exception("Unsupported waslab operation: " + operation)
    emit(handlers[operation](payload))
except SystemExit:
    raise
except Exception as exc:
    fail(exc)
'''
