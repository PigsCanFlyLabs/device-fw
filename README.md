# device-fw
FW for the device

## General Design

In general there are three components:
1) Interface to the satelite modem
2) Interface to the BTLE device
3) setup + mainloop

For the most part the interface to the satelite modem waits for the satelite modem to enter a "ready" state and then informs the BTLE device it is ready.

### Satelite interface

The satelite interface is implemented according to https://swarm.space/wp-content/uploads/2021/11/Swarm-Hive-API-Integration-Guide.pdf?utm_source=google&utm_medium=cpc&utm_term=iot_satellite&utm_content=Ad_2&utm_campaign=Google_Search_Broad_NB_Satellite_US&gclid=CjwKCAiA1aiMBhAUEiwACw25MUVEAeBC9Aya0srzd70CdkbINKhBvqLUu0YiMLmKG4PBpcVlNlffuRoCOYUQAvD_BwE (e.g. Swarm Hive 1.3 API Integration Guide).

Most message types are blindly sent through 

Special consideration:
1) when txing_pin from the modem is set to high the ESP32 *must* disable all TXing on BT/Wifi.
(note this is not implemented yet).

### BTLE interface

The BTLE interface follows the nordic UART profile.

Prior to sending or receiving actual data, an unsigned little endian message indicating the size of the message to follow should be written.


#### When receiving msgs:
The first character after message length received by the BTLE interface dictates which method will be called.

For 'M':
the next two bytes are the application id
the remainder of the message is a UTF-8 encoded string which will be relayed to the modem more or less directly as a $TD message.
For clarity the client _should not_ send another message until after the message is ackd with eather "MSGID: {id}" or "ERROR: ..."

For 'P':
The message represents a phone id / profile.
No response.

TODO:
For '?':
Requests the current phone id / profile.

For 'R':
Raw modem command.

For 'F':
Upload new firmware *for* the modem (to be stored on the ESP32 pending verification).

For 'W':
Write the latest firmware to the modem *if* it's a higher version than on the modem.

#### When sending msgs:

Unsolicited msg received from satelites:
MSG {app_id} {msg}

Error:
ERROR {error}

When a queued message has been sent to satelites: 
ACK {msgid}

When ready for msgs:
READY

TODO:

When receiving an otherwise unhandled message
RAW {msg}
