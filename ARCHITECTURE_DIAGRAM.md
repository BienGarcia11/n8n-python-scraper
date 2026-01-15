# RAG System with Semantic Cache - Architecture Diagram

## Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              n8n Webhook / Manual Trigger                     │
│                              (Monthly / On Demand)                              │
└────────────────────────────┬────────────────────────────────────────────────────────┘
                         │
                         │ POST /scrape OR /daemon/start
                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          Railway Deployment                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐       │
│  │                    FastAPI Application                      │       │
│  │                                                               │       │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │       │
│  │  │    Queue     │  │    Daemon    │  │  Endpoints   │ │       │
│  │  │   Manager    │  │    Engine    │  │              │ │       │
│  │  │              │  │              │  │  - /scrape    │ │       │
│  │  │  - Process   │  │  - Auto-run  │  │  /scrape-    │ │       │
│  │  │    Batches   │  │    Forever   │  │    batch     │ │       │
│  │  │  - Recovery   │  │  - Poll every│  │  /daemon/    │ │       │
│  │  │    Handler   │  │    N sec    │  │    start     │ │       │
│  │  │              │  │              │  │  /daemon/    │ │       │
│  │  │  - Retry     │  │  - Auto-     │  │    stop      │ │       │
│  │  │    Logic    │  │    Recover   │  │  /daemon/    │ │       │
│  │  │              │  │              │  │    status    │ │       │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │       │
│  │          │                 │                   │              │       │
│  └──────────┼─────────────────┼───────────────────┼──────────────┘       │
│             │                 │                   │                      │
└─────────────┼─────────────────┼───────────────────┼──────────────────────┘
              │                 │                   │
              ▼                 ▼                   ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │  Supabase   │   │   OpenAI    │   │   Playwright │
    │  Database   │   │   API       │   │   Browser   │
    │             │   │             │   │             │
    │ - url_queue  │   │ - text-     │   │ - Chromium  │
    │   table     │   │   embedding-│   │   Driver   │
    │             │   │   3-small   │   │             │
    │ - documents │   │   (1536     │   │ - Dynamic   │
    │   table     │   │   dims)     │   │   Content  │
    │             │   │             │   │             │
    │ - pgvector  │   │ - Batch     │   │ - Screenshots│
    │   index     │   │   Processing│   │ - Wait for  │
    └─────────────┘   └─────────────┘   │   JS Load   │
                                      └─────────────┘
```

## Detailed Workflow Diagrams

### 1. Initial Setup & Startup

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Application Startup                              │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Load Environment  │
                    │ Variables (.env)   │
                    │                   │
                    │ - SUPABASE_URL     │
                    │ - SUPABASE_KEY     │
                    │ - OPENAI_API_KEY   │
                    │ - AUTO_START_DAEMON│
                    │ - DAEMON_POLL_INTERVAL│
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ Initialize Clients │
                    │                   │
                    │ - Supabase Client  │
                    │ - OpenAI Client    │
                    │ - Playwright       │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ Reset Stuck URLs  │
                    │                   │
                    │ Find URLs with     │
                    │ status='processing'│
                    │ Reset to 'pending' │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ Check AUTO_START   │
                    │ _DAEMON env var   │
                    └───────────┬────────┘
                                │
                     ┌──────────┴──────────┐
                     ▼                     ▼
              ┌──────────────┐    ┌──────────────┐
              │Auto-start? YES│    │Auto-start? NO│
              │ Start Daemon │    │ Wait for API │
              └──────────────┘    └──────────────┘
```

### 2. Daemon Mode Continuous Processing

