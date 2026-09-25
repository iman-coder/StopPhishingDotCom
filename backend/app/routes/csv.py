from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.utils.database import SessionLocal
from app.services.csv_service import export_csv, import_csv_chunked as service_import_csv_chunked
from app.utils.logger import get_logger
import io

logger = get_logger(__name__)

router = APIRouter(prefix="/urls", tags=["CSV"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/export")
def export_csv_route(db: Session = Depends(get_db)):
    csv_str = export_csv(db)

    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=urls.csv"},
    )


@router.post("/import")
async def import_csv_route(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Chunk size: 5MB (5 * 1024 * 1024 bytes)
    CHUNK_SIZE = 5 * 1024 * 1024
    
    logger.info("import_csv_route: filename=%s starting chunked import", file.filename)
    
    try:
        # Use chunked import for better memory efficiency
        result = await import_csv_chunked(file, db, chunk_size=CHUNK_SIZE)
        logger.info("import_csv_route: result=%s", result)
        return result
    except Exception as e:
        logger.exception("import_csv failed")
        raise HTTPException(status_code=500, detail=str(e))


async def import_csv_chunked(file: UploadFile, db: Session, chunk_size: int = 5 * 1024 * 1024):
    """
    Import CSV file in chunks to handle large files efficiently.
    Processes file in 5MB chunks to avoid loading entire file into memory.
    """
    # Buffer to handle partial rows at chunk boundaries
    buffer = ""
    total_size = 0
    chunk_count = 0
    
    # Preload existing URLs once (used across all chunks)
    from app.models import URL
    existing_urls = set([r[0] for r in db.query(URL.url).all()]) if db.query(URL).count() > 0 else set()
    
    # Track progress across chunks
    total_inserted = 0
    total_skipped = 0
    delimiter = None
    fieldnames = None
    
    # Read file in chunks
    while True:
        chunk_bytes = await file.read(chunk_size)
        if not chunk_bytes:
            break
            
        chunk_count += 1
        total_size += len(chunk_bytes)
        
        # Decode chunk (handle encoding errors gracefully)
        try:
            chunk_text = chunk_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                chunk_text = chunk_bytes.decode("latin-1")
            except Exception as e:
                logger.error("Failed to decode chunk %d: %s", chunk_count, e)
                raise HTTPException(status_code=400, detail="Invalid file encoding")
        
        # Combine buffer (partial row from previous chunk) with new chunk
        full_chunk = buffer + chunk_text
        
        # Process chunk and get remaining partial row for next iteration
        result = service_import_csv_chunked(
            full_chunk, 
            db, 
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=(chunk_count == 1)
        )
        
        # Update state from first chunk
        if chunk_count == 1:
            delimiter = result.get("delimiter")
            fieldnames = result.get("fieldnames")
        
        # Accumulate results
        total_inserted += result.get("inserted", 0)
        total_skipped += result.get("skipped", 0)
        
        # Get remaining buffer (partial row at end of chunk)
        buffer = result.get("buffer", "")
        
        # Update existing_urls set with newly inserted URLs to avoid duplicates
        if result.get("inserted_urls"):
            existing_urls.update(result.get("inserted_urls", []))
        
        logger.debug("Chunk %d processed: %d inserted, %d skipped, buffer size: %d", 
                    chunk_count, result.get("inserted", 0), result.get("skipped", 0), len(buffer))
    
    # Process any remaining buffer (last partial row)
    if buffer.strip():
        result = service_import_csv_chunked(
            buffer,
            db,
            existing_urls=existing_urls,
            delimiter=delimiter,
            fieldnames=fieldnames,
            is_first_chunk=False
        )
        total_inserted += result.get("inserted", 0)
        total_skipped += result.get("skipped", 0)
    
    logger.info("import_csv_chunked: total_size=%d bytes, chunks=%d, inserted=%d, skipped=%d", 
                total_size, chunk_count, total_inserted, total_skipped)
    
    return {
        "inserted": total_inserted,
        "skipped": total_skipped,
        "chunks_processed": chunk_count,
        "total_size_bytes": total_size
    }