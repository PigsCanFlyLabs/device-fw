# Create an INTERFACE library for our C module.
add_library(usermod_btle_sleep INTERFACE)

# Add our source files to the lib
target_sources(usermod_btle_sleep INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/btle_sleep.c
)

# Add the current directory as an include directory.
target_include_directories(usermod_btle_sleep INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Link our INTERFACE library to the usermod target.
target_link_libraries(usermod INTERFACE usermod_btle_sleep)
