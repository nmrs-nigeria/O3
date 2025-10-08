import pandas as pd
import requests
import json
import time
from math import ceil

import http.client as http_client
import logging

http_client.HTTPConnection.debuglevel = 1
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

# ================================
# CONFIGURATION
# ================================
EXCEL_FILE = "OCL_All_Concepts_Bulk_Upload.xlsx"
OCL_API_URL = "https://api.openconceptlab.org"  # or staging URL
ORG_ID = "anwokoma@ihvnigeria.org"
SOURCE_ID = "IHVN"
API_TOKEN = "bec8227b5ae4a96dc2372f37e23891462dd902fc"  # replace with your OCL API token
BATCH_SIZE = 100

# ================================
# FUNCTION DEFINITIONS
# ================================

def build_concept(row):
    """Convert one Excel row to OCL bulk import JSON object"""
    concept = {
        "action": "create",
        "type": "Concept",
        "owner": ORG_ID,
        "owner_type": "User",
        "source": SOURCE_ID,
        "id": str(row["id"]).strip(),
        "external_id": str(row["external_id"]).strip() if not pd.isna(row["external_id"]) else None,
        "concept_class": str(row["concept_class"]).strip() if not pd.isna(row["concept_class"]) else "Misc",
        "datatype": str(row["datatype"]).strip() if not pd.isna(row["datatype"]) else "Text",
        "names": [
            {
                "name": str(row["name"]).strip(),
                "locale": "en",
                "locale_preferred": True,
                "name_type": "Fully Specified"
            }
        ],
        "descriptions": [],
        "extras": {}
    }

    # Optional: description
    if not pd.isna(row.get("description")) and str(row["description"]).strip():
        concept["descriptions"].append({
            "description": str(row["description"]).strip(),
            "locale": "en"
        })

    # Optional extras
    extras = {}
    for col in ["form_name", "html_question_text"]:
        if col in row and not pd.isna(row[col]):
            extras[col] = str(row[col]).strip()
    concept["extras"] = extras

    return concept


def upload_batch(batch, batch_num):
    """Upload one batch to OCL bulk import endpoint (with verbose error reporting)"""
    url = f"{OCL_API_URL}/importers/bulk-import/"
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }

    data = json.dumps(batch, indent=2)
    try:
        response = requests.post(url, headers=headers, data=data)

        # Try to get more detailed information from OCL's response
        try:
            resp_json = response.json()
        except Exception:
            resp_json = {"raw_text": response.text}

        if response.status_code in [200, 201, 202]:
            print(f"✅ Batch {batch_num} uploaded successfully.")
            return True

        elif response.status_code == 409:
            print(f"⚠️ Batch {batch_num}: Conflict (409). Some concepts may already exist.")
            return True

        else:
            print(f"\n❌ Batch {batch_num} failed:")
            print(f"Status: {response.status_code}")
            print("Response:")
            print(json.dumps(resp_json, indent=2))
            log_error(batch_num, resp_json)
            return False

    except Exception as e:
        print(f"\n❌ Batch {batch_num} upload error: {str(e)}")
        log_error(batch_num, str(e))
        return False


def log_error(batch_num, error):
    """Save failed batch info"""
    with open("ocl_upload_errors.log", "a", encoding="utf-8") as f:
        f.write(f"\n\nBatch {batch_num} failed at {time.ctime()}\n{str(error)}\n")


# ================================
# MAIN SCRIPT
# ================================
if __name__ == "__main__":
    print("📦 Reading Excel file...")
    df = pd.read_excel(EXCEL_FILE)
    print(f"Total concepts found: {len(df)}")

    # Convert all rows to concept objects
    concepts = [build_concept(row) for _, row in df.iterrows()]

    # Split into batches
    total_batches = ceil(len(concepts) / BATCH_SIZE)
    print(f"🚀 Starting upload in {total_batches} batches of {BATCH_SIZE}...")

    success_count = 0
    for i in range(total_batches):
        batch = concepts[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        print(f"\nUploading batch {i+1}/{total_batches} ({len(batch)} concepts)...")
        success = upload_batch(batch, i + 1)
        if success:
            success_count += len(batch)
        time.sleep(2)  # polite delay to avoid API throttling

    print(f"\n✅ Upload completed! Successfully uploaded {success_count} concepts.")
    print("Check 'ocl_upload_errors.log' for any skipped or failed batches.")
