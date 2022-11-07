import os
import re
import shutil
import sys
import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from fabric.connection import Connection

INVENTORY = os.path.join('templates')
VARS = None
K3S_URL = None
CHARS_URL = None

script = lambda *args: "curl -sfL https://www.drycc.cc/install.sh | bash -s - %s" % " ".join(args)


def init():
    global VARS, K3S_URL, CHARS_URL
    VARS = yaml.load(open(os.path.join(INVENTORY, "vars.yaml")), Loader=yaml.Loader)
    K3S_URL="https://%s:6443" % VARS["master"]
    if VARS["environment"]["CHANNEL"] == "stable":
        CHARS_URL = "oci://registry.drycc.cc/charts"
    else:
        CHARS_URL = "oci://registry.drycc.cc/charts-testing"


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


def render_yaml(template, **kwargs):
    env = Environment(loader=FileSystemLoader("templates"))
    return env.get_template(template).render(kwargs)


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


def helm_install(name, chart_url, wait=False):
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        values_file = "/tmp/%s.yaml" % name 
        with open(values_file , "w") as f:
            f.write(render_yaml("helm/%s.yaml" % name, **VARS["environment"]))
        conn.put(values_file, "/tmp")
        os.remove(values_file)
        command = "helm install %s %s -f %s -n %s --create-namespace" % (
            name,
            chart_url,
            values_file,
            name
        )
        if wait:
            command = "%s --wait" % command
        run_script(
            conn,
            command,
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


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
        result = run_script(
            conn,
            "curl -Ls https://drycc-mirrors.drycc.cc/topolvm/topolvm/releases|grep /topolvm/topolvm/releases/tag/",
            envs=None,
            out_stream=open(os.devnull, 'w'),
            asynchronous=False
        )
        versions = []
        for tag in result.stdout.strip().split("\n"):
            m = re.search("/topolvm/topolvm/releases/tag/topolvm-chart-v[0-9\.]{1,}", tag)
            if m:
                versions.append(m.group().replace("/topolvm/topolvm/releases/tag/", ""))
        if len(versions) == 0:
            raise ValueError("Cannot get the topolvm version")
        print("topolvm versions: ", versions)
        url = "https://drycc-mirrors.drycc.cc/topolvm/topolvm/archive/refs/tags/{}.tar.gz".format(
            versions[0]
        )
        script = ";".join([
            "rm -rf topolvm-*",
            "curl -o tmp.tar.gz %s" % url,
            "tar -xvzf tmp.tar.gz",
            "cd topolvm-topolvm-chart-*/charts/topolvm",
            "helm dependency update",
            "helm install topolvm . -n topolvm --create-namespace -f /tmp/topolvm.yaml --wait",
            "cd -",
            "rm -rf topolvm-* tmp.tar.gz",
        ])
        run_script(conn, script, envs=None, out_stream=sys.stdout, asynchronous=True).join()

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


def install_manager():
    helm_install("drycc-manager", "%s/manager" % CHARS_URL, True)


def install_helmbroker():
    helm_install("drycc-helmbroker", "%s/helmbroker" % CHARS_URL, True)
    with Connection(
        host=VARS["master"],
        user=VARS["user"],
        connect_kwargs={"key_filename": VARS["key_filename"]}
    ) as conn:
        name = "catalog"
        kube_file = "/tmp/%s.yaml" % name 
        with open(kube_file , "w") as f:
            f.write(render_yaml("kubenetes/%s.yaml" % name, **VARS["environment"]))
        conn.put(kube_file, "/tmp")
        os.remove(kube_file)
        run_script(
            conn,
            "kubectl apply -f %s" % kube_file,
            out_stream=sys.stdout,
            asynchronous=True
        ).join()


def install_drycc():
    helm_install("drycc", "%s/workflow" % CHARS_URL, True)


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
            shutil.copytree(os.path.join(current, "templates"), "templates")
        else:
            print("the inventory directory already exists")
    else:
        print(usage)

if __name__ == "__main__":
    init()
    print(render_yaml("helm/drycc.yaml", **VARS["environment"]))