```
┌─────────────────────────────────────────────────────────────────────┐
│ DAEMON PROCESS LOOP (Runs Indefinitely)                  │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Sleep for N       │
                    │  seconds            │
                    │  (default: 10s)    │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  Check Queue for    │
                    │  Pending URLs       │
                    └───────────┬────────┘
                                │
                     ┌──────────┴──────────┐
                     ▼                     ▼
              ┌──────────────┐    ┌──────────────┐
              │ URLs Found   │    │ No URLs     │
              │ (Get Batch) │    │ Available    │
              └──────┬───────┘    └──────┬───────┘
                     │                     │
                     ▼                     │
          ┌─────────────────────┐          │
          │ Update Status:       │          │
          │ 'processing'         │          │
          └──────────┬──────────┘          │
                     │                     │
                     ▼                     │
          ┌─────────────────────┐          │
          │ Process URLs in     │          │
          │ Parallel (Batch of  │          │
          │ N URLs)            │          │
          └──────────┬──────────┘          │
                     │                     │
                     ▼                     │
          ┌──────────────────────────────────┐│
          │ For Each URL:                 ││
          │                              ││
          │  1. Scrape with Playwright ││
          │  2. Chunk Text            ││
          │  3. Generate Embeddings    ││
          │  4. Delete Old Chunks     ││
          │  5. Insert New Chunks     ││
          │  6. Update Status         ││
          └──────────┬───────────────────┘│
                     │                     │
                     ▼                     │
          ┌─────────────────────┐          │
          │ Log Results & Stats  │          │
          └──────────┬──────────┘          │
                     │                     │
                     └─────────────────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  Loop Continues     │
                    │  (Back to Sleep)    │
                    └───────────┬────────┘
                                │
                                │ (repeat forever)
                                └──────┐
                                       │
                                       ▼
                               (until daemon_running=False)
```

### 3. Automatic Crash Recovery

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCENARIO: Railway Restart / Application Crash               │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Process Dies       │
                    │  (URLs stuck in    │
                    │   'processing')     │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  App Restarts      │
                    │  (Railway Auto-    │
                    │   Restart)          │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  Startup Event     │
                    │  Handler Runs      │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  reset_stuck_urls()│
                    │  Function Executes  │
                    │                   │
                    │  SELECT * FROM      │
                    │  url_queue         │
                    │  WHERE status =     │
                    │  'processing'       │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  UPDATE url_queue  │
                    │  SET status =       │
                    │  'pending'         │
                    │  WHERE status =     │
                    │  'processing'       │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  URLs Ready for     │
                    │  Reprocessing      │
                    │  Daemon Picks       │
                    │  Them Up          │
                    └──────────────────────┘
```

### 4. URL Processing Flow (Single URL)

```
┌─────────────────────────────────────────────────────────────────────┐
│ PROCESS SINGLE URL                                         │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ 1. Fetch URL       │
                    │    from Queue      │
                    │    status='pending'│
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 2. Update Status   │
                    │    to 'processing' │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 3. Scrape with     │
                    │    Playwright      │
                    │                   │
                    │    - Load URL       │
                    │    - Wait for JS    │
                    │    - Extract:       │
                    │      * Content      │
                    │      * Title        │
                    │      * Metadata     │
                    │      * Links        │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 4. Chunk Text      │
                    │    (800 chars)     │
                    │    (100 overlap)    │
                    │                   │
                    │    Result:          │
                    │    [Chunk 1]       │
                    │    [Chunk 2]       │
                    │    [Chunk 3] ...   │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 5. Generate        │
                    │    Embeddings      │
                    │    (OpenAI API)    │
                    │                   │
                    │    Batch Size: 20   │
                    │    Model: text-     │
                    │      embedding-3-    │
                    │      small           │
                    │    Dim: 1536        │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 6. Delete Old      │
                    │    Chunks          │
                    │                   │
                    │    DELETE FROM       │
                    │    documents        │
                    │    WHERE url = ?    │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 7. Insert New      │
                    │    Chunks          │
                    │                   │
                    │    INSERT INTO       │
                    │    documents:       │
                    │    - content       │
                    │    - embedding     │
                    │    - metadata      │
                    │    - url           │
                    │    - chunk_index   │
                    │    - total_chunks  │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 8. Update Status   │
                    │    to 'completed'  │
                    │                   │
                    │    SET processed_at │
                    │    = NOW()          │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │ 9. Log Success     │
                    │                   │
                    │    - URL ID         │
                    │    - Chunks Added   │
                    │    - Time Taken     │
                    └──────────────────────┘
