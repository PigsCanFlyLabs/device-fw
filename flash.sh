#!/bin/bash

source common.sh

source "${venv_dir}/bin/activate"
pushd "${build_dir}/microPython/project/micropython/ports/esp32"


~/.espressif/python_env/idf4.3_py3.8_env/bin/python ../../../../../esp-idf/components/esptool_py/esptool/esptool.py -p ${1} -b 460800 --before default_reset --after hard_reset --chip esp32  write_flash --flash_mode dio --flash_size detect --flash_freq 40m 0x1000 build-GENERIC/bootloader/bootloader.bin 0x8000 build-GENERIC/partition_table/partition-table.bin 0x10000 build-GENERIC/micropython.bin
