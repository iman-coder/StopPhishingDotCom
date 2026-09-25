# app/services/csv_service.py

import csv
from io import StringIO
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import URL
from app.schemas import URLCreate
from app.utils.logger import get_logger
from app.utils.threat import normalize_threat, risk_score

logger = get_logger(__name__)


# -------- CSV IMPORT -------- #

def import_csv(file_content: str, db: Session):
    """Legacy import function - processes entire file at once."""
    existing_urls = set([r[0] for r in db.query(URL.url).all()]) if db.query(URL).count() > 0 else set()
    return _process_csv_content(file_content, db, existing_urls, None, None, True)


def import_csv_chunked(
    file_content: str, 
    db: Session,
    existing_urls: set = None,
    delimiter: str = None,
    fieldnames: list = None,
    is_first_chunk: bool = True
):
    """
    Process a chunk of CSV content. Handles partial rows at chunk boundaries.
    
    Args:
        file_content: CSV content (may be partial chunk)
        db: Database session
        existing_urls: Set of existing URLs to check duplicates
        delimiter: CSV delimiter (detected on first chunk)
        fieldnames: CSV column names (detected on first chunk)
        is_first_chunk: Whether this is the first chunk (for header detection)
    
    Returns:
        dict with: inserted, skipped, buffer (remaining partial row), delimiter, fieldnames, inserted_urls
    """
    if existing_urls is None:
        existing_urls = set([r[0] for r in db.query(URL.url).all()]) if db.query(URL).count() > 0 else set()
    
    return _process_csv_content(file_content, db, existing_urls, delimiter, fieldnames, is_first_chunk, chunked=True)


def _process_csv_content(
    file_content: str,
    db: Session,
    existing_urls: set,
    delimiter: str = None,
    fieldnames: list = None,
    is_first_chunk: bool = True,
    chunked: bool = False
):
    """
    Internal function to process CSV content.
    For chunked processing, handles partial rows at boundaries.
    """
    # Detect delimiter on first chunk
    if delimiter is None:
        sample = file_content[:4096] if len(file_content) > 4096 else file_content
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t'])
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ','
    
    # Find the last complete line (for chunked processing)
    buffer = ""
    content_to_process = file_content
    
    if chunked:
        # Find last newline to identify complete rows
        last_newline = file_content.rfind('\n')
        if last_newline != -1:
            # Process complete rows, keep partial row in buffer
            content_to_process = file_content[:last_newline + 1]
            buffer = file_content[last_newline + 1:]
        # If no newline found, entire chunk might be a partial row
        elif file_content:
            buffer = file_content
            content_to_process = ""
    
    if not content_to_process:
        # No complete rows to process, return buffer
        return {
            "inserted": 0,
            "skipped": 0,
            "buffer": buffer,
            "delimiter": delimiter,
            "fieldnames": fieldnames,
            "inserted_urls": []
        }
    
    reader = csv.DictReader(StringIO(content_to_process), delimiter=delimiter, fieldnames=fieldnames)
    
    # Capture fieldnames on first chunk
    if is_first_chunk and reader.fieldnames:
        fieldnames = reader.fieldnames
        # Log detected headers
        try:
            norm_fieldnames = [fn.strip().lower() if fn else fn for fn in fieldnames]
            logger.info("import_csv: detected delimiter='%s' headers=%s", delimiter, fieldnames)
            logger.debug("import_csv: normalized headers=%s", norm_fieldnames)
        except Exception:
            logger.debug("import_csv: could not read headers")
    
    created_count = 0
    skipped = []
    seen = set()
    inserted_urls = []

    def _parse_risk_field(val):
        """Parse a CSV risk/threat field which may be textual ('high','malicious')
        or numeric ('90', '55') and return a canonical threat label.

        Numeric thresholds (coarse):
          >= 75 -> 'malicious'
          40-74 -> 'suspicious'
          < 40  -> 'safe'
        """
        if val is None:
            return None
        if isinstance(val, (int, float)):
            score = int(val)
            if score >= 75:
                return "malicious"
            if score >= 40:
                return "suspicious"
            return "safe"
        # string value: try numeric parse first
        s = str(val).strip()
        if s == "":
            return None
        # Try parse as integer/float
        try:
            n = float(s)
            return _parse_risk_field(int(n))
        except Exception:
            # fallback: treat as textual threat and normalize
            return normalize_threat(s)

    for row in reader:
        # Normalize row keys (case-insensitive, trim) and values
        norm_row = { (k.strip().lower() if k else k): (v.strip() if isinstance(v, str) else v) for k, v in (row.items() if row else []) }
        # Accept 'url' column in any case / with spaces
        url_value = norm_row.get("url") or norm_row.get("link") or norm_row.get("uri")
        if not url_value:
            skipped.append(norm_row)
            continue

        # Avoid duplicate URLs (both in DB and already seen in this import)
        if url_value in existing_urls or url_value in seen:
            skipped.append(norm_row)
            continue

        # normalize threat text so stored values are canonical
        # Accept multiple column names that might provide risk info
        raw_threat = norm_row.get("threat") or norm_row.get("risk") or norm_row.get("risk_score") or norm_row.get("score")
        # parse numeric/textual risk into canonical label
        normalized = _parse_risk_field(raw_threat) or normalize_threat(raw_threat)

        # Compute numeric risk_score to store (preserve numeric if present,
        # otherwise map textual labels to coarse scores via `risk_score()`)
        numeric_score = None
        if raw_threat is not None:
            # try numeric parse first
            try:
                n = float(str(raw_threat).strip())
                # clamp to 0-100 and store integer value
                numeric_score = max(0, min(100, int(n)))
            except Exception:
                # textual -> use helper mapping
                try:
                    numeric_score = int(max(0, min(100, risk_score(str(raw_threat)))))
                except Exception:
                    numeric_score = None
        new_url = URL(
            url=url_value,
            domain=norm_row.get("domain") or norm_row.get("host"),
            threat=normalized,
            risk_score=numeric_score,
            status=norm_row.get("status"),
            source=norm_row.get("source"),
        )

        db.add(new_url)
        created_count += 1
        seen.add(url_value)
        inserted_urls.append(url_value)
        
        # Commit in batches of 1000 to avoid long transactions
        if created_count % 1000 == 0:
            db.commit()
            logger.debug("Committed batch: %d URLs inserted so far", created_count)

    # Final commit
    db.commit()

    logger.info("import_csv: inserted=%s skipped=%s", created_count, len(skipped))
    if skipped and not chunked:
        # log up to 10 skipped rows for debugging (only for non-chunked)
        logger.debug("import_csv skipped rows sample: %s", skipped[:10])

    result = {
        "inserted": created_count,
        "skipped": len(skipped),
    }
    
    if chunked:
        result.update({
            "buffer": buffer,
            "delimiter": delimiter,
            "fieldnames": fieldnames,
            "inserted_urls": inserted_urls
        })
    
    return result


# -------- CSV EXPORT -------- #

def export_csv(db: Session) -> str:
    urls = db.query(URL).all()

    output = StringIO()
    writer = csv.writer(output)

    # CSV header (include risk_score if present)
    writer.writerow(["id", "url", "domain", "threat", "risk_score", "date_added", "status", "source"])

    # CSV rows
    for item in urls:
        writer.writerow([
            item.id,
            item.url,
            item.domain,
            item.threat,
            item.risk_score if getattr(item, "risk_score", None) is not None else "",
            item.date_added.isoformat() if item.date_added is not None else "",
            item.status,
            item.source,
        ])

    return output.getvalue()
