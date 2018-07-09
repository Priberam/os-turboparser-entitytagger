#!/bin/bash
apt-get update
apt-get install -y wget build-essential automake autoconf git unzip libconfig++-dev libicu-dev python3 cython3 python3-flask python3-pip
pip3 install flask
pip3 install flask_cors
pip3 install wtforms
pip3 install requests
pip3 install tornado
pip3 install gevent
pip3 install sortedcontainers