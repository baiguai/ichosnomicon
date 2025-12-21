#!/bin/bash

# Build script for ichosnomicon.py
# Creates a standalone Linux binary using PyInstaller

set -e

echo "Building ichosnomicon.py for Linux..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Check if the Python file exists
if [ ! -f "ichosnomicon.py" ]; then
    echo "Error: ichosnomicon.py not found in current directory"
    exit 1
fi

# Build the executable
echo "Creating standalone executable..."
pyinstaller --onefile --name ichosnomicon \
    --add-data "ichos_help.html:." \
    --windowed \
    --clean \
    ichosnomicon.py

echo "Build complete!"
echo "Executable created: dist/ichosnomicon"
echo ""
echo "To run: ./dist/ichosnomicon"