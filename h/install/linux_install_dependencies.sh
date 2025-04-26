#!/bin/bash

# Update package lists
echo "Updating package lists..."
sudo apt update

# Install Python3 and pip if not already installed
echo "Installing Python3 and pip..."
sudo apt install -y python3 python3-pip python3-venv

# Install required system dependencies for GPG
echo "Installing GPG dependencies..."
sudo apt install -y gnupg gnupg2 libgpgme-dev swig

# Create a virtual environment (recommended)
echo "Creating a Python virtual environment..."
python3 -m venv gpg_telegram_env
source gpg_telegram_env/bin/activate

# Install required Python packages
echo "Installing required Python packages..."
pip install python-telegram-bot python-gnupg nest-asyncio

# Make the Python scripts executable
echo "Making scripts executable..."
chmod +x sendMessage.py telegram_getid.py

echo "========================================================"
echo "Installation complete!"
echo ""
echo "To run the scripts:"
echo "1. Activate the virtual environment:"
echo "   source gpg_telegram_env/bin/activate"
echo ""
echo "2. Run the main script:"
echo "   ./sendMessage.py"
echo ""
echo "3. Or run the get ID script (after updating the BOT_TOKEN):"
echo "   ./telegram_getid.py"
echo "========================================================"
