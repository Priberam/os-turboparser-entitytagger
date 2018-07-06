FROM ubuntu:16.04

# Install nedeed tools for TurboParser and TurboTextAnalysis
RUN apt-get update
RUN apt-get install -y build-essential automake autoconf git unzip libconfig++8-dev libicu-dev python3 cython3 python3-flask

# Install TurboParser
WORKDIR /TurboParser
RUN sh install_deps.sh
RUN rm missing
RUN aclocal
RUN autoconf
RUN automake --add-missing
RUN ./configure && make
WORKDIR /TurboParser/libturboparser
RUN make

# Install TurboTextAnalysis
WORKDIR /TurboTextAnalysis/TurboTextAnalysis
RUN sed -ie 's/pba\/workspace/g' Makefile
RUN make

# Install TurboTextAnalysisPython
WORKDIR /TurboTextAnalysis/TurboTextAnalysisPython
RUN sed -ie 's/pba\/workspace/g' setup.py
RUN python3 setup.py install

WORKDIR /
RUN wget -r ftp://"ftp.priberam.pt|anonymous":@ftp.priberam.pt/SUMMAPublic/Models/EntityRecognition/v1
RUN cp ftp.priberam.pt/SUMMAPublic/Models/EntityRecognition/v1/* TurboTextAnalysis/Data/

WORKDIR /root
ENV baseDir .
COPY ${baseDir}/turbo_parser_server.py  /usr/bin
COPY ${baseDir}/app.py  /usr/bin
RUN chmod a+x /usr/bin/app.py

EXPOSE 5000

# Load turboserver by default
ENV LD_LIBRARY_PATH /TurboParser/libturboparser:/TurboTextAnalysis/TurboTextAnalysis:/TurboParser/deps/local/lib
CMD app.py