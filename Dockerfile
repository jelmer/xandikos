# Docker file for Xandikos.
#
# Note that this dockerfile starts Xandikos without any authentication;
# for authenticated access we recommend you run it behind a reverse proxy.

FROM debian:sid-slim
LABEL maintainer="jelmer@jelmer.uk"
RUN apt-get update && \
    apt-get -y install python3-icalendar python3-dulwich python3-jinja2 python3-defusedxml python3-aiohttp python3-pip && \
    python3 -m pip install aiohttp-openmetrics && \
    apt-get clean
ADD . /code
WORKDIR /code
VOLUME /data
EXPOSE 8000
ENTRYPOINT python3 -m xandikos.web --port=8000 --listen-address=0.0.0.0 -d/data
CMD "--defaults"
