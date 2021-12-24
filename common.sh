#!/bin/bash
set -ex

export SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export build_dir="${SCRIPT_DIR}/tmp-build"
export venv_dir="${build_dir}/microPython"
