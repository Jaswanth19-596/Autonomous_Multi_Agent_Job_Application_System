from apify_client import ApifyClient
import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Determine project root and data directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
EXCEL_PATH = DATA_DIR / "jobs.xlsx"

client = ApifyClient(os.environ.get("APIFY_API_TOKEN", ""))


def save_jobs_to_excel(jobs: list[dict], file_path: Path = EXCEL_PATH):
    """
    Appends new job search results to an Excel file.

    - New jobs receive ``application_status = "Not Applied"`` and a
      ``fetched_at`` timestamp.
    - Existing rows are **never overwritten**, so manually-updated status
      values are preserved across runs.
    - Deduplication is based on the ``id`` column.
    """
    if not jobs:
        return

    # Ensure data directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Process complex structures (lists/dicts) into string representations for Excel
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    processed_jobs = []
    for job in jobs:
        job_copy = dict(job)
        for key, val in job_copy.items():
            if isinstance(val, (list, dict)):
                job_copy[key] = str(val) if val else ""
        # Tag every new job with default status and fetch timestamp
        job_copy.setdefault("application_status", "Not Applied")
        job_copy.setdefault("fetched_at", now)
        processed_jobs.append(job_copy)

    new_df = pd.DataFrame(processed_jobs).astype(str)

    # Append to existing Excel file, preserving existing rows
    if file_path.exists() and file_path.stat().st_size > 0:
        try:
            existing_df = pd.read_excel(file_path, dtype=str)
        except Exception as exc:
            print(f"⚠️  Could not read existing {file_path}, starting fresh: {exc}")
            existing_df = pd.DataFrame()

        if not existing_df.empty:
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            if "id" in combined_df.columns:
                # keep="first" → the *existing* row wins, preserving its status
                combined_df.drop_duplicates(subset=["id"], keep="first", inplace=True)
            else:
                combined_df.drop_duplicates(keep="first", inplace=True)

            prev_count = len(existing_df)
            new_count = len(combined_df) - prev_count
            combined_df.to_excel(file_path, index=False)
            print(f"✅ Appended {new_count} new job(s) to {file_path} "
                  f"(total: {len(combined_df)})")
            return

    new_df.to_excel(file_path, index=False)
    print(f"✅ Created {file_path} with {len(new_df)} job(s)")


def search_jobs(keywords, location, under10Applicants: bool = False ):
    """
    Search LinkedIn job postings using Apify.

    Use this tool when the user asks to find current or recently
    posted jobs. Returns structured job listings and saves them to data/jobs.xlsx.
    """

    run_input = {
        "keywords": keywords,   # string
        "location": location, # string
        "geoId": "",  # string
        "distance": 0,  # int
        "datePosted": "past24Hours",  #"anyTime", "past24Hours", "pastWeek", "pastMonth" 
        "companyIds": [],  # list of strings
        "under10Applicants": under10Applicants,  # boolean
        "autoConvertToAiSearch": True,  # boolean
        "scrapeCompany": True, # boolean
        "limitPerSource": 100, # int
        "splitByLocation": False, # boolean
        "splitCountry": "US", # string
    }

    run = client.actor("hKByXkMQaC5Qt9UMN").call(
        run_input=run_input
    )

    dataset_id = run["default_dataset_id"] if isinstance(run, dict) else run.default_dataset_id

    results = list(client.dataset(dataset_id).iterate_items())
    
    save_jobs_to_excel(results, EXCEL_PATH)

    return results


if __name__ == "__main__":
    search_jobs(keywords="AI Engineer", location="United States")