```

### 5. Error Handling & Retry Logic

```
┌─────────────────────────────────────────────────────────────────────┐
│ ERROR HANDLING FLOW                                        │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Processing Error   │
                    │  Detected          │
                    └───────────┬────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  Check Attempts    │
                    │  Current vs Max   │
                    └───────────┬────────┘
                                │
                     ┌──────────┴──────────┐
                     ▼                     ▼
              ┌──────────────┐    ┌──────────────┐
              │Attempt < MAX │    │Attempt >= MAX│
              │(0,1,2)     │    │(3)          │
              └──────┬───────┘    └──────┬───────┘
                     │                     │
                     ▼                     ▼
          ┌─────────────────────┐  ┌──────────────────┐
          │  Retry with        │  │  Mark as Failed │
          │  Backoff          │  │                 │
          │                   │  │  Update status   │
          │  Wait Time:        │  │  = 'failed'    │
          │  [30, 60, 120]s  │  │  Log error msg  │
          │                   │  │                 │
          │  Update status      │  └──────────────────┘
          │  = 'pending'       │
          │  Increment attempts │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  Wait Backoff      │
          │  Time             │
          └──────────┬──────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │  Retry Processing  │
          │  (Same URL)       │
          └─────────────────────┘
```

### 6. API Endpoints Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ API ENDPOINTS                                              │
└──────────────────────────────────┬──────────────────────────────┘
                               │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │  Queue &     │     │  Daemon &    │     │  Scraping    │
   │  Status     │     │  Control    │     │  Endpoints   │
   │  Endpoints  │     │  Endpoints  │     │              │
   │             │     │             │     │  - /scrape    │
   │  GET /       │     │  POST /     │     │  (GET/POST) │
   │    health    │     │    daemon/   │     │  - /scrape-   │
   │             │     │    start     │     │    batch     │
   │  GET /       │     │             │     │  (GET/POST) │
   │    queue/    │     │  POST /     │     │              │
   │    status   │     │    daemon/   │     │  All process  │
   │             │     │    stop      │     │  URLs until   │
   │  Returns:   │     │             │  empty queue  │
   │  - pending  │     │  GET /       │     │              │
   │  -          │     │    daemon/   │     │  Batch size   │
   │    processing│     │    status    │  parameter    │
   │  - completed │     │             │  available    │
   │  - failed   │     │  Returns:   │  (default: 3) │
   │             │     │  - daemon_   │     │              │
   │  Queue counts│     │    running   │     │  Returns:    │
   │             │     │  - config     │     │  - success    │
   └──────────────┘     │  - queue      │     │  - processed  │
                        │    stats     │     │  - successful │
                        │  - task      │     │  - failed     │
                        │    active    │     │  - chunks     │
                        └──────────────┘     │    inserted   │
                                             │  - details    │
                                             └──────────────┘
```

## Database Schema Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ URL QUEUE TABLE                                           │
│                                                           │
│  Columns:                                                  │
│  - id (PK)                                                 │
│  - url (UNIQUE)                                             │
│  - status ('pending', 'processing', 'completed', 'failed')           │
│  - error_message                                            │
│  - attempts (default: 0)                                    │
│  - created_at                                               │
│  - updated_at                                               │
│  - processed_at                                             │
│                                                           │
│  Indexes:                                                  │
│  - idx_url_queue_status (status)                               │
└──────────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                        (URL Processed)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ DOCUMENTS TABLE                                          │
│                                                           │
│  Columns:                                                  │
│  - id (PK)                                                 │
│  - content (TEXT)                                           │
│  - metadata (JSONB)                                         │
│  - embedding (VECTOR(1536))                                  │
│  - url (TEXT)                                               │
│  - title (TEXT)                                             │
│  - chunk_index (INT)                                         │
│  - total_chunks (INT)                                        │
│  - created_at                                               │
│                                                           │
│  Indexes:                                                  │
│  - idx_documents_embedding (IVFFLAT) - Cosine similarity      │
│  - idx_documents_hnsw (HNSW) - Better performance       │
│  - idx_documents_url (url)                                  │
│                                                           │
│  RLS Policies:                                             │
│  - Public read access (authenticated)                          │
│  - Service role write access                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Real-World Usage Example

