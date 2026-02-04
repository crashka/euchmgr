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

# NOTES:
# - even though we have a (hopefully) functionally complete .dockerignore, we still do
#   opt-in copying rather than a scary looking `COPY . ./`
# - inclusion of requirements.txt is purely for reference
# - `config` may be shadowed by a bind mount in deployment
# - `static` content may be served by an upstream (or "downstream" in nginx-speak) proxy
COPY requirements.txt *.py ./
COPY config ./config
COPY templates ./templates
COPY static ./static
COPY brackets ./brackets

# NOTE: `log` and `data` may be bind mounts in deployment
RUN mkdir log data sessions uploads

ENTRYPOINT ["gunicorn", "server:create_app(proxied=True)", "--access-logfile=-"]
CMD ["--bind=0.0.0.0:5050", "--threads=3"]
