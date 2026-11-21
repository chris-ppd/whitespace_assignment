.PHONY: setup run test reviews

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

run:
	cd frontend && npm run build
	cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

test:
	.venv/bin/pytest backend/tests

reviews:
	./review data/plans/harbour-run.md data/reviews/harbour-run.json
	python3 check_contract.py review data/reviews/harbour-run.json
	./review data/plans/lantern-festival.md data/reviews/lantern-festival.json
	python3 check_contract.py review data/reviews/lantern-festival.json
	./review data/plans/spring-market.md data/reviews/spring-market.json
	python3 check_contract.py review data/reviews/spring-market.json
