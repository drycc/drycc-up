#coding:utf-8

import os
import sys
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

readme_file = os.path.join(here, 'README.md')

def read_text(file_path):
    """
    fix the default operating system encoding is not utf8.
    """
    if sys.version_info.major < 3:
        with open(file_path) as f:
            return f.read()
    with open(file_path, encoding="utf8") as f:
        return f.read()

README = read_text(os.path.join(here, 'README.md'))

requires = [
    "jinja2",
    "fabric",
    "pyyaml",
]

setup(
    name='drycc_up',
    description='a drycc up tools',
    version='3.1.7',
    author='duanhongyi',
    author_email='duanhongyi@doopai.com',
    packages=find_packages(),
    include_package_data=True,
    long_description=README,
    url='https://github.com/drycc/drycc-up',
    install_requires=requires,
    platforms='all platform',
    license='BSD',
    entry_points={
        'console_scripts': ['drycc-up=drycc_up.install:main']
    }
)