from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")  # default sqlite

# Handle SQLite in-memory tests: use a shared-cache in-memory URI so that
# multiple connections (engine + sessions) see the same in-memory database.
# If tests set DATABASE_URL to 'sqlite:///:memory:' we translate it to
# 'sqlite:///file::memory:?cache=shared' and enable URI parsing.
connect_args = {}
engine_url = DATABASE_URL
if DATABASE_URL.startswith("sqlite") and ":memory:" in DATABASE_URL:
	# Use shared-cache memory DB and allow cross-thread access
	engine_url = "sqlite:///file::memory:?cache=shared"
	connect_args = {"check_same_thread": False, "uri": True}
else:
	if "sqlite" in DATABASE_URL:
		connect_args = {"check_same_thread": False}
		# If using a file-based sqlite URL, ensure parent directory exists
		# so SQLite can create the file. Example URL formats handled:
		# - sqlite:///./data/test.db
		# - sqlite:///C:/absolute/path/to/db.sqlite
		try:
			if engine_url.startswith("sqlite:///") and "file::memory:" not in engine_url:
				db_path = engine_url.replace("sqlite:///", "", 1)
				# On Windows the path may begin with a drive letter like C:/
				parent = os.path.dirname(db_path)
				if parent and not os.path.exists(parent):
					os.makedirs(parent, exist_ok=True)
		except Exception:
			# If directory creation fails, let SQLAlchemy raise the original error later.
			pass

engine = create_engine(engine_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
