FROM python:3.10-slim

ARG BASE_PATH=/code
WORKDIR $BASE_PATH

COPY . .

RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry lock
RUN poetry install

RUN apt-get update && apt-get install -y poppler-utils

EXPOSE 8080
CMD ["poetry", "run", "start"]