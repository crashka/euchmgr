#########
# build #
#########

FROM python:3.12-slim AS build

RUN apt update
RUN apt install -y git
RUN apt install -y python3-venv
RUN apt install -y build-essential
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

WORKDIR /app/
COPY --from=build /app/venv /app/venv
ENV PATH="/app/venv/bin:${PATH}"

# TODO: mount ./log/ and ./data/ as volumes or bind mounts!!!
RUN mkdir log sessions data uploads

COPY requirements.txt *.py *.sh ./
COPY templates ./templates
COPY static ./static
# TODO: move the bracket files to ./static (so ./data/ can be a mount)!!!
COPY data/*.csv ./data/

ENTRYPOINT ["flask", "--app", "server", "run"]
CMD ["--host=0.0.0.0", "--port=5050", "--debug"]
