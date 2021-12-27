#!/bin/bash
set -ex

(((dpkg -l |grep gcc-arm-none-eabi) || sudo apt-get update; sudo apt-get install -y build-essential libreadline-dev libffi-dev git pkg-config gcc-arm-none-eabi libnewlib-arm-none-eabi python3-virtualenv) &> apt.logs) || (cat apt.logs; exit 1)


export SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export build_dir="${SCRIPT_DIR}/tmp-build"
export venv_dir="${build_dir}/microPython"
