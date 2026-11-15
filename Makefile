run:
	cd backend && python -m uvicorn app.main:app --port 8000
test:
	cd backend && python -m pytest -q
install:
	pip install -r backend/requirements.txt -r backend/requirements-dev.txt
