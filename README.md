# What is Drycc UP

Drycc UP is a tool to download and install Drycc components.

## Requirements

The core of the script is written in fabric, so the only dependency is to need a latest version of Python runtime environment.

## Install Drycc UP

Virtual environment installation is recommended.

```
python3 -m venv .venv
source .venv/bin/activate
pip3 install https://drycc-mirrors.drycc.cc/drycc/drycc-up/archive/refs/heads/main.zip
```

## Installing Drycc

First, you need to generate the configuration template file.

```
drycc-up template
```

Modify the files in the inventory directory, and then execute the installation command to install the cluster.

```
drycc-up run install_all
```

See the install.py file for other functions.

## Best practices

* Suggest using BGP network when conditions permit.
* Suggest deploying no less than 4 nodes for the first time.
* Suggest that the number of slave nodes should not be less than 2.
* When there are both fast and slow disks, it is recommended to use bcache.
