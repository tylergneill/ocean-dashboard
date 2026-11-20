# Ocean registration progress dashboard.
#
#   make data    rebuild docs/data/progress.json from the sibling repos
#                (paths in config.toml)
#   make serve   open the page at http://localhost:8765
#   make stop    free the port by killing whatever is listening on it
#   make free-server-port   kill whatever holds the serve port
#   make test    run the link-rule tests in tests/
#   make         data and serve

PORT ?= 8765

all: data serve

test:
	python3 -m unittest

data:
	python3 build_progress.py

serve:
	@echo "http://localhost:$(PORT)"
	python3 -m http.server $(PORT) --directory docs

free-server-port:
	kill $$(lsof -ti tcp:$(PORT))

.PHONY: all data serve test free-server-port
