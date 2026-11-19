# Ocean registration progress dashboard.
#
#   make data    rebuild docs/data/progress.json from the sibling repos
#                (paths in config.toml)
#   make serve   open the page at http://localhost:8765
#   make         both

PORT ?= 8765

all: data serve

data:
	python3 build_progress.py

serve:
	@echo "http://localhost:$(PORT)"
	python3 -m http.server $(PORT) --directory docs

.PHONY: all data serve
