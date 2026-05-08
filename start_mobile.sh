#!/bin/bash
echo "Fetching latest updates from GitHub..."
git pull origin main
echo "Starting Mobile Client..."
python mobile_client.py
