$ cp examples/uwsgi-heroku.ini uwsgi.ini
(Update according to your requirements)
$ echo web: uwsgi uwsgi.ini > Procfile
$ echo uwsgi > requirements.txt
$ heroku create
$ git push heroku master
$ heroku open
