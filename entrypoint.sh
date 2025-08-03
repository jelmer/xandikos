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
if [ -n "$PORT" ]; then
    ARGS+=("--port=$PORT")
else
    ARGS+=("--port=$DEFAULT_PORT")
fi

if [ -n "$METRICS_PORT" ]; then
    ARGS+=("--metrics-port=$METRICS_PORT")
else
    ARGS+=("--metrics-port=$DEFAULT_METRICS_PORT")
fi

if [ -n "$LISTEN_ADDRESS" ]; then
    ARGS+=("--listen-address=$LISTEN_ADDRESS")
else
    ARGS+=("--listen-address=$DEFAULT_LISTEN_ADDRESS")
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

if [ "$NO_DETECT_SYSTEMD" = "true" ] || [ "$NO_DETECT_SYSTEMD" = "1" ]; then
    ARGS+=("--no-detect-systemd")
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
    python3 -m xandikos.web "$@" &
else
    # Use environment variable configuration  
    python3 -m xandikos.web "${ARGS[@]}" &
fi

XANDIKOS_PID=$!
wait $XANDIKOS_PID