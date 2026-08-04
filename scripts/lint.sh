#!/bin/bash


set -ev

cd /app
autoflake --in-place --recursive --remove-unused-variables --remove-all-unused-imports --exclude docker/,.git/ .
isort --line-length 120 --multi-line VERTICAL_HANGING_INDENT --trailing-comma .
black --exclude '(docker/|\.direnv|\.eggs|\.git|\.mypy_cache|\.nox|\.tox|\.venv|venv|\.ipynb_checkpoints|_build|buck-out|build|dist|__pypackages__)' -l 120 .
flake8 --max-line-length=80 --exclude=.tox,.git,*/migrations/*,*/static/CACHE/*,docs,node_modules,docker/data/ --ignore=I001,I003,I004,E231,E501,W503
