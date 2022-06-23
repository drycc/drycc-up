import os
import sys
import yaml
from fabric.group import SerialGroup
from fabric.connection import Connection

INVENTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory', sys.argv[1])
VARS = yaml.load(open(os.path.join(INVENTORY, "vars.yaml")), Loader=yaml.CLoader)
K3S_URL="https://%s:6443" % VARS["master"]

script = lambda *args: "curl -sfL https://drycc.cc/install.sh | bash -s - %s" % " ".join(args)

def master():
    with Connection(VARS["master"], inline_ssh_env=True) as conn:
        conn.config.run.env = VARS["environment"]
        conn.run(script("check_metallb", "install_k3s_server", "install_helm", "install_components"))

def slave():
    with SerialGroup(VARS["slave"], inline_ssh_env=True) as conn:
        conn.config.run.env = VARS["environment"]
        conn.config.run.env["K3S_URL"] = "https://%s:6443" % VARS["master"]
        conn.run(script("install_k3s_server", "install_helm"))


def agent():
    with SerialGroup(VARS["agent"], inline_ssh_env=True) as conn:
        conn.config.run.env = VARS["environment"]
        conn.config.run.env["K3S_URL"] = "https://%s:6443" % VARS["master"]
        conn.run(script("install_k3s_agent"))


def lvmvg():
    pass


def openebs():
    pass


def metallb():
    pass


if __name__ == "__main__":
    master()