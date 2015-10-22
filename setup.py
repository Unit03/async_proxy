#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from setuptools import setup

setup(name="Async proxy",
      version="1.0",
      author="Jacek Kołodziej",
      author_email="kolodziejj@gmail.com",
      py_modules=["proxy"],
      scripts=["proxy.py"],
      install_requires=["werkzeug"],
      extras_require={
          "tests": [
              "pytest",
              "requests",
          ],
      },
      )
