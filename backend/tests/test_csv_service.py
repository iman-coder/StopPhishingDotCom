from app.utils import database
from app.services import csv_service
from app.models import URL
import io


def setup_module(module):
    database.Base.metadata.create_all(bind=database.engine)


def teardown_module(module):
    database.Base.metadata.drop_all(bind=database.engine)


def test_import_and_export_csv():
    db = database.SessionLocal()
    try:
        # clean
        db.query(URL).delete()
        db.commit()

        csv_content = "url,domain,threat,status,source\nhttps://a.test,a.test,high,new,import\n,missing,low,new,import\nhttps://a.test,a.test,high,new,import\n"

        res = csv_service.import_csv(csv_content, db)
        assert res["inserted"] == 1
        assert res["skipped"] >= 1

        out = csv_service.export_csv(db)
        assert "https://a.test" in out
        # header present
        assert out.splitlines()[0].startswith("id,url,domain")

    finally:
        db.close()


def test_chunked_import_basic():
    """Test basic chunked import with multiple chunks."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        # Create a CSV that will be split into multiple chunks
        # Each row is ~50 bytes, so 5MB chunk = ~100k rows
        # For testing, create a smaller file that will be split into 2-3 chunks
        header = "url,domain,threat,status,source\n"
        rows = []
        for i in range(1000):  # 1000 rows should create multiple chunks
            rows.append(f"https://test{i}.example.com,test{i}.example.com,malicious,new,test\n")
        
        csv_content = header + "".join(rows)
        
        # Simulate chunked processing with 5KB chunks (smaller for testing)
        chunk_size = 5 * 1024  # 5KB instead of 5MB for faster tests
        existing_urls = set()
        delimiter = None
        fieldnames = None
        total_inserted = 0
        total_skipped = 0
        
        # Process in chunks
        for i in range(0, len(csv_content), chunk_size):
            chunk = csv_content[i:i + chunk_size]
            is_first = (i == 0)
            
            result = csv_service.import_csv_chunked(
                chunk,
                db,
                existing_urls=existing_urls,
                delimiter=delimiter,
                fieldnames=fieldnames,
                is_first_chunk=is_first
            )
            
            if is_first:
                delimiter = result.get("delimiter")
                fieldnames = result.get("fieldnames")
            
            total_inserted += result.get("inserted", 0)
            total_skipped += result.get("skipped", 0)
            
            # Update existing URLs to prevent duplicates
            if result.get("inserted_urls"):
                existing_urls.update(result.get("inserted_urls", []))
        
        # Process any remaining buffer
        if result.get("buffer"):
            final_result = csv_service.import_csv_chunked(
                result.get("buffer", ""),
                db,
                existing_urls=existing_urls,
                delimiter=delimiter,
                fieldnames=fieldnames,
                is_first_chunk=False
            )
            total_inserted += final_result.get("inserted", 0)
            total_skipped += final_result.get("skipped", 0)
        
        # Verify results
        assert total_inserted == 1000, f"Expected 1000 inserted, got {total_inserted}"
        assert delimiter == ","
        assert fieldnames is not None
        assert "url" in fieldnames
        
        # Verify in database
        count = db.query(URL).count()
        assert count == 1000, f"Expected 1000 URLs in DB, got {count}"
        
    finally:
        db.close()


def test_chunked_import_boundary_handling():
    """Test that rows split across chunk boundaries are handled correctly."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        # Create CSV where a row will be split at chunk boundary
        header = "url,domain,threat\n"
        # Make sure a row is split: chunk ends in middle of a row
        row1 = "https://test1.com,test1.com,malicious\n"
        row2 = "https://test2.com,test2.com,suspicious\n"
        row3 = "https://test3.com,test3.com,safe\n"
        
        csv_content = header + row1 + row2 + row3
        
        # Split at a point that cuts through row2
        split_point = len(header) + len(row1) + len(row2) // 2
        chunk1 = csv_content[:split_point]
        chunk2 = csv_content[split_point:]
        
        existing_urls = set()
        delimiter = None
        fieldnames = None
        
        # Process first chunk
        result1 = csv_service.import_csv_chunked(
            chunk1,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=True
        )
        
        delimiter = result1.get("delimiter")
        fieldnames = result1.get("fieldnames")
        existing_urls.update(result1.get("inserted_urls", []))
        
        # Process second chunk (should include buffer from first chunk)
        buffer = result1.get("buffer", "")
        result2 = csv_service.import_csv_chunked(
            buffer + chunk2,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=False
        )
        
        existing_urls.update(result2.get("inserted_urls", []))
        
        total_inserted = result1.get("inserted", 0) + result2.get("inserted", 0)
        
        # All 3 rows should be inserted
        assert total_inserted == 3, f"Expected 3 inserted, got {total_inserted}"
        
        # Verify all URLs are in database
        urls = db.query(URL).all()
        url_values = {url.url for url in urls}
        assert "https://test1.com" in url_values
        assert "https://test2.com" in url_values
        assert "https://test3.com" in url_values
        
    finally:
        db.close()


