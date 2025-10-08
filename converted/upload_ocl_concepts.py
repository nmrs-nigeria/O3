import pandas as pd
import requests
import json
import math
import time

# ========== CONFIGURATION ==========
EXCEL_FILE = "OCL_All_Concepts_Bulk_Upload.xlsx"
OCL_API_URL = "https://api.openconceptlab.org"  # or staging URL
USERNAME = "anwokoma@ihvnigeria.org"
SOURCE_ID = "IHVN"
API_TOKEN = "bec8227b5ae4a96dc2372f37e23891462dd902fc"  # replace with your OCL API token
BATCH_SIZE = 100
# ===================================

# Step 1. Read Excel
print("📘 Loading Excel file...")
df = pd.read_excel(EXCEL_FILE)
print(f"✅ Loaded {len(df)} rows")

# Normalize column names (case-insensitive match)
df.columns = [col.strip().lower() for col in df.columns]

# Step 2. Convert rows to OCL concept JSON
concepts = []
for _, row in df.iterrows():
    name = str(row.get("name") or "").strip()
    description = str(row.get("description") or "").strip()

    # Skip if completely empty name
    if not name:
        continue

    # Default description if missing
    if not description:
        description = "No description provided."

    form_name = str(row.get("form_name") or "").strip()
    html_question_text = str(row.get("html_question_text") or "").strip()

    metadata = {}
    if form_name:
        metadata["form_name"] = form_name
    if html_question_text:
        metadata["html_question_text"] = html_question_text

    concept = {
        "id": str(row.get("id") or "").strip(),
        "external_id": str(row.get("external_id") or "").strip(),
        "concept_class": str(row.get("concept_class") or "Misc").strip(),
        "datatype": str(row.get("datatype") or "Text").strip(),
        "names": [
            {
                "name": name,
                "locale": "en",
                "locale_preferred": True,
                "name_type": "Fully Specified"
            }
        ],
        "descriptions": [
            {
                "description": description,
                "locale": "en"
            }
        ],
        "owner": USERNAME,
        "owner_type": "User",
        "source": SOURCE_ID,
        "type": "Concept",
        "extras": metadata  # <-- custom metadata here
    }

    # Remove empty keys
    concept = {k: v for k, v in concept.items() if v not in [None, "", []]}
    concepts.append(concept)

print(f"🧩 Prepared {len(concepts)} valid concepts for upload")

if len(concepts) == 0:
    print("⚠️ No valid concepts found with non-empty names. Please check your Excel file.")
    print("👉 Ensure your column name is exactly 'name' (case-insensitive).")
    exit(0)

# Step 3. Upload in batches via OCL Bulk Import API
num_batches = math.ceil(len(concepts) / BATCH_SIZE)
print(f"\n🚀 Starting bulk upload in {num_batches} batches of up to {BATCH_SIZE} concepts...")

headers = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json"
}

def upload_batch(batch, batch_num):
    url = f"{OCL_API_URL}/importers/bulk-import/"
    payload = {"data": batch}

    print(f"\n📦 Uploading batch {batch_num}/{num_batches} ({len(batch)} concepts)...")
    print("🧠 Example payload:")
    print(json.dumps(batch[0], indent=2))

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print(f"🔁 Status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"✅ Batch {batch_num} uploaded successfully.")
        else:
            print(f"❌ Batch {batch_num} failed.")
            print("Response text:")
            print(response.text)
            print("Partial payload sample:")
            print(json.dumps(batch[:2], indent=2))
    except Exception as e:
        print(f"🚨 Exception during batch {batch_num}: {e}")

# Step 4. Upload all batches
for i in range(num_batches):
    start = i * BATCH_SIZE
    end = min(start + BATCH_SIZE, len(concepts))
    batch = concepts[start:end]
    if not batch:
        continue
    upload_batch(batch, i + 1)
    time.sleep(2)

print("\n🎉 Upload process complete.")
