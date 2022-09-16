# What is Drycc UP

Drycc UP is a tool to download and install Drycc components.

## Requirements

The core of the script is written in fabric, so the only dependency is to need a latest version of Python runtime environment.

## Install Drycc UP

Virtual environment installation is recommended.

```
python3 -m venv .venv
source .venv/bin/activate
pip3 install https://github.com/drycc/drycc-up/archive/refs/heads/main.zip
```

## Installing Drycc

First, you need to generate the configuration template file.

```
drycc-up template
```

Modify the files in the inventory directory, and then execute the installation command to install the cluster.

```
python install.py sample install_all
```

See the install.py file for other functions.