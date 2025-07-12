Configuring Clients
===================

Xandikos supports ``auto-discovery`` of DAV collections (i.e. calendars or
addressbooks). Most clients today do as well, but there are some exceptions.

This section contains basic instructions on how to use various clients with Xandikos.
Please do send us patches if your favourite client is missing.

Evolution
---------

Evolution is a free and open source mail client, calendar, and address book
application for Linux.

**Configuration Steps:**

1. Open Evolution and go to File → New → Mail Account
2. Enter your name and email address
3. For "Server Type", select either:

   - "CardDAV" for address books
   - "CalDAV" for calendars

4. In the "Server URL" field, enter your Xandikos root URL (e.g., ``https://dav.example.com``)
5. Enter your username and password
6. Click "Find Addressbooks" or "Find Calendars"
7. Evolution will display all available collections - select the ones you want to sync
8. Click "Apply" to save the configuration

DAVx5
--------

DAVx5 (formerly DAVdroid) is an open-source CalDAV/CardDAV synchronization app
for Android.

**Configuration Steps:**

1. Install DAVx5 from F-Droid or Google Play Store
2. Open DAVx5 and tap the "+" button
3. Select "Login with URL and user name"
4. Enter your Xandikos base URL (e.g., ``https://dav.example.com``)
5. Enter your username and password
6. Tap "LOGIN"
7. DAVx5 will discover available calendars and address books
8. Select which collections to sync
9. Configure sync intervals as desired

vdirsyncer
----------

Vdirsyncer is a command-line tool for synchronizing calendars and address books
between servers and the local filesystem.

**Configuration Steps:**

1. Install vdirsyncer: ``pip install vdirsyncer``
2. Create a configuration file at ``~/.config/vdirsyncer/config``:

   .. code-block:: ini

      [general]
      status_path = "~/.vdirsyncer/status/"

      [pair my_contacts]
      a = "my_contacts_local"
      b = "my_contacts_remote"
      collections = ["from a", "from b"]

      [storage my_contacts_local]
      type = "filesystem"
      path = "~/.contacts/"
      fileext = ".vcf"

      [storage my_contacts_remote]
      type = "carddav"
      url = "https://dav.example.com"
      username = "your_username"
      password = "your_password"

      [pair my_calendars]
      a = "my_calendars_local"
      b = "my_calendars_remote"
      collections = ["from a", "from b"]

      [storage my_calendars_local]
      type = "filesystem"
      path = "~/.calendars/"
      fileext = ".ics"

      [storage my_calendars_remote]
      type = "caldav"
      url = "https://dav.example.com"
      username = "your_username"
      password = "your_password"

3. Discover available collections: ``vdirsyncer discover``
4. Synchronize: ``vdirsyncer sync``

Thunderbird
-----------

Thunderbird supports CalDAV natively and CardDAV through the CardBook add-on.

**CalDAV Configuration:**

1. Open Thunderbird and navigate to the Calendar tab
2. Right-click in the calendar list and select "New Calendar"
3. Choose "On the Network" and click "Next"
4. Select "CalDAV" and enter the calendar URL:
   ``https://dav.example.com/user/calendars/calendar``
5. Enter a display name for the calendar
6. Enter your credentials when prompted

**CardDAV Configuration (using CardBook):**

1. Install the CardBook add-on from Thunderbird's add-on manager
2. Open CardBook (Tools → CardBook)
3. Click the gear icon and select "New Address Book"
4. Choose "Remote" → "CardDAV"
5. Enter your Xandikos URL: ``https://dav.example.com``
6. Enter your username and password
7. Click "Validate" to discover available address books
8. Select the address books you want to sync

caldavzap/carddavmate
---------------------

CalDAVZAP and CardDAVMATE are web-based CalDAV and CardDAV clients.

**Configuration Steps:**

1. Deploy CalDAVZAP/CardDAVMATE on your web server
2. Edit the ``config.js`` file:

   .. code-block:: javascript

      var globalNetworkCheckSettings={
          href: 'https://dav.example.com/',
          userAuth: {
              userName: 'your_username',
              userPassword: 'your_password'
          }
      };

3. Access the web interface and your calendars/contacts will be loaded

Apple iOS
---------

iOS has built-in support for CalDAV and CardDAV.

**Configuration Steps:**

1. Go to Settings → Accounts & Passwords → Add Account
2. Select "Other"
3. For calendars: tap "Add CalDAV Account"
   For contacts: tap "Add CardDAV Account"
4. Enter:

   - Server: ``dav.example.com`` (without https://)
   - User Name: your username
   - Password: your password
   - Description: any name for the account

5. Tap "Next" - iOS will discover available calendars/address books
6. Toggle on the collections you want to sync
7. Tap "Save"

Tasks
-----

Tasks.org is an open-source to-do list app for Android with CalDAV support.

**Configuration Steps:**

1. Install Tasks from F-Droid or Google Play Store
2. Open Tasks and go to Settings → Synchronization
3. Tap "Add account" and select "CalDAV"
4. Enter:

   - Name: any display name
   - URL: ``https://dav.example.com``
   - User: your username
   - Password: your password

5. Tap the checkmark to save
6. Tasks will discover available task lists
7. Select which lists to synchronize

AgendaV
-------

AgendaV is a CalDAV web client with a clean interface.

**Configuration Steps:**

1. Deploy AgendaV on your web server
2. Edit ``web/config/settings.php``:

   .. code-block:: php

      $config['caldav_principal_url'] = 'https://dav.example.com/%u/';
      $config['caldav_calendar_url'] = 'https://dav.example.com/%u/calendars/%c/';
      $config['caldav_public_url'] = 'https://dav.example.com/public/%c/';

3. Configure authentication method in ``web/config/config.php``
4. Access AgendaV through your web browser

CardBook
--------

CardBook is a Thunderbird add-on for CardDAV synchronization (see Thunderbird section above).

pycardsyncer
------------

PyCardsyncer is a simple Python script for CardDAV synchronization.

**Configuration Steps:**

1. Install pycardsyncer: ``pip install pycarddav``
2. Create ``~/.config/pycard/pycard.conf``:

   .. code-block:: ini

      [Account example]
      user: your_username
      passwd: your_password
      resource: https://dav.example.com/user/contacts/addressbook/
      write_support: YesPleaseIDoHaveABackupOfMyData

3. Run initial sync: ``pycardsyncer --account example``

akonadi
-------

Akonadi is the KDE PIM storage service.

**Configuration Steps:**

1. Open System Settings → Personal Information → KDE Wallet (ensure it's enabled)
2. Open Kontact or KOrganizer
3. Go to Settings → Configure KOrganizer → Calendars
4. Click "Add" and select "DAV groupware resource"
5. Enter:

   - Server: ``https://dav.example.com``
   - Username and password

6. Click "Fetch" to discover available resources
7. Select calendars/address books to sync

CalDAV-Sync / CardDAV-Sync
--------------------------

These are Android apps for calendar and contact synchronization.

**Configuration Steps:**

1. Install CalDAV-Sync or CardDAV-Sync from Google Play Store
2. Open the app and tap "Add Account"
3. Enter:

   - Account name: any display name
   - Server URL: ``https://dav.example.com``
   - Username and password

4. Tap "Next" to discover collections
5. Select which calendars/address books to sync
6. Configure sync interval and other options
7. Tap "Finish"

Calendarsync
------------

CalendarSync is another Android CalDAV sync adapter.

**Configuration Steps:**

1. Install CalendarSync from Google Play Store
2. Open Android Settings → Accounts → Add Account
3. Select "CalDAV"
4. Enter your server details:

   - Server: ``https://dav.example.com``
   - Username and password

5. The app will discover and sync available calendars
