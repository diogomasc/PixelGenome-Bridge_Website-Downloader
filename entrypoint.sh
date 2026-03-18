#!/bin/bash

# Default port for Gunicorn
PORT=${PORT:-5001}

echo "Starting PixelGenome Bridge on port $PORT..."

# Start the application using Gunicorn
# Adjust the app:app based on your Flask app instance name in app.py
exec gunicorn --bind 0.0.0.0:$PORT --timeout 120 app:app
