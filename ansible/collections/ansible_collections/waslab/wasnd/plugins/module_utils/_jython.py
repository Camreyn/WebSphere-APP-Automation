# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type


BRIDGE = r'''import sys
import time


RESULT_PREFIX = "ANSIBLE_WAS_RESULT="
ERROR_PREFIX = "ANSIBLE_WAS_ERROR="


def lines(value):
    if not value:
        return []
    return [item for item in str(value).splitlines() if item]


def truth(value):
    if value:
        return 1
    return 0


def java_boolean(value):
    if truth(value):
        return "true"
    return "false"


def ordered_lines(value):
    result = lines(value)
    result.sort()
    return result


def runtime_info():
    version = str(sys.version)
    number = version.split()[0]
    pieces = number.split(".")
    generation = number
    if len(pieces) >= 2:
        generation = pieces[0] + "." + pieces[1]
    return {
        "implementation": "Jython",
        "version": version,
        "generation": generation,
        "supported": truth(generation == "2.1" or generation == "2.7"),
    }


def emit(value):
    print RESULT_PREFIX + repr(value)


def fail(message):
    print ERROR_PREFIX + str(message)
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


def wait_for_server(node_name, server_name, wanted, attempts, delay):
    for unused in range(attempts):
        if truth(server_runtime(node_name, server_name)) == truth(wanted):
            return 1
        time.sleep(delay)
    return 0


def operation_info(payload):
    result = {
        "cell": str(AdminControl.getCell()),
        "connected_node": str(AdminControl.getNode()),
        "applications": ordered_lines(AdminApp.list()),
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
    return {"changed": 0, "facts": result}


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
        return {"available": 1, "lines": lines(value), "raw": str(value or "")}
    except Exception, exc:
        # Some traditional WAS fix packs expose fewer AdminApp.view options.
        # Discovery must remain useful even when one optional view is absent.
        return {"available": 0, "lines": [], "raw": "", "error": str(exc)}


def operation_application_info(payload):
    name = payload["name"]
    installed = name in lines(AdminApp.list())
    if not installed:
        return {
            "changed": 0,
            "application": {
                "name": name,
                "installed": 0,
                "running": 0,
                "modules": [],
                "runtime_instances": [],
                "configuration": {},
            },
        }

    runtime_names = lines(AdminControl.queryNames("type=Application,name=%s,*" % name))
    return {
        "changed": 0,
        "application": {
            "name": name,
            "installed": 1,
            "running": truth(runtime_names),
            "modules": ordered_lines(AdminApp.listModules(name)),
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
    if not truth(payload.get("check_mode", 0)):
        AdminApp.export(name, destination)
    return {
        "changed": 1,
        "application": name,
        "destination": destination,
    }


def operation_cluster(payload):
    name = payload["name"]
    desired = payload["state"]
    check = truth(payload.get("check_mode", 0))
    configured = truth(cluster_id(name))
    runtime = runtime_state(cluster_runtime(name))
    before = {"configured": configured, "runtime_state": runtime}
    changed = 0

    if desired == "present" and not configured:
        changed = 1
        if not check:
            AdminTask.createCluster(
                "[-clusterConfig [-clusterName %s -preferLocal %s]]" %
                (name, java_boolean(payload.get("prefer_local", 1)))
            )
            AdminConfig.save()
    elif desired == "absent" and configured:
        changed = 1
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
            action = "stop"
            if wants_running:
                action = "start"
            AdminControl.invoke(mbean, action)

    after_configured = configured
    after_runtime = runtime
    if not check:
        after_configured = truth(cluster_id(name))
        after_runtime = runtime_state(cluster_runtime(name))
    elif changed:
        if desired == "present":
            after_configured = 1
        elif desired == "absent":
            after_configured = 0
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
    check = truth(payload.get("check_mode", 0))
    config = cluster_id(cluster_name)
    if not config:
        raise Exception("Cluster is not configured: " + cluster_name)
    member = member_id(config, node_name, member_name)
    running = truth(server_runtime(node_name, member_name))
    before = {"configured": truth(member), "running": running}
    changed = 0

    if desired == "present" and not member:
        changed = 1
        if not check:
            AdminTask.createClusterMember(
                "[-clusterName %s -memberConfig [-memberNode %s -memberName %s "
                "-memberWeight %s -genUniquePorts %s -replicatorEntry false]]" % (
                    cluster_name,
                    node_name,
                    member_name,
                    str(payload.get("weight", 2)),
                    java_boolean(payload.get("generate_unique_ports", 0)),
                )
            )
            AdminConfig.save()
    elif desired == "absent" and member:
        changed = 1
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
            changed = 1
            if not check:
                if running:
                    AdminControl.stopServer(member_name, node_name)
                    wait_for_server(node_name, member_name, 0, 60, 2)
                AdminControl.startServer(member_name, node_name)
                if not wait_for_server(node_name, member_name, 1, 90, 2):
                    raise Exception("Cluster member did not return after restart")

    after_member = truth(member)
    after_running = running
    if not check:
        after_member = truth(member_id(cluster_id(cluster_name), node_name, member_name))
        after_running = truth(server_runtime(node_name, member_name))
    if check and changed:
        if desired == "present":
            after_member = 1
        elif desired == "absent":
            after_member = 0
            after_running = 0
        elif desired == "started":
            after_running = 1
        elif desired == "stopped":
            after_running = 0
    return {
        "changed": changed,
        "before": before,
        "after": {"configured": after_member, "running": after_running},
    }


def operation_jvm_heap(payload):
    cluster_name = payload["cluster"]
    requested_initial = str(payload["initial_heap_mb"])
    requested_maximum = str(payload["maximum_heap_mb"])
    check = truth(payload.get("check_mode", 0))
    config = cluster_id(cluster_name)
    if not config:
        raise Exception("Cluster is not configured: " + cluster_name)
    changed = 0
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
    check = truth(payload.get("check_mode", 0))
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
    return {"changed": truth(synced), "synced": synced, "unavailable": unavailable}


def operation_application(payload):
    name = payload["name"]
    desired = payload["state"]
    check = truth(payload.get("check_mode", 0))
    installed = name in lines(AdminApp.list())
    runtime_names = lines(AdminControl.queryNames("type=Application,name=%s,*" % name))
    running = truth(runtime_names)
    before = {"installed": installed, "running": running}
    changed = 0

    if desired == "present":
        update = truth(payload.get("update", 0))
        if not installed:
            changed = 1
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
            changed = 1
            if not check:
                AdminApp.update(name, "app", "[-operation update -contents %s]" % payload["archive"])
                AdminConfig.save()
    elif desired == "absent" and installed:
        changed = 1
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
                action = "stopApplication"
                if wants_running:
                    action = "startApplication"
                AdminControl.invoke(manager, action, name)

    after_installed = installed
    after_running = running
    if not check:
        after_installed = name in lines(AdminApp.list())
        after_running = truth(lines(AdminControl.queryNames("type=Application,name=%s,*" % name)))
    if check and changed:
        if desired == "present":
            after_installed = 1
        elif desired == "absent":
            after_installed = 0
            after_running = 0
        elif desired == "started":
            after_running = 1
        elif desired == "stopped":
            after_running = 0
    return {
        "changed": changed,
        "before": before,
        "after": {"installed": after_installed, "running": after_running},
    }


try:
    operation = sys.argv[-2]
    payload_path = sys.argv[-1]
    payload_stream = open(payload_path, "r")
    try:
        # The controller writes only escaped literals from a strict, recursive
        # serializer. eval keeps the transport usable where json is absent.
        payload = eval(payload_stream.read(), {"__builtins__": {}})
    finally:
        payload_stream.close()
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
    runtime = runtime_info()
    if not runtime["supported"]:
        raise Exception(
            "Unsupported wsadmin Jython generation %s; expected 2.1 or 2.7"
            % runtime["generation"]
        )
    result = handlers[operation](payload)
    result["wsadmin_runtime"] = runtime
    emit(result)
except SystemExit:
    raise
except Exception, exc:
    fail(exc)
'''
