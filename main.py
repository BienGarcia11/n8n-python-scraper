import threading
import sys
import os
import asyncio
from fastapi import FastAPI, BackgroundTasks
from dotenv import load_dotenv
from logger_config import setup_logger

# --- LOGGER SETUP ---
logger = setup_logger("API")

# Import your logic
# We use the controller from manager which handles the full pipeline + logging
from manager import main_controller

# Load env vars
load_dotenv()

app = FastAPI()

# --- JOB MANAGEMENT ---
IS_RUNNING = False

@app.get("/")
def read_root():
    return {"status": "ready", "message": "Call POST /start to begin scraping"}

async def run_job_wrapper():
    """
    Wrapper to run the pipeline and update global state.
    """
    global IS_RUNNING
    try:
        logger.info("Starting background job...")
        await main_controller()
    except Exception as e:
        logger.exception(f"Job Wrapper Error: {e}")
    finally:
        IS_RUNNING = False
        logger.info("Background job finished.")

@app.post("/start")
async def start_scraping_job(background_tasks: BackgroundTasks):
    global IS_RUNNING
    
    if IS_RUNNING:
        logger.warning("Attempted to start job while one is already running.")
        return {"status": "error", "message": "Job is already running"}
    
    IS_RUNNING = True
    
    # Run in background using FastAPI's system
    background_tasks.add_task(run_job_wrapper)
    
    logger.info("Received start signal.")
    return {"status": "started", "message": "Scraping started in background."}

@app.get("/status")
def check_status():
    """
    Checks if the job is running.
    """
    if IS_RUNNING:
        return {"status": "running"}
    else:
        return {"status": "idle"}