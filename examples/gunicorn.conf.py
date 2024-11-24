# Gunicorn config file
#
# Usage
# ----------------------------------------------------------
#
# Install: 1) copy this config to src directory for xandikos
#          2) run 'pip install gunicorn'
#          3) mkdir logs && mkdir data
#
# Execute: 'gunicorn'
#
wsgi_app = "xandikos.wsgi:app"

#  Server Mechanics
# ========================================
# daemon mode
daemon = False

# environment variables
raw_env = [
    "XANDIKOSPATH=./data",
    "CURRENT_USER_PRINCIPAL=/user/",
    "AUTOCREATE=defaults",
]

# Server Socket
# ========================================
bind = "0.0.0.0:8000"

# Worker Processes
# ========================================
workers = 2

#  Logging
# ========================================
# access log
accesslog = "./logs/access.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# gunicorn log
errorlog = "-"
loglevel = "info"
