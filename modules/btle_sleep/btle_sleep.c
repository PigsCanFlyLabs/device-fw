// Include required definitions first.
#include "py/obj.h"
#include "py/runtime.h"
#include "py/builtin.h"

#ifdef MODULE_BTLE_SLEEP_ENABLED
// esp32 headers
#include "esp_err.h"
#include "esp_pm.h"

// This is the function which will be called from Python as btle_sleep.deep_sleep(a, b).
STATIC void auto_sleep(mp_obj_t min_obj, mp_obj_t max_obj) {
    // Extract the ints from the micropython input objects
    int min = mp_obj_get_int(min_obj);
    int max = mp_obj_get_int(max_obj);

    esp_pm_config_esp32_t pm_config = {
        .max_freq_mhz = max, // e.g. 80, 160, 240
        .min_freq_mhz = min, // e.g. 40
        .light_sleep_enable = true, // enable light sleep
    };
    ESP_ERROR_CHECK( esp_pm_configure(&pm_config) );
}
// Define a Python reference to the function above
STATIC MP_DEFINE_CONST_FUN_OBJ_2(auto_sleep_obj, auto_sleep);

// Define all properties of the btle sleep module.
// Table entries are key/value pairs of the attribute name (a string)
// and the MicroPython object reference.
// All identifiers and strings are written as MP_QSTR_xxx and will be
// optimized to word-sized integers by the build system (interned strings).
STATIC const mp_rom_map_elem_t btle_sleep_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_btle_sleep) },
    { MP_ROM_QSTR(MP_QSTR_auto_sleep), MP_ROM_PTR(&auto_sleep_obj) },
};
STATIC MP_DEFINE_CONST_DICT(example_module_globals, example_module_globals_table);

// Define module object.
const mp_obj_module_t btle_sleep_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&btle_sleep
    _module_globals,
};

// Register the module to make it available in Python
MP_REGISTER_MODULE(MP_QSTR_btle_sleep, btle_sleep_user_cmodule, MODULE_BTLE_SLEEP_ENABLED);
#endif
