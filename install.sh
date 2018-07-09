#!/bin/bash
apt-get update
apt-get install -y wget build-essential automake autoconf git unzip libconfig++-dev libicu-dev python3 cython3 python3-flask

apt-get install -y python3-pip
pip3 install --upgrade pip
pip3 install flask
pip3 install flask_cors
pip3 install wtforms
pip3 install requests
pip3 install tornado
pip3 install gevent
pip3 install sortedcontainers

current_path="$(pwd)"
outer_context="../.."

cd TurboParser
./install_deps.sh
rm missing
aclocal
autoconf -f
automake --add-missing
./configure && make
cd libturboparser
make
cd ../..

cd TurboTextAnalysis/TurboTextAnalysis
find="/pba/workspace"
sed -ie "s?${find}?${outer_context}?g" Makefile
make

cd ..
cd TurboTextAnalysisPython
sed -ie "s?${find}?${outer_context}?g" setup.py
python3 setup.py build_ext --inplace

cd ..
cd CrossPlatfTurboTextAnalysis
find="/pba/workspace"
sed -ie "s?${find}?${outer_context}?g" Makefile
make

add_to_ld_library_path=":/pba/workspace/TurboParser/deps/local/lib/:/pba/workspace/TurboParser/libturboparser/:/pba/workspace/TurboTextAnalysis/TurboTextAnalysis:/pba/workspace/TurboTextAnalysis/TurboTextAnalysisPython"
add_to_ld_library_path=${add_to_ld_library_path//$find/$current_path}
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:${add_to_ld_library_path}



