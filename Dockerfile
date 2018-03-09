FROM python:3

LABEL maintainer="Alexander Nwala <anwala@cs.odu.edu>"

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.txt .
RUN git clone https://github.com/anwala/Util.git
RUN pip install --no-cache-dir -r ./Util/requirements.txt
RUN mv ./Util/genericCommon.py .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

#CMD ["./serviceClusterStories.py"]