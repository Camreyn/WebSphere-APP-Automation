from __future__ import print_function

import os
import sys
import time


cell_name = os.environ.get("WAS_CELL_NAME", "LabCell01")
cluster_name = os.environ.get("WAS_CLUSTER_NAME", "AppCluster01")
server_name = os.environ.get("WAS_SERVER_NAME", "server1")
node_names = [
    os.environ.get("WAS_NODE1_NAME", "Node01"),
    os.environ.get("WAS_NODE2_NAME", "Node02"),
]
initial_heap = os.environ.get("WAS_INITIAL_HEAP_MB", "256")
maximum_heap = os.environ.get("WAS_MAX_HEAP_MB", "768")


def fail(message):
    print("WSADMIN_ERROR=" + str(message))
    sys.exit(1)


def config_id(path):
    return AdminConfig.getid(path)


try:
    missing_nodes = []
    for node_name in node_names:
        if not config_id("/Cell:%s/Node:%s/" % (cell_name, node_name)):
            missing_nodes.append(node_name)

    if missing_nodes:
        print("WAITING_FOR_NODES=true")
        print("MISSING_NODES=" + ",".join(missing_nodes))
        sys.exit(3)

    changed = False
    cluster_id = config_id("/Cell:%s/ServerCluster:%s/" % (cell_name, cluster_name))
    if not cluster_id:
        AdminTask.createCluster(
            "[-clusterConfig [-clusterName %s -preferLocal true]]" % cluster_name
        )
        AdminConfig.save()
        cluster_id = config_id("/Cell:%s/ServerCluster:%s/" % (cell_name, cluster_name))
        changed = True

    for node_name in node_names:
        server_id = config_id(
            "/Cell:%s/Node:%s/Server:%s/" % (cell_name, node_name, server_name)
        )
        if not server_id:
            AdminTask.createClusterMember(
                "[-clusterName %s -memberConfig "
                "[-memberNode %s -memberName %s -memberWeight 2 "
                "-genUniquePorts false -replicatorEntry false]]"
                % (cluster_name, node_name, server_name)
            )
            AdminConfig.save()
            server_id = config_id(
                "/Cell:%s/Node:%s/Server:%s/" % (cell_name, node_name, server_name)
            )
            changed = True

        jvms = AdminConfig.list("JavaVirtualMachine", server_id).splitlines()
        if jvms:
            jvm_id = jvms[0]
            current_initial = AdminConfig.showAttribute(jvm_id, "initialHeapSize")
            current_maximum = AdminConfig.showAttribute(jvm_id, "maximumHeapSize")
            if current_initial != initial_heap or current_maximum != maximum_heap:
                AdminConfig.modify(
                    jvm_id,
                    [["initialHeapSize", initial_heap], ["maximumHeapSize", maximum_heap]],
                )
                changed = True

    if changed:
        AdminConfig.save()

    for node_name in node_names:
        sync_mbean = AdminControl.completeObjectName("type=NodeSync,node=%s,*" % node_name)
        if sync_mbean:
            AdminControl.invoke(sync_mbean, "sync")

    time.sleep(2)
    cluster_mbean = AdminControl.completeObjectName("type=Cluster,name=%s,*" % cluster_name)
    if cluster_mbean:
        try:
            state = AdminControl.getAttribute(cluster_mbean, "state")
        except Exception:
            state = "unknown"
        if "running" not in str(state).lower():
            AdminControl.invoke(cluster_mbean, "start")
            changed = True

    print("CELL_NAME=" + cell_name)
    print("CLUSTER_NAME=" + cluster_name)
    print("CLUSTER_MEMBERS=" + ",".join([n + "/" + server_name for n in node_names]))
    print("CHANGED=" + ("true" if changed else "false"))
    print("BOOTSTRAP_COMPLETE=true")
except SystemExit:
    raise
except Exception as exc:
    fail(exc)
