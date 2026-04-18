# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# ffmpeg is crucial for the bot's media processing
# git is often needed for some python packages
# gcc and python3-dev are required to build TgCrypto on ARM architectures
# p7zip-full is required for unpacking rar/zip/7z archives
# rclone is required for the Mirror-Leech rclone uploader (covers 70+
# cloud backends). Safe to keep installed even when Mirror-Leech is off.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    gcc \
    python3-dev \
    p7zip-full \
    rclone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Run the application
CMD ["python3", "main.py"]
