Running Xandikos on Heroku
==========================

Heroku is an easy way to get a public instance of Xandikos running. A free
heroku instance comes with 100Mb of local storage, which is enough for
thousands of calendar items or contacts.

Deployment
----------

All of these steps assume you already have a Heroku account and have installed
the heroku command-line client.

To run a Heroku instance with Xandikos:

1. Create a copy of Xandikos::

    $ git clone git://jelmer.uk/xandikos xandikos
    $ cd xandikos

2. Make a copy of the example uwsgi configuration::

    $ cp examples/uwsgi-heroku.ini uwsgi.ini

3. Edit *uwsgi.ini* as necessary, such as changing the credentials (the
   defaults are *user1*/*password1*).

4. Make heroku install and use uwsgi::

    $ echo uwsgi > requirements.txt
    $ echo web: uwsgi uwsgi.ini > Procfile

5. Create the Heroku instance::

    $ heroku create

(this might ask you for your heroku credentials)

6. Deploy the app::

    $ git push heroku master

7. Open the app with your browser::

    $ heroku open

(The URL opened is also the URL that you can provide to any CalDAV/CardDAV
application that supports service discovery)
