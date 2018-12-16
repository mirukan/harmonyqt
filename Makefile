# Copyright 2018 miruka
# This file is part of harmonyqt, licensed under GPLv3.

PKG_DIR = harmonyqt

PYTHON = python3
PIP    = pip3
PYLINT = pylint
MYPY   = mypy
CLOC   = cloc

ARCHIVE_FORMATS = gztar
INSTALL_FLAGS   = --process-dependency-links --user --editable
PYLINT_FLAGS    = --output-format colorized
MYPY_FLAGS      = --ignore-missing-imports
CLOC_FLAGS      = --ignore-whitespace

.PHONY: all clean dist install upload test


all: clean dist install

clean:
	find . -name '__pycache__' -exec rm -Rfv {} +
	find . -name '*.pyc'       -exec rm -Rfv {} +
	find . -name '*.egg-info'  -exec rm -Rfv {} +
	rm -Rfv build dist

dist: clean
	@echo
	${PYTHON} setup.py sdist --format ${ARCHIVE_FORMATS}
	@echo
	${PYTHON} setup.py bdist_wheel

install: clean
	@echo
	${PIP} install ${INSTALL_FLAGS} .


upload: dist
	@echo
	twine upload dist/*


test:
	- ${PYLINT} ${PYLINT_FLAGS} ${PKG_DIR} *.py
	@echo
	- ${MYPY}   ${MYPY_FLAGS}   ${PKG_DIR} *.py
	@echo
	${CLOC} ${CLOC_FLAGS} ${PKG_DIR}
