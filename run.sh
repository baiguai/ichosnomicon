#!/bin/bash

# This script builds and runs the ichosnomicon application.

# Exit immediately if a command exits with a non-zero status.
set -e

# Run the build script to ensure the application is up-to-date.
echo "Building the application..."
bash build.sh

# Run the compiled application from the dist directory.
echo "Running the application..."
./dist/ichosnomicon
