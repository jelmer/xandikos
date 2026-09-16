#!/bin/bash
set -e

# Default values
DEFAULT_PORT="8000"
DEFAULT_METRICS_PORT="8001"
DEFAULT_LISTEN_ADDRESS="0.0.0.0"
DEFAULT_DATA_DIR="/data"
DEFAULT_CURRENT_USER_PRINCIPAL="/user/"
DEFAULT_ROUTE_PREFIX="/"

# Build command line arguments
ARGS=()

# Handle environment variables and build arguments
# Determine the effective listen address up-front so we know whether we
# need a --port (TCP) or not (unix socket).
EFFECTIVE_LISTEN_ADDRESS="${LISTEN_ADDRESS:-$DEFAULT_LISTEN_ADDRESS}"

case "$EFFECTIVE_LISTEN_ADDRESS" in
    /*|unix:*)
        # Unix-socket listener: --port is meaningless.
        ;;
    *)
        if [ -n "$PORT" ]; then
            ARGS+=("--port=$PORT")
        else
            ARGS+=("--port=$DEFAULT_PORT")
        fi
        ;;
esac

if [ -n "$METRICS_PORT" ]; then
    ARGS+=("--metrics-port=$METRICS_PORT")
else
    ARGS+=("--metrics-port=$DEFAULT_METRICS_PORT")
fi

ARGS+=("--listen-address=$EFFECTIVE_LISTEN_ADDRESS")

# Optional permissions for a Unix-socket web listener.
if [ -n "$SOCKET_MODE" ]; then
    ARGS+=("--socket-mode=$SOCKET_MODE")
fi
if [ -n "$SOCKET_GROUP" ]; then
    ARGS+=("--socket-group=$SOCKET_GROUP")
fi

if [ -n "$DATA_DIR" ]; then
    ARGS+=("-d" "$DATA_DIR")
else
    ARGS+=("-d" "$DEFAULT_DATA_DIR")
fi

if [ -n "$CURRENT_USER_PRINCIPAL" ]; then
    ARGS+=("--current-user-principal=$CURRENT_USER_PRINCIPAL")
else
    ARGS+=("--current-user-principal=$DEFAULT_CURRENT_USER_PRINCIPAL")
fi

if [ -n "$ROUTE_PREFIX" ]; then
    ARGS+=("--route-prefix=$ROUTE_PREFIX")
else
    ARGS+=("--route-prefix=$DEFAULT_ROUTE_PREFIX")
fi

# Boolean flags
if [ "$AUTOCREATE" = "true" ] || [ "$AUTOCREATE" = "1" ]; then
    ARGS+=("--autocreate")
fi

if [ "$DEFAULTS" = "true" ] || [ "$DEFAULTS" = "1" ]; then
    ARGS+=("--defaults")
fi

if [ "$DUMP_DAV_XML" = "true" ] || [ "$DUMP_DAV_XML" = "1" ]; then
    ARGS+=("--dump-dav-xml")
fi

if [ "$AVAHI" = "true" ] || [ "$AVAHI" = "1" ]; then
    ARGS+=("--avahi")
fi

if [ "$NO_STRICT" = "true" ] || [ "$NO_STRICT" = "1" ]; then
    ARGS+=("--no-strict")
fi

if [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    ARGS+=("--debug")
fi

if [ "$PARANOID" = "true" ] || [ "$PARANOID" = "1" ]; then
    ARGS+=("--paranoid")
fi

if [ -n "$INDEX_THRESHOLD" ]; then
    ARGS+=("--index-threshold=$INDEX_THRESHOLD")
fi

if [ "$EAGER" = "true" ] || [ "$EAGER" = "1" ]; then
    ARGS+=("--eager")
fi

if [ "$NO_DETECT_SYSTEMD" = "true" ] || [ "$NO_DETECT_SYSTEMD" = "1" ]; then
    ARGS+=("--no-detect-systemd")
fi

if [ "$AUTOCERT" = "true" ] || [ "$AUTOCERT" = "1" ]; then
    ARGS+=("--autocert")
fi

if [ "$WEBDAV_PUSH" != "false" ] && [ "$WEBDAV_PUSH" != "0" ]; then
    ARGS+=("--webdav-push")
fi

if [ -n "$STATE_DIR" ]; then
    ARGS+=("--state-dir=$STATE_DIR")
else
    ARGS+=("--state-dir=/data/state")
fi

if [ -n "$HTPASSWD" ]; then
    ARGS+=("--htpasswd=$HTPASSWD")
fi

# iMIP LMTP listener. Pass "auto" (or "1"/"true") to default to a
# UNIX socket inside the /sockets/ volume; any other value is taken
# verbatim (e.g. "unix:/sockets/custom.sock" or "host:port").
if [ -n "$IMIP_LISTEN" ]; then
    case "$IMIP_LISTEN" in
        auto|1|true)
            ARGS+=("--imip-listen=unix:/sockets/imip.sock")
            ;;
        *)
            ARGS+=("--imip-listen=$IMIP_LISTEN")
            ;;
    esac
fi
if [ -n "$IMIP_LISTEN_MODE" ]; then
    ARGS+=("--imip-listen-mode=$IMIP_LISTEN_MODE")
fi
if [ -n "$IMIP_LISTEN_GROUP" ]; then
    ARGS+=("--imip-listen-group=$IMIP_LISTEN_GROUP")
fi

# In-process Postfix/Sendmail milter. Same "auto" convention as
# IMIP_LISTEN above.
if [ -n "$MILTER_LISTEN" ]; then
    case "$MILTER_LISTEN" in
        auto|1|true)
            ARGS+=("--milter-listen=unix:/sockets/milter.sock")
            ;;
        *)
            ARGS+=("--milter-listen=$MILTER_LISTEN")
            ;;
    esac
fi
if [ -n "$MILTER_LISTEN_MODE" ]; then
    ARGS+=("--milter-listen-mode=$MILTER_LISTEN_MODE")
fi
if [ -n "$MILTER_LISTEN_GROUP" ]; then
    ARGS+=("--milter-listen-group=$MILTER_LISTEN_GROUP")
fi

# Handle graceful shutdown
shutdown_handler() {
    echo "Received SIGTERM, shutting down gracefully..."
    if [ -n "$XANDIKOS_PID" ]; then
        kill -TERM "$XANDIKOS_PID" 2>/dev/null || true
        wait "$XANDIKOS_PID" 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap shutdown_handler SIGTERM SIGINT

# If user provided arguments, pass them directly to xandikos
if [ $# -gt 0 ]; then
    python3 -m xandikos "$@" &
else
    # Use environment variable configuration
    python3 -m xandikos "${ARGS[@]}" &
fi

XANDIKOS_PID=$!
wait $XANDIKOS_PID
