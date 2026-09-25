import os
import io

# Ensure test environment variables are set before importing the app
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SINGLE_ADMIN_USERNAME", "admin")
os.environ.setdefault("SINGLE_ADMIN_PASSWORD", "changeme")
os.environ.setdefault("SECRET_KEY", "test-secret-123")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_health():
    r = client.get("/urls/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_auth_token_and_protected_delete():
    # Unauthenticated delete should be rejected
    r = client.delete("/urls/")
    assert r.status_code in (401, 403)

    # Obtain token using seeded admin
    r = client.post("/auth/token", data={"username": "admin", "password": "changeme"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    token = body["access_token"]

    # Use token to call protected endpoint
    headers = {"Authorization": f"Bearer {token}"}
    r = client.delete("/urls/", headers=headers)
    assert r.status_code == 200
    j = r.json()
    assert "deleted" in j


def test_create_and_list_url():
    payload = {"url": "http://example.com", "domain": "example.com"}
    r = client.post("/urls/", json=payload)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created.get("url") == "http://example.com"

    r = client.get("/urls/")
    assert r.status_code == 200
    urls = r.json()
    assert any(u.get("url") == "http://example.com" for u in urls)


def test_chunked_csv_import():
    """Test chunked CSV import via API endpoint."""
    # Get auth token
    r = client.post("/auth/token", data={"username": "admin", "password": "changeme"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a CSV file that will be processed in chunks
    # Generate a large CSV content (simulating 100MB file with smaller data for testing)
    header = "url,domain,threat,status,source\n"
    rows = []
    for i in range(500):  # 500 rows for testing
        rows.append(f"https://test{i}.example.com,test{i}.example.com,malicious,new,import\n")
    
    csv_content = header + "".join(rows)
    
    # Create file-like object
    csv_file = io.BytesIO(csv_content.encode("utf-8"))
    
    # Upload CSV
    files = {"file": ("test.csv", csv_file, "text/csv")}
    r = client.post("/urls/import", files=files, headers=headers)
    
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    result = r.json()
    
    # Verify results
    assert "inserted" in result
    assert "skipped" in result
    assert result["inserted"] == 500, f"Expected 500 inserted, got {result['inserted']}"
    
    # Verify chunks_processed is present (indicates chunked processing)
    assert "chunks_processed" in result or "total_size_bytes" in result
    
    # Verify URLs were actually inserted
    r = client.get("/urls/", headers=headers)
    assert r.status_code == 200
    urls = r.json()
    assert len(urls.get("items", [])) >= 500, f"Expected at least 500 URLs, got {len(urls.get('items', []))}"
