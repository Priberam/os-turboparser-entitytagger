FROM ubuntu:16.04

# Install nedeed tools for TurboParser and TurboTextAnalysis
RUN apt-get update && apt-get install -y wget build-essential automake autoconf git unzip libconfig++-dev libicu-dev python3 cython3 python3-flask python3-pip
RUN pip3 install flask
RUN pip3 install flask_cors
RUN pip3 install wtforms
RUN pip3 install requests
RUN pip3 install tornado
RUN pip3 install gevent
RUN pip3 install sortedcontainers