#!/bin/bash

source common.sh

source "${venv_dir}/bin/activate"
pushd "${build_dir}/microPython/project/micropython/ports/esp32"

PORT=${PORT:-${1:-/dev/ttyUSB0}}
BOARD=${BOARD:-${2:-"SPACEBEAVER_C3"}}

~/.espressif/python_env/idf4.4_py3.8_env/bin/python ../../../../../esp-idf/components/esptool_py/esptool/esptool.py -p ${PORT} -b 460800 --before default_reset --after hard_reset --chip esp32c3  write_flash --flash_mode dio --flash_size detect --flash_freq 80m 0x0 build-${BOARD}/bootloader/bootloader.bin 0x8000 build-${BOARD}/partition_table/partition-table.bin 0x10000 build-${BOARD}/micropython.bin
