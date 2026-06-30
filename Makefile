.PHONY: install dev test self-test list-tools run-stdio run-http run-mock clean build docker version check-version publish-test publish tag-release

VERSION := $(shell python -c "from fridamcp import __version__; print(__version__)")

install:
        pip install -e .

dev:
        pip install -e ".[dev]"

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

version:
        @echo "FridaMCP v$(VERSION)"

check-version:
        @echo "Checking version consistency..."
        @python -c "from fridamcp import __version__; print(f'  __init__.py: {__version__}')"
        @python -c "import setuptools; print('  setup.py: OK')" 2>/dev/null
        @grep -q "$(VERSION)" setup.py && echo "  setup.py: $(VERSION) ✓" || echo "  setup.py: MISMATCH ✗"
        @grep -q "$(VERSION)" CHANGELOG.md && echo "  CHANGELOG.md: $(VERSION) ✓" || echo "  CHANGELOG.md: MISMATCH ✗"

clean:
        rm -rf build/ dist/ *.egg-info fridamcp.egg-info
        find . -type d -name __pycache__ -exec rm -rf {} +
        find . -type d -name .pytest_cache -exec rm -rf {} +

build:
        ./build.sh

build-pypi:
        python -m build

publish-test: build-pypi
        twine upload --repository testpypi dist/*

publish: build-pypi
        twine upload dist/*

tag-release:
        @echo "Creating tag v$(VERSION)..."
        git tag -a v$(VERSION) -m "Release v$(VERSION)"
        git push origin v$(VERSION)
        @echo "Tag v$(VERSION) pushed. GitHub Actions will build binaries and publish to PyPI."

docker:
        docker build -t fridamcp .

docker-run:
        docker run -i --rm fridamcp

docker-run-http:
        docker run -p 8768:8768 --rm fridamcp -t http -p 8768 --host 0.0.0.0
