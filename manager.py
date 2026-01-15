import asyncio
import pandas as pd
from dotenv import load_dotenv
from worker import run_scraper
from embedder import generate_embeddings
from uploader import upload_to_supabase

# Load environment variables at the very start
load_dotenv()

# --- POST PROCESSING LOGIC ---
def post_processing(csv_file):
    """
    Runs after scraping. 
    1. Reads stats from CSV.
    2. Generates Embeddings.
    3. Uploads to Supabase.
    """
    print(f"\nManager: Loading stats from {csv_file}...")
    
    try:
        # Read CSV for stats
        df = pd.read_csv(csv_file)
        
        total = len(df)
        success = len(df[df['status'] == 'Success'])
        fail = total - success
        print(f"Manager: Total Rows: {total}")
        print(f"Manager: Successful Scrapes: {success}")
        print(f"Manager: Failed Scrapes: {fail}")
        
        # --- RUN EMBEDDER ---
        if success > 0:
            print("Manager: Starting Embedding process...")
            # Input is CSV, Output is CSV
            generate_embeddings(input_file=csv_file, output_file="embedded_data.csv")
            
            # --- RUN UPLOADER ---
            print("Manager: Starting Upload process...")
            upload_to_supabase("embedded_data.csv")
        else:
            print("Manager: No data to embed or upload.")
        
    except Exception as e:
        print(f"Manager: Error during processing: {e}")

# --- NEW WRAPPER FOR API ---
async def main_controller():
    """
    This is the function main.py calls. 
    It mimics what the __main__ block did.
    """
    try:
        output_csv = await run_scraper()
        
        if output_csv:
            post_processing(csv_file=output_csv)
        else:
            print("Controller: Worker returned no file. Exiting.")
            
    except Exception as e:
        print(f"Controller: Error {e}")

# Keep this for local testing
if __name__ == "__main__":
    asyncio.run(main_controller())