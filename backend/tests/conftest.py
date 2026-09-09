import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("EMAIL_TEST_MODE", "true")
os.environ.setdefault("GOOGLE_SHEETS_ID", "")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
