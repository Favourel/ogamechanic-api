#!/usr/bin/env bash
# Install system dependencies needed for python-ldap
apt-get update
apt-get install -y libldap2-dev libsasl2-dev libssl-dev
