import os
import sys
import yaml
from fabric.connection import Connection

INVENTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory', sys.argv[1])
VARS = yaml.load(open(os.path.join(INVENTORY, "vars.yaml")), Loader=yaml.CLoader)
K3S_URL="https://%s:6443" % VARS["master"]

script = lambda *args: "curl -sfL https://www.drycc.cc/install.sh | bash -s - %s" % " ".join(args)


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


def install_carina():
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        conn.put(os.path.join(INVENTORY, "kubenetes", "carina.yaml"), "/tmp")
        run_script(
            conn,
            "; ".join([
                "helm repo add carina-csi-driver https://carina-io.github.io",
                "helm install carina-csi-driver carina-csi-driver/carina-csi-driver --set carina-scheduler.enabled=true,storage.create=false --create-namespace --namespace carina --wait",
                "kubectl apply -f /tmp/carina.yaml"
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
    install_carina()
    install_components()
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
                "||".join([
                    """lvs|awk '{print $2"/"$1}' | xargs lvremove {} -f""",
                    "echo clean lvs node %s ok" % host
                ]),
                out_stream=sys.stdout,
                asynchronous=True
            ).join()


if __name__ == "__main__":
    eval("{}()".format(sys.argv[2]))