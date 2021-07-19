FROM python:3.7

LABEL maintainer="Alexander Nwala <alexandernwala@gmail.com>"

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .

#CMD ["./serviceClusterStories.py"]