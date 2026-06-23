import sys
from src.pipeline import process_telemetry_file
import pandas as pd

if __name__ == "__main__":
    print("Testing pipeline on RawData.xlsx...")
    try:
        with open("RawData.xlsx", "rb") as f:
            output_bytes, df = process_telemetry_file(f, "RawData.xlsx", report_config_id=1)
            
        if output_bytes:
            with open("test_output.xlsx", "wb") as f:
                f.write(output_bytes.read())
            print("Successfully processed and wrote test_output.xlsx.")
            print("\nPreview of Results:")
            print(df.head())
        else:
            print("Pipeline returned no data.")
    except Exception as e:
        print(f"Error during testing: {e}")
