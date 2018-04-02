API Stability
=============

There are currently no guarantees about Xandikos Python APIs staying the same
across different versions, except the following APIs:

xandikos.web.XandikosBackend(path)
xandikos.web.XandikosBackend.create_principal(principal, create_defaults=False)
xandikos.web.XandikosApp(backend, current_user_principal)
xandikos.web.WellknownRedirector(app, path)

If you care about stability of any other APIs, please file a bug against Xandikos.
