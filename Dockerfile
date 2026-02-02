#########
# build #
#########

FROM python:3.12-slim AS build

RUN apt update
RUN apt install -y git
RUN apt install -y python3-venv
RUN apt install -y build-essential
RUN apt install -y python3-dev
RUN apt install -y libsqlite3-dev

WORKDIR /app/
RUN python -m venv venv
ENV PATH="/app/venv/bin:${PATH}"

COPY requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip install --no-binary peewee -r requirements.txt

#######
# run #
#######

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV TZ=America/Los_Angeles

WORKDIR /app/
COPY --from=build /app/venv /app/venv
ENV PATH="/app/venv/bin:${PATH}"

# NOTE: `log` and `data` may be bind mounts in deployment
RUN mkdir log data sessions uploads

COPY requirements.txt *.py ./
COPY templates ./templates
COPY static ./static
COPY resources ./resources
COPY scripts ./scripts

ENTRYPOINT ["gunicorn", "server:create_app()", "--access-logfile=-"]
CMD ["--bind=0.0.0.0:5050", "--threads=3"]
