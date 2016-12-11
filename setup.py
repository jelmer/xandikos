#!/usr/bin/env python3
from distutils.core import setup

version = "0.0.1"

setup(name="dystros",
      description="VCS fastimport/fastexport parser",
      version=version,
      author="Jelmer Vernooij",
      author_email="jelmer@jelmer.uk",
      license="Apache v2 or later",
      url="https://www.jelmer.uk/projects/dystros",
      requires=['jinja2', 'icalendar', 'dulwich'],
      packages=['dystros'])
