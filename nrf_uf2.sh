source common.sh

set -ex

source "${venv_dir}/bin/activate"
pushd "${build_dir}/microPython/project/micropython/ports/nrf"

BOARD=${NRF_BOARD:-${BOARD:-${2:-"SPACEBEAVER_NRF"}}}

python ../../tools/uf2conv.py -f 0xADA52840 -c -o "build-${BOARD}-s140/out.uf2" build-${BOARD}-s140/firmware.hex
pwd
