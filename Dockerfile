FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code
COPY . .

# Expose the port the app will run on
EXPOSE 5000

# Set the environment variable for GCP credentials
ENV GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcp-key.json

# Start the application
CMD ["python", "app.py"]
