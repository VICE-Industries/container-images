# based on https://github.com/abcminiuser/python-elgato-streamdeck

from functools import partial
import os
import signal
import threading
import time

from loguru import logger
from pyModbusTCP.client import ModbusClient
from PIL import Image, ImageDraw, ImageFont
import requests
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper

# Folder location of image assets used by this example.
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "Assets")

ADDRESS_LED = os.environ.get("ADDRESS_LED", "192.168.88.201")
ADDRESS_GATEWAY = os.environ.get("ADDRESS_GATEWAY", "192.168.88.20")


def get_modbus_client():
    return ModbusClient(
        host=ADDRESS_GATEWAY, unit_id=1, auto_open=True, auto_close=True, timeout=0.5
    )


def sigterm_handler(signum, frame, deck):
    logger.info("SIGTERM received")
    deck.reset()
    deck.close()


# Generates a custom tile with run-time generated text and custom image via the
# PIL module.
def render_key_image(deck, icon_filename, font_filename, label_text):
    # Resize the source image asset to best-fit the dimensions of a single key,
    # leaving a margin at the bottom so that we can draw the key title
    # afterwards.
    icon = Image.open(icon_filename)
    image = PILHelper.create_scaled_image(deck, icon, margins=[0, 0, 20, 0])

    # Load a custom TrueType font and use it to overlay the key index, draw key
    # label onto the image a few pixels from the bottom of the key.
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_filename, 14)
    draw.text(
        (image.width / 2, image.height - 5),
        text=label_text,
        font=font,
        anchor="ms",
        fill="white",
    )

    return PILHelper.to_native_format(deck, image)


# Returns styling information for a key based on its position and state.
def get_key_style(deck, key, state):
    # Last button in the example application is the exit button.
    exit_key_index = deck.key_count() - 1

    if key == exit_key_index:
        name = "exit"
        icon = "{}.png".format("Exit")
        font = "Roboto-Regular.ttf"
        label = "Bye" if state else "Exit"
    else:
        name = "emoji"
        icon = "{}.png".format("Pressed" if state else "Released")
        font = "Roboto-Regular.ttf"
        label = "Pressed!" if state else "Key {}".format(key)

    return {
        "name": name,
        "icon": os.path.join(ASSETS_PATH, icon),
        "font": os.path.join(ASSETS_PATH, font),
        "label": label,
    }


# Creates a new key image based on the key index, style and current key state
# and updates the image on the StreamDeck.
def update_key_image(deck, key, state):
    # Determine what icon and label to use on the generated key.
    key_style = get_key_style(deck, key, state)

    # Generate the custom key with the requested image and label.
    image = render_key_image(
        deck, key_style["icon"], key_style["font"], key_style["label"]
    )

    # Use a scoped-with on the deck to ensure we're the only thread using it
    # right now.
    with deck:
        # Update requested key with the generated image.
        deck.set_key_image(key, image)


# Prints key state change information, updates rhe key image and performs any
# associated actions when a key is pressed.
def key_change_callback(deck, key, state):
    red_key_index = 0
    green_key_index = 1
    blue_key_index = 2

    left_key_index = 3
    right_key_index = 4

    url_led = f"http://{ADDRESS_LED}/color"

    # Print new key state
    logger.info("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

    # Update the key image based on the new key state.
    update_key_image(deck, key, state)

    # Check if the key is changing to the pressed state.
    if state:
        key_style = get_key_style(deck, key, state)

        if key == red_key_index:
            logger.info("Color is now RED")
            requests.post(f"{url_led}?red=255&green=0&blue=0")
        elif key == green_key_index:
            logger.info("Color is now GREEN")
            requests.post(f"{url_led}?red=0&green=255&blue=0")
        elif key == blue_key_index:
            logger.info("Color is now BLUE")
            requests.post(f"{url_led}?red=0&green=0&blue=255")
        elif key == left_key_index:
            u1 = get_modbus_client()
            u1.write_single_coil(0x00, True)
            time.sleep(3)

            u1 = get_modbus_client()
            u1.write_single_coil(0x00, False)
        elif key == right_key_index:
            u1 = get_modbus_client()
            u1.write_single_coil(0x01, True)
            time.sleep(3)

            u1 = get_modbus_client()
            u1.write_single_coil(0x01, False)

        # When an exit button is pressed, close the application.
        if key_style["name"] == "exit":
            logger.info("Color is now OFF")
            requests.post(f"{url_led}?red=0&green=0&blue=0")

            logger.info("Transport is now OFF")
            u1 = get_modbus_client()
            u1.write_single_coil(0x00, False)
            u1.write_single_coil(0x01, False)

            # Use a scoped-with on the deck to ensure we're the only thread
            # using it right now.
            with deck:
                # Reset deck, clearing all button images.
                deck.reset()

                # Close deck handle, terminating internal worker threads.
                deck.close()


if __name__ == "__main__":
    streamdecks = DeviceManager().enumerate()

    logger.info("Found {} Stream Deck(s).\n".format(len(streamdecks)))

    for index, deck in enumerate(streamdecks):
        # This example only works with devices that have screens.
        if not deck.is_visual():
            continue

        # We only have 1 streamdeck inside the pod
        signal.signal(signal.SIGTERM, partial(sigterm_handler, deck=deck))

        deck.open()
        deck.reset()

        logger.info(
            "Opened '{}' device (serial number: '{}', fw: '{}')".format(
                deck.deck_type(), deck.get_serial_number(), deck.get_firmware_version()
            )
        )

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        # Set initial key images.
        for key in range(deck.key_count()):
            update_key_image(deck, key, False)

        # Register callback function for when a key state changes.
        deck.set_key_callback(key_change_callback)

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            try:
                t.join()
            except RuntimeError:
                pass
