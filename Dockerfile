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
ENV current_user_principal="/dav/user1"

# TODO(jelmer): Add support for authentication
# --plugin=router_basicauth,python3  --route="^/ basicauth:myrealm,user1:password1"
CMD uwsgi --http-socket=:8000 --umask=022 --master --cheaper=2 --processes=4 --plugin=python3 --module=xandikos.wsgi:app --env=XANDIKOSPATH=/data --env=CURRENT_USER_PRINCIPAL=$current_user_principal --env=AUTOCREATE=$autocreate
