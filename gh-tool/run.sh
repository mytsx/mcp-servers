#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$DIR/venv/bin/activate"

# Run the server
exec python "$DIR/server.py"