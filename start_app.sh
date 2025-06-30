#!/bin/bash
cd "$(dirname "$0")"
export FLASK_APP=app.py
export FLASK_ENV=production
echo "Starting Flask application..."
python app.py