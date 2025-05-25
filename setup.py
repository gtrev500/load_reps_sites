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
            "district-offices-scrape=cli.scrape:main",
            "district-offices-validate=district_offices.validation.runner:main",
            "district-offices-find-contacts=district_offices.processing.contact_finder:main",
        ],
    },
)