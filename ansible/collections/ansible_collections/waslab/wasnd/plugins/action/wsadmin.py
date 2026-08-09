# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    TRANSFERS_FILES = True

    def run(self, tmp=None, task_vars=None):
        task_vars = task_vars or {}
        result = super(ActionModule, self).run(tmp, task_vars)
        args = self._task.args.copy()
        source = args.get("src")
        if not source:
            raise AnsibleActionFail("src is required")
        created_tmp = None
        try:
            if not args.get("remote_src", False):
                source_path = self._find_needle("files", source)
                created_tmp = self._make_tmp_path()
                remote_path = self._connection._shell.join_path(
                    created_tmp,
                    os.path.basename(source_path),
                )
                self._transfer_file(source_path, remote_path)
                self._fixup_perms2((created_tmp, remote_path), execute=False)
                args["src"] = remote_path
                args["remote_src"] = True
            result.update(self._execute_module(
                module_name="waslab.wasnd.wsadmin",
                module_args=args,
                task_vars=task_vars,
                tmp=tmp,
            ))
        finally:
            if created_tmp:
                self._remove_tmp_path(created_tmp)
        return result
