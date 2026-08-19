import os
from phantomfetch import main as start_bot

if __name__ == '__main__':
  # Set the TELEGRAM_TOKEN environment variable if not set
  if not os.getenv("TELEGRAM_TOKEN"):
    print("Please set the TELEGRAM_TOKEN environment variable.")
  else:
    start_bot()  # Call the main function from phantomfetch.py
