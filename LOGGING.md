# Structured Logging Documentation

This application now uses structured JSON logging for better observability in Railway logs.

## Overview

All logging is now output in structured JSON format, making it easier to:
- Filter and search logs
- Parse log data programmatically
- Monitor application behavior
- Debug issues in production

## Log Format

Logs are structured JSON objects with the following fields:
- `asctime`: Timestamp of the log entry
- `name`: Logger name (typically the module name)
- `levelname`: Log level (INFO, WARNING, ERROR, DEBUG)
- `message`: The main log message
- Custom fields via `extra` parameter for context-specific data

## Example Log Output

```json
{
  "asctime": "2026-01-14 15:40:00",
  "name": "supabase_scraper",
  "levelname": "INFO",
  "message": "Processing URL 123: https://example.com/article",
  "url_id": 123,
  "url": "https://example.com/article",
  "attempt": 1
}
```

## Log Levels

- **DEBUG**: Detailed debugging information (use `LOG_LEVEL=DEBUG` to see)
- **INFO**: General informational messages about application flow
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages for failures and exceptions

## Configuration

Set the `LOG_LEVEL` environment variable to control log verbosity:

```bash
# In Railway environment variables
LOG_LEVEL=INFO

# Available levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

Default: `INFO`

## What's Being Logged

### supabase_scraper.py
- Application startup and initialization
- Supabase and OpenAI client status
- URL queue operations (fetching, processing, updating status)
- Scraping progress per URL
- Embedding generation status
- Document insertion/deletion operations
- Batch processing statistics
- Error conditions and retry attempts
- Final summary with total statistics

### versatile_scraper.py
- Page fetching operations
- HTML parsing status
- Content extraction (metadata, headings, paragraphs, lists, etc.)
- Data export operations
- Scraping completion summary

### embedding_generator.py
- API key validation
- Data loading status
- Text chunking operations
- Embedding generation (batch processing)
- Output structure creation
- File save operations
- Final processing summary

## Viewing Logs in Railway

1. Go to your Railway project
2. Select your service
3. Click the "Logs" tab
4. Use the search/filter functionality to find specific log entries

### Example Searches

**Find errors:**
- Search for: `"levelname":"ERROR"`

**Find specific URL processing:**
- Search for: `"https://example.com/article"`

**Find batch statistics:**
- Search for: `"BATCH #"`

**Find final summaries:**
- Search for: `"FINAL SUMMARY"`

## Testing Logging

Run the test script to verify logging is working:

```bash
python test_logging.py
```

This will output several structured JSON log messages showing different log levels and data.

## Benefits of Structured Logging

1. **Better Searchability**: Filter logs by any field value
2. **Programmatic Analysis**: Parse logs with tools like jq or ELK stack
3. **Context-Rich**: Each log entry includes relevant metadata
4. **Consistent Format**: All logs follow the same JSON structure
5. **Production-Ready**: Works well with log aggregation services

## Example: Filtering Logs

To see only errors in Railway logs:
```bash
# Use Railway's log filter
levelname: ERROR
```

To see processing for a specific URL:
```bash
# Search in Railway logs
url: "https://central.xero.com/..."
```

## Log Levels in Production

**Development/Debugging:**
```bash
LOG_LEVEL=DEBUG
```

**Normal Production:**
```bash
LOG_LEVEL=INFO
```

**Production - Minimal Logging:**
```bash
LOG_LEVEL=WARNING
