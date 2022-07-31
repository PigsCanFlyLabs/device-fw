#define MODULE_MAC_SETUP_ENABLED (1)
#ifdef MODULE_MAC_SETUP_ENABLED
// Include required definitions first.
#include "py/obj.h"
#include "py/runtime.h"
#include "py/builtin.h"

// esp32 headers
#include "esp_err.h"
#include "esp_pm.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_wifi.h"
#include "esp_system.h"
// Our OUID is 8C:1F:64:DC:0
uint8_t mac_address[8] = {0x8C, 0x1F, 0x64, 0xDC, 0x00, 0x00};
// This is the function for python to call with trailing bits of randomness to set a MAC
STATIC mp_obj_t mac_setup_setup(mp_obj_t trailing_bits) {
  int trailing = mp_obj_get_int(trailing_bits);
  // get the last few bits from trailing matching our OUID prefix.
  mac_address[5] = trailing % 256;
  mac_address[4] = (trailing>>8) % 16;
  ESP_ERROR_CHECK(esp_base_mac_addr_set(mac_address));
  return mp_obj_new_int(mac_address[5]);
}

// Define a Python reference to the function above
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mac_setup_setup_obj, mac_setup_setup);

// Define all properties of the module.
// Table entries are key/value pairs of the attribute name (a string)
// and the MicroPython object reference.
// All identifiers and strings are written as MP_QSTR_xxx and will be
// optimized to word-sized integers by the build system (interned strings).
STATIC const mp_rom_map_elem_t mac_setup_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mac_setup) },
    { MP_ROM_QSTR(MP_QSTR_setup), MP_ROM_PTR(&mac_setup_setup_obj) },
};
STATIC MP_DEFINE_CONST_DICT(mac_setup_globals, mac_setup_module_globals_table);

// Define module object.
const mp_obj_module_t mac_setup_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&mac_setup_globals
};

// Register the module to make it available in Python
MP_REGISTER_MODULE(MP_QSTR_mac_setup, mac_setup_cmodule);
#endif
