#!/bin/bash
set -ex

(dpkg -l |grep gcc-arm-none-eabi) || sudo apt-get install -y build-essential libreadline-dev libffi-dev git pkg-config gcc-arm-none-eabi libnewlib-arm-none-eabi
if ! command -v virtualenv &> /dev/null; then
  sudo apt-get install -y python3-virtualenv
fi


export SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export build_dir="${SCRIPT_DIR}/tmp-build"
export venv_dir="${build_dir}/microPython"
