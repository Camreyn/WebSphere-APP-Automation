# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r'''
options:
  install_root:
    description: Traditional WebSphere installation root.
    type: path
    default: /opt/WebSphere/AppServers
  profile_name:
    description: Deployment manager profile used to run wsadmin.
    type: str
    default: Dmgr01
  wsadmin_path:
    description: Explicit path to genuine wsadmin.sh; defaults to the selected profile.
    type: path
  username:
    description: WebSphere administrative user.
    type: str
    required: true
  password:
    description: WebSphere administrative password.
    type: str
    required: true
  host:
    description: SOAP connector host as seen from wsadmin.
    type: str
    default: localhost
  port:
    description: SOAP connector port.
    type: int
    default: 8879
  timeout:
    description: Maximum administrative operation time in seconds.
    type: int
    default: 300
'''
