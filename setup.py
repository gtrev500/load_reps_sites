#!/usr/bin/env python3
"""Setup script for district-offices package."""

from setuptools import setup, find_packages

setup(
    packages=find_packages(where="src") + ["cli"],
    package_dir={
        "": "src",
        "cli": "cli"
    },
    entry_points={
        "console_scripts": [
            "district-offices=cli.main:main",
            "district-offices-scrape=cli.scrape:main",
            "district-offices-validate=cli.validate:main",
            "district-offices-find-contacts=cli.find_contacts:main",
        ],
    },
)