FROM python:3.9

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot script
COPY . .

# Run the bot using environment variables passed at runtime
CMD ["python", "bot.py"]
