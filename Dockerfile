FROM ubuntu:16.04_updated

# Install nedeed tools for TurboParser and TurboTextAnalysis
#RUN apt-get update && apt-get install -y wget build-essential automake autoconf git unzip libconfig++-dev libicu-dev python3 cython3 python3-flask python3-pip
#RUN pip3 install flask
#RUN pip3 install flask_cors
#RUN pip3 install wtforms
#RUN pip3 install requests
#RUN pip3 install tornado
#RUN pip3 install gevent
#RUN pip3 install sortedcontainers

# Install TurboParser
COPY TurboParser /TurboParser
WORKDIR /TurboParser
RUN sh install_deps.sh
RUN rm missing
RUN aclocal
RUN autoconf -f
RUN automake --add-missing
#RUN ./configure && make
WORKDIR /TurboParser/libturboparser
RUN make

# Install TurboTextAnalysis
COPY TurboTextAnalysis /TurboTextAnalysis
WORKDIR /TurboTextAnalysis/TurboTextAnalysis
RUN sed -ie 's/\/pba\/workspace\//\//g' Makefile
RUN make

# Install TurboTextAnalysisPython
WORKDIR /TurboTextAnalysis/TurboTextAnalysisPython
RUN sed -ie 's/\/pba\/workspace\//\//g' setup.py
RUN python3 setup.py install

WORKDIR /
RUN wget -r ftp://"ftp.priberam.pt|anonymous":@ftp.priberam.pt/SUMMAPublic/Models/EntityRecognition/v1
RUN mv ftp.priberam.pt/SUMMAPublic/Models/EntityRecognition/v1/* /TurboTextAnalysis/Data/

# Load turboserver by default
ENV LD_LIBRARY_PATH /TurboParser/deps/local/lib:/TurboParser/libturboparser:/TurboTextAnalysis/TurboTextAnalysis:TurboTextAnalysis/TurboTextAnalysisPython

COPY EntityDiscoveryLinkingPythonCli.py     /usr/bin  
COPY EntityTaggingAPIWP4SUMMA.py      		/usr/bin  
COPY TurboTextAnalysisServer.py 			/usr/bin
COPY entitytagginglauncher           		/usr/bin   
RUN chmod u+x /usr/bin/entitytagginglauncher   
WORKDIR /usr/bin

EXPOSE 5000
EXPOSE 5001
CMD entitytagginglauncher


