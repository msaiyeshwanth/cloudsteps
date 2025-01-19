import os
import json
import base64
from google.cloud import storage, bigquery
import xml.etree.ElementTree as ET
from datetime import datetime

def process_health_data(event, context):
    try:
        # Decode and parse the Pub/Sub message
        pubsub_message = json.loads(base64.b64decode(event['data']).decode('utf-8'))
        file_name = pubsub_message['file']
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error decoding message: {e}")
        return

    # Initialize Google Cloud Storage client
    storage_client = storage.Client()
    bucket_name = 'health-data-xml-bucket'
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)

    # Download the XML file
    xml_data = blob.download_as_text()

    # Parse XML data to extract steps data
    tree = ET.ElementTree(ET.fromstring(xml_data))
    root = tree.getroot()

    records = []
    for record in root.findall(".//Record[@type='HKQuantityTypeIdentifierStepCount']"):
        start_date = record.get('startDate')
        value = int(record.get('value'))
        date_obj = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S %z')
        records.append((date_obj, value))

    if not records:
        print("No records found in the XML file.")
        return

    # Get the start and end dates of the records
    start_date = min(record[0] for record in records).date()
    end_date = max(record[0] for record in records).date()

    # Initialize BigQuery client
    client = bigquery.Client()
    dataset_id = 'health_dataset'
    table_id = 'steps_data'

    # Delete existing rows in the date range
    delete_query = f"""
    DELETE FROM `{client.project}.{dataset_id}.{table_id}`
    WHERE DATE(date) BETWEEN '{start_date}' AND '{end_date}'
    """
    try:
        delete_job = client.query(delete_query)
        delete_job.result()  # Wait for the query to complete
        print(f"Deleted rows for date range: {start_date} to {end_date}")
    except Exception as e:
        print(f"Error deleting rows: {e}")
        return

    # Insert new data into BigQuery
    rows_to_insert = [{"date": record[0].isoformat(), "steps": record[1]} for record in records]
    errors = client.insert_rows_json(f"{client.project}.{dataset_id}.{table_id}", rows_to_insert)

    if errors:
        print(f"Error inserting rows: {errors}")
    else:
        print(f"Successfully processed and inserted {len(rows_to_insert)} records into BigQuery.")
