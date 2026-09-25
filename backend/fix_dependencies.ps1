# PowerShell script to fix FastAPI/Pydantic compatibility
# Run this from the backend directory with venv activated

Write-Host "Fixing FastAPI/Pydantic compatibility..." -ForegroundColor Green

# Uninstall conflicting packages
Write-Host "Uninstalling old versions..." -ForegroundColor Yellow
pip uninstall -y fastapi pydantic pydantic-core

# Install compatible versions
Write-Host "Installing compatible versions..." -ForegroundColor Yellow
pip install "fastapi>=0.104.0,<0.110.0"
pip install "pydantic>=2.0.0,<3.0.0"
pip install "pydantic-core>=2.0.0"

# Verify versions
Write-Host "`nVerifying versions..." -ForegroundColor Green
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import pydantic; print(f'Pydantic: {pydantic.__version__}')"

Write-Host "`nDone! Try running pytest again." -ForegroundColor Green

