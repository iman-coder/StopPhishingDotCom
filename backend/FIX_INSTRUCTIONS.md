# Fix FastAPI/Pydantic Compatibility Issue

## Problem
The error `AttributeError: 'FieldInfo' object has no attribute 'in_'` occurs because FastAPI version is incompatible with Pydantic v2.

## Solution

### Option 1: Quick Fix (Recommended)
```powershell
# Activate venv first
cd "C:\Users\thinkpad\Desktop\Phising detector"
.\venv\Scripts\Activate.ps1

# Navigate to backend
cd backend

# Run the fix script
.\fix_dependencies.ps1
```

### Option 2: Manual Fix
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Navigate to backend
cd backend

# Uninstall old versions
pip uninstall -y fastapi pydantic pydantic-core

# Install compatible versions
pip install "fastapi>=0.104.0,<0.110.0"
pip install "pydantic>=2.0.0,<3.0.0"

# Reinstall all requirements
pip install -r requirements.txt
```

### Option 3: Fresh Install
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Navigate to backend
cd backend

# Reinstall everything
pip install --upgrade --force-reinstall -r requirements.txt
```

## Verify Installation
After fixing, verify versions:
```powershell
python -c "import fastapi; print('FastAPI:', fastapi.__version__)"
python -c "import pydantic; print('Pydantic:', pydantic.__version__)"
```

You should see:
- FastAPI: 0.104.x or higher
- Pydantic: 2.x.x

## Run Tests
```powershell
pytest -q
```

The error should be resolved!

