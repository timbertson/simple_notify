#!/usr/bin/env python

## NOTE: ##
## setup.py is not maintained, and is only provided for convenience.
## please see http://gfxmonk.net/dist/0install/index/ for
## up-to-date installable packages.

from setuptools import *
setup(
	name='simple_notify',
	version='0.1.1',
	author_email='tim@gfxmonk.net',
	author='Tim Cuthbertson',
	url='http://gfxmonk.net/dist/0install/simple_notify.xml',
	description="simple inotify wrapper",
	long_description="simple inotify wrapper",
	py_modules = ['simple_notify'],
	license='BSD',
)
