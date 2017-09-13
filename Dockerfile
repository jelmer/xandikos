FROM debian:sid
LABEL maintainer="jelmer@jelmer.uk"
ARG port=80
RUN apt-get update && \
    apt-get -y install uwsgi uwsgi-plugin-python3 python3-icalendar python3-dulwich python3-jinja2 python3-defusedxml && \
    apt-get clean
ADD . /code
WORKDIR /code
VOLUME /data
EXPOSE $port
cMD uwsgi --http-socket=:$port --umask=022 --master --cheaper=2 --processes=4 --plugin=router_basicauth,python3 --route="^/ basicauth:myrealm,user1:password1" --module=xandikos.wsgi:app --env=XANDIKOSPATH=/data --env=CURRENT_USER_PRINCIPAL=/dav/user1 --env=AUTOCREATE=defaults
