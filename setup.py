"""Setuptools configuration for pip install.

Used for `pip install -e .` so the package and its UI assets are installed.
Terminal-only distribution: no py2app; run via alias liscribe from install.sh.
"""

from setuptools import find_packages, setup

# UI assets included in the package (panels, assets)
PACKAGE_DATA_LISCRIBE = [
    "ui/panels/*.html",
    "ui/assets/*",
]

setup(
    name="liscribe",
    version="2.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={"liscribe": PACKAGE_DATA_LISCRIBE},
)
