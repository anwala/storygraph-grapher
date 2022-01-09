FROM python:3.7

LABEL maintainer="Alexander Nwala <alexandernwala@gmail.com>"

WORKDIR /src
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt && python -m spacy download en_core_web_sm
COPY . .