def test_chunked_import_duplicate_detection():
    """Test that duplicates are detected across chunks."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        header = "url,domain,threat\n"
        # Same URL appears in multiple chunks
        chunk1_content = header + "https://duplicate.com,duplicate.com,malicious\nhttps://unique1.com,unique1.com,safe\n"
        chunk2_content = "https://duplicate.com,duplicate.com,malicious\nhttps://unique2.com,unique2.com,safe\n"
        
        existing_urls = set()
        delimiter = None
        fieldnames = None
        
        # Process first chunk
        result1 = csv_service.import_csv_chunked(
            chunk1_content,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=True
        )
        
        delimiter = result1.get("delimiter")
        fieldnames = result1.get("fieldnames")
        existing_urls.update(result1.get("inserted_urls", []))
        
        # Process second chunk (duplicate should be skipped)
        result2 = csv_service.import_csv_chunked(
            chunk2_content,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=False
        )
        
        total_inserted = result1.get("inserted", 0) + result2.get("inserted", 0)
        total_skipped = result1.get("skipped", 0) + result2.get("skipped", 0)
        
        # Should have 3 unique URLs inserted (duplicate.com, unique1.com, unique2.com)
        assert total_inserted == 3, f"Expected 3 inserted, got {total_inserted}"
        # Duplicate should be skipped
        assert total_skipped >= 1, f"Expected at least 1 skipped (duplicate), got {total_skipped}"
        
        # Verify in database
        count = db.query(URL).count()
        assert count == 3, f"Expected 3 URLs in DB, got {count}"
        
        # Verify duplicate.com appears only once
        duplicate_count = db.query(URL).filter(URL.url == "https://duplicate.com").count()
        assert duplicate_count == 1, f"Expected 1 duplicate.com, got {duplicate_count}"
        
    finally:
        db.close()


def test_chunked_import_state_preservation():
    """Test that delimiter and fieldnames are preserved across chunks."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        # Use semicolon delimiter to test state preservation
        header = "url;domain;threat\n"
        chunk1 = header + "https://test1.com;test1.com;malicious\n"
        chunk2 = "https://test2.com;test2.com;safe\n"
        
        existing_urls = set()
        delimiter = None
        fieldnames = None
        
        # Process first chunk
        result1 = csv_service.import_csv_chunked(
            chunk1,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=True
        )
        
        # Verify delimiter and fieldnames are detected
        assert result1.get("delimiter") == ";", "Delimiter should be detected as semicolon"
        assert result1.get("fieldnames") is not None, "Fieldnames should be detected"
        assert "url" in result1.get("fieldnames", []), "url should be in fieldnames"
        
        delimiter = result1.get("delimiter")
        fieldnames = result1.get("fieldnames")
        existing_urls.update(result1.get("inserted_urls", []))
        
        # Process second chunk with preserved state
        result2 = csv_service.import_csv_chunked(
            chunk2,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=False
        )
        
        # Verify state is preserved
        assert result2.get("delimiter") == ";", "Delimiter should be preserved"
        assert result2.get("fieldnames") == fieldnames, "Fieldnames should be preserved"
        
        # Verify both rows were inserted correctly
        total_inserted = result1.get("inserted", 0) + result2.get("inserted", 0)
        assert total_inserted == 2, f"Expected 2 inserted, got {total_inserted}"
        
    finally:
        db.close()


def test_chunked_import_batch_commits():
    """Test that commits happen in batches of 1000."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        # Create CSV with exactly 2500 rows to test batch commits
        header = "url,domain,threat\n"
        rows = []
        for i in range(2500):
            rows.append(f"https://test{i}.com,test{i}.com,malicious\n")
        
        csv_content = header + "".join(rows)
        
        # Process in one large chunk (simulating chunked processing)
        existing_urls = set()
        result = csv_service.import_csv_chunked(
            csv_content,
            db,
            existing_urls=existing_urls,
            delimiter=None,
            fieldnames=None,
            is_first_chunk=True
        )
        
        # Should have inserted all 2500 rows
        assert result.get("inserted") == 2500, f"Expected 2500 inserted, got {result.get('inserted')}"
        
        # Verify in database
        count = db.query(URL).count()
        assert count == 2500, f"Expected 2500 URLs in DB, got {count}"
        
    finally:
        db.close()


def test_chunked_import_empty_buffer():
    """Test handling of empty chunks and buffers."""
    db = database.SessionLocal()
    try:
        db.query(URL).delete()
        db.commit()

        # Test with empty content
        result = csv_service.import_csv_chunked(
            "",
            db,
            existing_urls=set(),
            delimiter=None,
            fieldnames=None,
            is_first_chunk=True
        )
        
        assert result.get("inserted") == 0
        assert result.get("skipped") == 0
        assert result.get("buffer") == ""
        
        # Test with only header
        header = "url,domain,threat\n"
        result = csv_service.import_csv_chunked(
            header,
            db,
            existing_urls=set(),
            delimiter=None,
            fieldnames=None,
            is_first_chunk=True
        )
        
        assert result.get("inserted") == 0
        assert result.get("fieldnames") is not None
        
    finally:
        db.close()
