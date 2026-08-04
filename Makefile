ifeq ($(CI),true)
	DOCKER_EXEC_FLAGS = -T
else
	DOCKER_EXEC_FLAGS = -it
endif
COMPOSE = docker compose
COMPOSE_RUN = $(COMPOSE) run --rm $(DOCKER_EXEC_FLAGS)

ifeq ($(ENV_TYPE),development)
	MAIN_RUN =
else
	MAIN_RUN = $(COMPOSE_RUN) main
endif

bash: 								# Run bash inside `main` container
	$(MAIN_RUN) bash

bash-root: 							# Run bash as root inside `main` container
	$(COMPOSE_RUN) -u root main bash

build: 								# Build containers
	$(COMPOSE) build

container-clean: 					# Clean orphan containers
	$(COMPOSE) down -v --remove-orphans

help:								# List all make commands
	@awk -F ':.*#' '/^[a-zA-Z_-]+:.*?#/ { printf "\033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST) | sort

kill:								# Force stop (kill) and remove containers
	$(COMPOSE) kill
	$(COMPOSE) rm --force

lint:								# Run linter script inside `main` container
	$(MAIN_RUN) /app/scripts/lint.sh

package-build:						# Build the Python package in `dist/`
	rm -rf build dist
	$(MAIN_RUN) python -m build
	$(MAIN_RUN) twine check dist/*

package-release: package-build		# Build and release the package to PyPI
	$(MAIN_RUN) twine upload dist/*

package-test-release: package-build	# Build and test-release the package (to test.pypi.org)
	$(MAIN_RUN) twine upload --repository-url https://test.pypi.org/legacy/ dist/*

test:								# Execute `pytest` and coverage report
	$(MAIN_RUN) bash -c 'coverage run --include="outgram/*" -m pytest --doctest-modules --pdb -vvvs tests/ outgram/ $(TEST_ARGS) && coverage report'

.PHONY:	bash bash-root build container-clean help kill lint package-build package-release package-test-release test
