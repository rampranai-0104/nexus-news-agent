import os
import sys
import re
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError, OperationFailure

# Load environment variables
load_dotenv()

def mask_connection_string(text: str) -> str:
    """Mask any connection strings or passwords from exception messages."""
    if not text:
        return ""
    # Mask standard mongodb:// or mongodb+srv:// credentials
    masked = re.sub(r'mongodb(\+srv)?://([^:]+):([^@]+)@', r'mongodb\1://***:***@', str(text))
    return masked

def test_connection():
    print("==================================================")
    print("NEXUS NEWS AGENT — MONGODB ATLAS CONNECTIVITY TEST")
    print("==================================================")

    # 1. Environment Variable Verification
    mongodb_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("DATABASE_NAME", "nexus_news")

    if not mongodb_uri:
        print("MONGODB_URI: NOT FOUND in .env")
        print("RESULT: FAILED — MONGODB_URI is missing.")
        sys.exit(1)

    print("MONGODB_URI: FOUND")
    print(f"DATABASE_NAME: {database_name}")

    # 2. MongoClient Initialization
    try:
        # Connect with 10-second timeout
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10000)
        
        # 3. Ping MongoDB Atlas admin database
        print("Attempting to ping MongoDB Atlas cluster...")
        response = client.admin.command("ping")
        
        if response.get("ok") == 1.0 or response.get("ok") == 1:
            print("MongoDB ping: SUCCESS")
            print("Atlas Cluster: CONNECTED")
            print("Connection status: VERIFIED")
            print("==================================================")
            print("SUCCESS: Connection to MongoDB Atlas established successfully.")
            print("==================================================")
            client.close()
            return True
        else:
            print(f"MongoDB ping: UNEXPECTED RESPONSE ({response})")
            client.close()
            return False

    except ServerSelectionTimeoutError as e:
        print("RESULT: FAILED — Server selection timeout (10s limit reached).")
        print("Diagnosis: MongoDB Atlas cluster did not respond within 10 seconds.")
        print("Common causes:")
        print("  - Network Access / IP Whitelist: ensure your current IP address (or 0.0.0.0/0) is allowed in Atlas.")
        print("  - DNS / Firewall: ensure port 27017 and outgoing connections to Atlas are allowed.")
        print(f"Error details: {mask_connection_string(e)}")
        sys.exit(1)

    except OperationFailure as e:
        print("RESULT: FAILED — Authentication or authorization failed.")
        print("Common causes:")
        print("  - Invalid username or password in MONGODB_URI.")
        print("  - Database user does not have sufficient privileges.")
        print(f"Error details: {mask_connection_string(e)}")
        sys.exit(1)

    except PyMongoError as e:
        print("RESULT: FAILED — PyMongo connection error.")
        print(f"Error details: {mask_connection_string(e)}")
        sys.exit(1)

    except Exception as e:
        print("RESULT: FAILED — Unexpected error occurred.")
        print(f"Error details: {mask_connection_string(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
