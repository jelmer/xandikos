# Docker file for Xandikos.
# This docker image starts a Xandikos server on port 8000. It supports two
# environment variables:
#
# - autocreate: "principal" / "defaults"
#     If set to "yes", this will create the user principal, but not any
#     calendars or address books.
#     If set to "defaults", it will create a default calendar
#     (under $current_user_principal/calendars/calendar) and a default
#     addressbook (under $current_user_principal/contacts/addressbook)
#
# - current_user_principal: /path/to/user/principal
#    This specifies the path to the current users' principal, and effectively
#    the path under which Xandikos will be available.
#    It is recommended that you set it to "/YOURUSERNAME"
#
# E.g. If autocreate is set to "defaults" and current_user_principal is set to
# "/dav/joe", Xandikos will provide two collections (one calendar, one
# addressbook) at respecively:
#
#   http://localhost:8000/dav/joe/calendars/calendar
#   http://localhost:8000/dav/joe/contacts/addressbook
#
# Note that this dockerfile starts Xandikos without any authentication;
# for authenticated access we recommend you run it behind a reverse proxy.

FROM debian:sid
LABEL maintainer="jelmer@jelmer.uk"
RUN apt-get update && \
    apt-get -y install uwsgi uwsgi-plugin-python3 python3-icalendar python3-dulwich python3-jinja2 python3-defusedxml && \
    apt-get clean
ADD . /code
WORKDIR /code
VOLUME /data
EXPOSE 8000
ENV autocreate="defaults"
ENV current_user_principal="/user1"

# TODO(jelmer): Add support for authentication
# --plugin=router_basicauth,python3  --route="^/ basicauth:myrealm,user1:password1"
CMD uwsgi --http-socket=:8000 \
          --umask=022 \
          --master \
          --cheaper=2 \
          --processes=4 \
          --plugin=python3 \
          --module=xandikos.wsgi:app \
          --env=XANDIKOSPATH=/data \
          --env=CURRENT_USER_PRINCIPAL=$current_user_principal \
          --env=AUTOCREATE=$autocreate
