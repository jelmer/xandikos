# Docker file for Xandikos.
#
# Note that this dockerfile starts Xandikos without any authentication;
# for authenticated access we recommend you run it behind a reverse proxy.
#
# Environment variables:
#   PORT - Port to listen on (default: 8000)
#   METRICS_PORT - Port for metrics endpoint (default: 8001)
#   LISTEN_ADDRESS - Address to bind to (default: 0.0.0.0)
#   DATA_DIR - Data directory path (default: /data)
#   CURRENT_USER_PRINCIPAL - User principal path (default: /user/)
#   ROUTE_PREFIX - URL route prefix (default: /)
#   AUTOCREATE - Auto-create directories (true/false)
#   DEFAULTS - Create default calendar/addressbook (true/false)
#   DEBUG - Enable debug logging (true/false)
#   DUMP_DAV_XML - Print DAV XML requests/responses (true/false)
#   NO_STRICT - Enable client compatibility workarounds (true/false)
#
# Command line arguments passed to the container override environment variables.

FROM debian:sid-slim
LABEL maintainer="jelmer@jelmer.uk"
RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-icalendar python3-pip python3-jinja2 python3-defusedxml python3-aiohttp python3-vobject python3-aiohttp-openmetrics python3-qrcode curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/ && \
    groupadd -g 1000 xandikos && \
    useradd -d /code -c Xandikos -g xandikos -M -s /bin/bash -u 1000 xandikos && \
    # Install dulwich from pip instead of Debian package to get a newer version
    # that fixes _GitFile import issues in index.py (0.24.6 vs 0.24.2)
    pip3 install --break-system-packages dulwich
ADD . /code
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown xandikos:xandikos /entrypoint.sh && \
    mkdir -p /data && chown xandikos:xandikos /data
WORKDIR /code
VOLUME /data
EXPOSE 8000 8001
USER xandikos
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD []
