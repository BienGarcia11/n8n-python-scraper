import asyncio
import pandas as pd
from dotenv import load_dotenv
from worker import run_scraper, OUTPUT_CSV, OUTPUT_XLSX
from embedder import generate_embeddings
from uploader import upload_to_supabase

# Load environment variables
load_dotenv()

# --- POST PROCESSING LOGIC ---
def post_processing(csv_file, xlsx_file):
    """
    Runs after scraping. 
    1. Generates Embeddings.
    2. Uploads to Supabase.
    """
    # 1. Load Excel to show stats (Easier to view for human)
    print(f"\nManager: Loading stats from {xlsx_file}...")
    try:
        df_stats = pd.read_excel(xlsx_file)
        total = len(df_stats)
        success = len(df_stats[df_stats['status'] == 'Success'])
        fail = total - success
        print(f"Manager: Total Rows: {total}")
        print(f"Manager: Success: {success}")
        print(f"Manager: Failed: {fail}")
    except:
        print("Manager: Could not load Excel stats.")

    # 2. Run Embedder (Uses CSV for full data)
    if success > 0:
        print("Manager: Starting Embedding process...")
        generate_embeddings(input_file=csv_file, output_file="embedded_data.csv")
        
        # 3. Run Uploader (Uses embedded CSV)
        print("Manager: Starting Upload process...")
        upload_to_supabase("embedded_data.csv")
    else:
        print("Manager: No data to embed.")

# --- MAIN CONTROLLER ---
async def main():
    try:
        # 1. RUN SCRAPER
        # Worker returns the CSV filename
        output_csv = await run_scraper()
        
        if output_csv:
            # 2. RUN INTEGRATIONS
            post_processing(csv_file=OUTPUT_CSV, xlsx_file=OUTPUT_XLSX)
        else:
            print("Manager: Worker returned no file. Exiting.")
            
    except KeyboardInterrupt:
        print("\nManager: Stopped by user.")

if __name__ == "__main__":
    asyncio.run(main())