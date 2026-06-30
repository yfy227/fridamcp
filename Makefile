.PHONY: install dev test self-test list-tools run-stdio run-http run-mock clean build docker

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pip install pytest pytest-asyncio

test:
	FRIDAMCP_MOCK_DEVICE=1 pytest tests/ -v

test-short:
	FRIDAMCP_MOCK_DEVICE=1 pytest tests/ -v --tb=short -q

self-test:
	python -m fridamcp --self-test

list-tools:
	python -m fridamcp --list-tools

run-stdio:
	python -m fridamcp -t stdio

run-http:
	python -m fridamcp -t http -p 8768

run-mock:
	FRIDAMCP_MOCK_DEVICE=1 python -m fridamcp -t stdio

run-mock-http:
	FRIDAMCP_MOCK_DEVICE=1 python -m fridamcp -t http -p 18768

clean:
	rm -rf build/ dist/ *.egg-info fridamcp.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +

build:
	./build.sh

docker:
	docker build -t fridamcp .

docker-run:
	docker run -i --rm fridamcp

docker-run-http:
	docker run -p 8768:8768 --rm fridamcp -t http -p 8768 --host 0.0.0.0
