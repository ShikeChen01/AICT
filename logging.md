# Imports the Cloud Logging client library
import google.cloud.logging

# Instantiates a client
client = google.cloud.logging.Client()

# Retrieves a Cloud Logging handler based on the environment
# you're running in and integrates the handler with the
# Python logging module. By default this captures all logs
# at INFO level and higher
client.setup_logging()

# Imports Python standard library logging
import logging

# The data to log
text = "Hello, world!"

# Emits the data using the standard logging module
logging.warning(text)

see link: https://docs.cloud.google.com/logging/docs/setup/python