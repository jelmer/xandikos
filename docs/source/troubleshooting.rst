Troubleshooting
===============

This guide helps diagnose and resolve common issues with Xandikos.

Support channels
----------------

For help, please try the `Xandikos Discussions Forum
<https://github.com/jelmer/xandikos/discussions/categories/q-a>`_,
IRC (``#xandikos`` on irc.oftc.net), or Matrix (`#xandikos:matrix.org
<https://matrix.to/#/#xandikos:matrix.org>`_).

Common Issues
-------------

Collections Not Found (404 Errors)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Clients report 404 errors when trying to access calendars or addressbooks.

**Solutions**:

1. Ensure collections exist:

   .. code-block:: bash

      ls -la /path/to/xandikos/data/calendars/
      ls -la /path/to/xandikos/data/contacts/

2. Use ``--defaults`` flag to create default collections:

   .. code-block:: bash

      xandikos --defaults -d /path/to/data

3. Check route prefix configuration if behind a reverse proxy:

   .. code-block:: bash

      xandikos --route-prefix /dav -d /path/to/data

Authentication Failures
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Clients repeatedly prompt for credentials or report authentication errors.

**Solutions**:

1. Remember that Xandikos doesn't provide authentication - check your reverse proxy configuration
2. Verify credentials in your reverse proxy (htpasswd file, LDAP, etc.)
3. Check that authentication headers are being passed correctly:

   .. code-block:: nginx

      proxy_set_header Authorization $http_authorization;
      proxy_pass_header Authorization;

4. For Basic Auth issues, ensure the client supports it or try Digest Auth

Permission Denied Errors
~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: "Permission denied" errors in logs or when creating/modifying items.

**Solutions**:

1. Check file ownership:

   .. code-block:: bash

      chown -R xandikos:xandikos /path/to/data

2. Verify directory permissions:

   .. code-block:: bash

      chmod -R 750 /path/to/data

3. Ensure the Xandikos process user matches file ownership

Sync Not Working
~~~~~~~~~~~~~~~~

**Symptoms**: Changes not syncing between clients or sync errors.

**Solutions**:

1. Enable debug logging to see sync requests:

   .. code-block:: bash

      xandikos --debug --dump-dav-xml -d /path/to/data

2. Check for client-specific issues:
   
   - iOS: Ensure account is properly configured with full URLs
   - Android: Try force-refreshing the account
   - Evolution: Check collection discovery settings

3. Verify WebDAV methods are not blocked by reverse proxy
4. Check that all required DAV headers are passed through

"Method Not Allowed" Errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: 405 Method Not Allowed responses from server.

**Solutions**:

1. Ensure reverse proxy allows all DAV methods:

   .. code-block:: nginx

      location / {
          proxy_pass http://localhost:8080;
          proxy_method $request_method;
          
          # Allow all DAV methods
          if ($request_method !~ ^(GET|HEAD|POST|PUT|DELETE|OPTIONS|PROPFIND|PROPPATCH|MKCOL|COPY|MOVE|LOCK|UNLOCK|REPORT)$ ) {
              return 405;
          }
      }

2. Check that your reverse proxy isn't filtering methods

Large File Upload Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Failures when syncing large calendars or many contacts.

**Solutions**:

Xandikos itself does not limit file sizes, but reverse proxies may.

1. Configure reverse proxy limits:

   .. code-block:: nginx

      client_max_body_size 50M;
      proxy_request_buffering off;


Git Repository Corruption
~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Errors mentioning Git or repository corruption.

**Solutions**:

1. Run Git fsck on affected collection:

   .. code-block:: bash

      cd /path/to/data/calendars/calendar
      git fsck

2. Try to recover repository:

   .. code-block:: bash

      git gc --aggressive
      git prune

3. As last resort, clone to new repository:

   .. code-block:: bash

      git clone file:///path/to/data/calendars/calendar /tmp/calendar-backup
      mv /path/to/data/calendars/calendar /path/to/data/calendars/calendar.broken
      mv /tmp/calendar-backup /path/to/data/calendars/calendar

Client-Specific Issues
----------------------

Evolution
~~~~~~~~~

**Issue**: Evolution shows empty calendar list

**Solution**: Use the "Find Calendars" button instead of manual configuration

DAVx5
~~~~~

**Issue**: DAVx5 reports "Couldn't find CalDAV or CardDAV service"

**Solution**: Ensure well-known redirects are configured:

.. code-block:: nginx

   location /.well-known/caldav {
       return 301 $scheme://$host/;
   }
   
   location /.well-known/carddav {
       return 301 $scheme://$host/;
   }

iOS
~~~

**Issue**: iOS account verification fails

**Solution**: 

1. Use the server hostname without https://
2. Ensure SSL certificates are valid and trusted
3. Try advanced settings with full URLs

Thunderbird
~~~~~~~~~~~

**Issue**: Thunderbird can't find calendars

**Solution**: Use the full calendar URL instead of autodiscovery:
``https://dav.example.com/calendars/calendar``

Debugging Tools
---------------

Command-Line Debugging
~~~~~~~~~~~~~~~~~~~~~~

Use these flags for detailed debugging:

.. code-block:: bash

   xandikos \
     --debug \
     --dump-dav-xml \
     --log-level DEBUG \
     -d /path/to/data 2>&1 | tee xandikos-debug.log

Testing with curl
~~~~~~~~~~~~~~~~~

Test basic connectivity:

.. code-block:: bash

   # Test OPTIONS
   curl -X OPTIONS https://dav.example.com/ -u username:password

   # Test PROPFIND
   curl -X PROPFIND https://dav.example.com/ \
     -u username:password \
     -H "Depth: 0" \
     -H "Content-Type: application/xml" \
     -d '<?xml version="1.0" encoding="utf-8"?>
         <propfind xmlns="DAV:">
           <prop>
             <displayname/>
             <resourcetype/>
           </prop>
         </propfind>'

Monitoring Logs
~~~~~~~~~~~~~~~

Watch logs in real-time:

.. code-block:: bash

   # Xandikos logs
   journalctl -u xandikos -f

   # Reverse proxy logs
   tail -f /var/log/nginx/access.log /var/log/nginx/error.log

Performance Issues
------------------

Slow Response Times
~~~~~~~~~~~~~~~~~~~

1. Enable compression:

   .. code-block:: bash

      xandikos --compress -d /path/to/data

2. Check Git repository size:

   .. code-block:: bash

      du -sh /path/to/data/*/.git

3. Run Git garbage collection:

   .. code-block:: bash

      find /path/to/data -name ".git" -type d -exec git -C {} gc \;

Getting Help
------------

When requesting help, provide:

1. Xandikos version: ``xandikos --version``
2. Client name and version
3. Relevant error messages from:

   - Xandikos output (with ``--debug``)
   - Reverse proxy logs
   - Client logs

4. Output from ``--dump-dav-xml`` for protocol issues
5. Minimal steps to reproduce the issue
