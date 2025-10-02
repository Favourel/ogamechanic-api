#!/usr/bin/env bash
set -o errexit

# Install requirements with forced source build for python-ldap
pip install --upgrade pip
pip install --no-binary=:all: -r requirements.txt
