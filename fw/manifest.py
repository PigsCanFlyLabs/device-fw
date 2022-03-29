include("$(BOARD_DIR)/../manifest.py")
freeze("$(MPY_DIR)/drivers/display", "ssd1306.py")


freeze(".",
       ("boot.py",
        "Satelite.py",
        "UARTBluetooth.py",
       ),
)
