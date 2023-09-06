# Docker file for Xandikos.
#
# Note that this dockerfile starts Xandikos without any authentication;
# for authenticated access we recommend you run it behind a reverse proxy.

FROM debian:sid-slim
LABEL maintainer="jelmer@jelmer.uk"
RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-icalendar python3-dulwich python3-jinja2 python3-defusedxml python3-aiohttp python3-vobject python3-aiohttp-openmetrics && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/ && \
    groupadd -g 1000 xandikos && \
    useradd -d /code -c Xandikos -g xandikos -M -s /bin/bash -u 1000 xandikos
ADD . /code
WORKDIR /code
VOLUME /data
EXPOSE 8000
USER xandikos
ENTRYPOINT ["python3", "-m", "xandikos.web", "--port=8000", "--metrics-port=8001", "--listen-address=0.0.0.0", "-d", "/data"]
CMD ["--defaults"]
