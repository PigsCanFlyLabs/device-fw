include("$(BOARD_DIR)/../manifest.py")
freeze("$(MPY_DIR)/drivers/display", "ssd1306.py")


freeze(".",
       ("boot.py",
        "Satellite.py",
        "UARTBluetooth.py",
        "test_utils.py",
        "display_wrapper.py",
       ),
)