```
Month 1 Scenario:
════════════════

1. User adds 330 URLs to url_queue table via SQL
   ↓
2. User calls POST /scrape OR POST /daemon/start
   ↓
3. Daemon starts processing:
   - Batch 1: Processes 3 URLs (327 left)
   - Batch 2: Processes 3 URLs (324 left)
   - Batch 3: Processes 3 URLs (321 left)
   ... continues ...
   ↓
4. Railway restarts (maintenance/update)
   ↓
5. App restarts:
   - Startup handler detects 5 URLs stuck in 'processing'
   - Resets them to 'pending'
   - Daemon resumes processing
   ↓
6. User adds 165 more URLs
   ↓
7. Daemon automatically picks up new URLs
   ↓
8. All 498 URLs completed successfully
   ↓
9. Daemon continues running, checking every 10 seconds for new URLs
   ↓
10. Next month: User adds new URLs → Daemon processes automatically
```

## Key Features Illustrated

### 1. **Continuous Background Processing**
- Daemon runs indefinitely
- Polls queue every N seconds (configurable)
- No manual intervention needed after initial start

### 2. **Automatic Crash Recovery**
- Stuck URLs automatically reset on startup
- No data loss during restarts
- Seamless recovery without manual intervention

### 3. **Batch Processing**
- Processes URLs in parallel (configurable batch size)
- Efficient resource utilization
- Configurable for different workloads

### 4. **Retry Logic**
- 3 attempts with exponential backoff
- 30s → 60s → 120s wait times
- Failed URLs logged with error messages

### 5. **Full Refresh Strategy**
- Old chunks deleted before inserting new ones
- Clean data for each URL reprocessing
- Prevents duplicate data accumulation

### 6. **Vector Search Ready**
- pgvector extension enabled
- HNSW index for fast similarity search
- Ready for semantic queries in Supabase

## Monitoring & Debugging Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ MONITORING                                                │
└──────────────────────────────────┬──────────────────────────────┘
                               │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │  Railway    │     │  Supabase    │     │  Application │
   │  Logs       │     │  Logs       │     │  Logs       │
   │             │     │             │     │             │
   │  railway logs│     │  Dashboard   │     │  Structured  │
   │             │     │  - SQL       │     │  JSON logs  │
   │  View:      │     │  - Storage   │     │             │
   │  - Startup  │     │  - RLS       │     │  - Requests  │
   │  - Errors   │     │  - Indexes   │     │  - Processed│
   │  - Success  │     │             │     │  - Failed    │
   │             │     └──────────────┘     │  - Retries   │
   └──────────────┘                          │             │
                                             └──────────────┘
```

## Configuration Hierarchy

```
Environment Variables (.env):
├── SUPABASE_URL (Required)
├── SUPABASE_KEY (Required)
├── OPENAI_API_KEY (Required)
├── PORT (Optional, default: 8000)
├── AUTO_START_DAEMON (Optional, default: false)
│   └── true = Start daemon on app startup
│   └── false = Wait for manual /daemon/start
├── DAEMON_POLL_INTERVAL (Optional, default: 10)
│   └── Seconds between queue checks
└── DAEMON_BATCH_SIZE (Optional, default: 3)
    └── URLs processed per batch

Runtime Configuration:
├── BATCH_SIZE = 3 (Parallel processing)
├── MAX_RETRIES = 3 (Retry attempts)
└── BACKOFF_TIMES = [30, 60, 120] (Wait times in seconds)
```

## Summary

This RAG system provides:

✅ **Reliability** - Automatic crash recovery and retry logic
✅ **Scalability** - Batch processing and parallel execution
✅ **Automation** - Daemon mode runs continuously without intervention
✅ **Monitoring** - Multiple endpoints and logging for observability
✅ **Flexibility** - Configurable via environment variables
✅ **Production-Ready** - Deployed on Railway with health checks
✅ **Search-Ready** - Vector embeddings with pgvector indexes
