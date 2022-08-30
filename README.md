# What is Drycc UP

Drycc UP is a tool to download and install Drycc components.

## Requirements

The core of the script is written in fabric, so the only dependency is to need a latest version of Python runtime environment.

## Install Drycc UP

Virtual environment installation is recommended.

```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

## Installing Drycc

Please refer to the contents of the `inventory/sample` directory for specific configuration. If we have an env with the same configuration as the `inventory/sample` directory, we will start the installation process:

```
python install.py sample install_all
```

See the install.py file for other functions.