#!/bin/bash

echo "Updating system..."
apt update && apt upgrade -y

echo "Installing dependencies..."
apt install python3 python3-pip git libgl1-mesa-glx libglib2.0-0 -y

echo "Installing Python packages..."
pip3 install -r requirements.txt --break-system-packages

echo "Setup complete! You can now run the scanner with: python3 Code_scan.py"
