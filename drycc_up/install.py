import os
import shutil
import sys
import yaml
from fabric.connection import Connection

INVENTORY = os.path.join('inventory')
VARS = None
K3S_URL = None

script = lambda *args: "curl -sfL https://www.drycc.cc/install.sh | bash -s - %s" % " ".join(args)



def init():
    global VARS, K3S_URL
    VARS = yaml.load(open(os.path.join(INVENTORY, "vars.yaml")), Loader=yaml.CLoader)
    K3S_URL="https://%s:6443" % VARS["master"]


def run_script(runner, command, envs=None, **kwargs):
    envs = {} if envs is None else envs
    envs.update(VARS["environment"])
    create_env_file = """
rm -rf /tmp/environment; cat << EOF > "/tmp/environment"
%s
EOF
""" % "\n".join(["export %s=%s" % (key, value) for key, value in envs.items()])
    runner.run(create_env_file)
    command = "; ".join([
        "source /tmp/environment",
        command
    ])
    return runner.run(command, **kwargs)


def prepare():
    for item in VARS["prepare"]:
        with Connection(
            host=item["host"],
            user=VARS["user"],
            connect_kwargs={"key_filename": VARS["key_filename"]}
        ) as conn:
            for command in item["commands"]:
                run_script(
                    conn,
                    command,
                    out_stream=sys.stdout,
                    asynchronous=True
                ).join()


def get_token():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        result = run_script(conn, "cat /var/lib/rancher/k3s/server/token", hide=True)
        return result.stdout.strip()


def install_master():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        run_script(
            conn,
            script("install_k3s_server", "install_helm"),
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_slaves():
    for host in VARS["slave"]:
        with Connection(
            host=host,
            user=VARS["user"],
            connect_kwargs={"key_filename": VARS["key_filename"]}
        ) as conn:
            run_script(
                conn,
                script("install_k3s_server"),
                envs={"K3S_URL": K3S_URL, "K3S_TOKEN": get_token()},
                out_stream=sys.stdout,
                asynchronous=True
            ).join()


def install_agents():
    for host in VARS["agent"]:
        with Connection(
            host=host,
            user=VARS["user"],
            connect_kwargs={"key_filename": VARS["key_filename"]}
        ) as conn:
            run_script(
                conn,
                script("install_k3s_agent"),
                envs={"K3S_URL": K3S_URL, "K3S_TOKEN": get_token()},
                out_stream=sys.stdout,
                asynchronous=True
            ).join()


def label_nodes():
    with Connection(
            host=VARS["master"],
            user=VARS["user"],
            connect_kwargs={"key_filename": VARS["key_filename"]}
        ) as conn:
        for item in VARS["label"]:
            node = item["node"]
            for label in item["labels"]:
                key, value = label["key"], label["value"]
                command = f"kubectl label nodes {node} {key}={value} --overwrite"
                run_script(
                    conn,
                    command,
                    out_stream=sys.stdout,
                    asynchronous=True
                ).join()


def install_network():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        run_script(
            conn,
            script("install_network"),
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_metallb():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        conn.put(os.path.join(INVENTORY, "kubenetes", "metallb.yaml"), "/tmp")
        run_script(
            conn,
            script("install_metallb"),
            envs={
                "METALLB_CONFIG_FILE": "/tmp/metallb.yaml",
            },
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_topolvm():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        conn.put(os.path.join(INVENTORY, "kubenetes", "topolvm.yaml"), "/tmp")
        run_script(
            conn,
            ";".join([
                "helm repo add topolvm https://topolvm.github.io/topolvm",
                "helm repo update",
                "helm install topolvm topolvm/topolvm -n topolvm --create-namespace -f /tmp/topolvm.yaml --wait"  # noqa
            ]),
            envs=None,
            out_stream=sys.stdout,
            asynchronous=True
        ).join()

def install_components():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        run_script(
            conn,
            script("install_traefik", "install_cert_manager", "install_catalog"),
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_drycc():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        run_script(
            conn,
            script("install_drycc", "install_helmbroker"),
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_all():
    prepare()
    install_master()
    install_slaves()
    install_agents()
    install_network()
    install_metallb()
    label_nodes()
    install_components()
    install_topolvm()
    install_drycc()

def clean_all():
    hosts = []
    hosts.append(VARS["master"])
    hosts.extend(VARS["slave"])
    hosts.extend(VARS["agent"])
    for host in hosts:
        with Connection(
            host=host,
            user=VARS["user"],
            connect_kwargs={"key_filename": VARS["key_filename"]}
        ) as conn:
            run_script(
                conn,
                "||".join([
                    "curl -sfL https://www.drycc.cc/uninstall.sh | bash - > /dev/null 2>&1",
                    "echo clean k3s node %s ok" % host
                ]),
                out_stream=sys.stdout,
                asynchronous=True
            ).join()
            run_script(
                conn,
                ";".join([
                    """lvs|awk '{print $2"/"$1}' | xargs lvremove -f""",
                    """vgs --noheadings|awk '{print $1}'| xargs vgremove -f""",
                    """pvs --noheadings|awk '{print $1}'| xargs pvremove -f""",
                    "echo clean lvs node %s ok" % host
                ]),
                out_stream=sys.stdout,
                asynchronous=True
            ).join()

usage = """

A tool for fast installation of drycc clusters.

Usage: drycc-up <command> [<args>...]

command:

  run        run an installation process.
  template   generate installation template.

Use 'drycc-up run install_all' to deploy clusters.
"""
def main():
    if len(sys.argv) > 2 and sys.argv[1] == "run":
        init()
        eval("{}()".format(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "template":
        if not os.path.exists("inventory"):
            current = os.path.dirname(os.path.abspath(__file__))
            shutil.copytree(os.path.join(current, "templates"), "inventory")
        else:
            print("the inventory directory already exists")
    else:
        print(usage)

if __name__ == "__main__":
    main()
