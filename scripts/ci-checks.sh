#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

set -e

if [ "$1" == "-f" ]; then
  FIX=1
else
  FIX=0
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

ROOT_DIR=$( dirname "$SCRIPT_DIR" )
pushd "$ROOT_DIR" > /dev/null

CHECK_DELIMITER="---------------------------"

echo "$CHECK_DELIMITER"
echo "-- Shell scripts"
git ls-files | grep -e '\.sh$' | grep -E -v "^3rdparty" | xargs shellcheck -s bash -e SC2044,SC2002,SC1091,SC2181

echo "$CHECK_DELIMITER"
echo "-- TODOs"
"$SCRIPT_DIR"/check-todo.sh include src

echo "$CHECK_DELIMITER"
echo "-- C/C++/Proto format"
if [ $FIX -ne 0 ]; then
  "$SCRIPT_DIR"/check-format.sh -f include src samples proto
else
  "$SCRIPT_DIR"/check-format.sh include src samples proto
fi

echo "$CHECK_DELIMITER"
echo "-- TypeScript, JavaScript, Markdown, YAML and JSON format"
npm install --loglevel=error --no-save prettier 1>/dev/null
if [ $FIX -ne 0 ]; then
  git ls-files -- . ':!:3rdparty/' | grep -e '\.ts$' -e '\.js$' -e '\.md$' -e '\.yaml$' -e '\.yml$' -e '\.json$' | xargs npx prettier --write
else
  git ls-files -- . ':!:3rdparty/' | grep -e '\.ts$' -e '\.js$' -e '\.md$' -e '\.yaml$' -e '\.yml$' -e '\.json$' | xargs npx prettier --check
fi

echo "$CHECK_DELIMITER"
echo "-- Copyright notice headers"
python3 "$SCRIPT_DIR"/notice_check.py

echo "$CHECK_DELIMITER"
echo "-- CMake format"
if [ $FIX -ne 0 ]; then
  "$SCRIPT_DIR"/check-cmake-format.sh -f cmake samples src tests CMakeLists.txt
else
  "$SCRIPT_DIR"/check-cmake-format.sh cmake samples src tests CMakeLists.txt
fi

echo "$CHECK_DELIMITER"
echo "-- Python dependencies"
# Virtual Environment w/ dependencies for Python steps
VENV_DIR=.venv
if [ ! -f "${VENV_DIR}/bin/activate" ]
    then
        python3.8 -m venv ${VENV_DIR}
fi

# shellcheck source=/dev/null
source ${VENV_DIR}/bin/activate
pip install -U pip
pip install -U wheel black[jupyter] pylint mypy cpplint 1>/dev/null
pip install -r requirements.txt

echo "$CHECK_DELIMITER"
echo "-- Python format"
if [ $FIX -ne 0 ]; then
  git ls-files | grep -e '\.py$' -e '\.ipynb$' | xargs black
else
  git ls-files | grep -e '\.py$' -e '\.ipynb$' | xargs black --check
fi

echo "$CHECK_DELIMITER"
echo "-- Python lint"
git ls-files | grep -e '\.py$' | xargs python -m pylint --ignored-modules "*_pb2" --disable duplicate-code

echo "$CHECK_DELIMITER"
echo "-- Python types"
git ls-files | grep -e '\.py$' | xargs mypy

echo "$CHECK_DELIMITER"
echo "-- CPP Lint"
make cpplint
