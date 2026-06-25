FROM python:3.11-slim

# Set working directory to /app
WORKDIR /app

# Copy dependency list and install them efficiently without caching bloat
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly copy only the necessary source code and auth tokens.
# By explicitly listing these, we inherently exclude .env and other sensitive local files.
COPY src/ ./src/
COPY credentials.json .
COPY token.json .

# Expose the specific port required by Google Cloud Run
EXPOSE 8080

# Run the server module exactly as requested
CMD ["python", "-m", "src.app"]
