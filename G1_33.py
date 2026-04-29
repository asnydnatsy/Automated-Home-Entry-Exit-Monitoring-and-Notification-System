import RPi.GPIO as GPIO
import time
from gpiozero import LED
import board
import busio
from adafruit_ssd1306 import SSD1306_I2C
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
import os
import threading

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Ultrasonic Sensor A (Exit)
TRIG_A = 23
ECHO_A = 17

# Ultrasonic Sensor B (Enter)
TRIG_B = 24
ECHO_B = 27

GPIO.setup(TRIG_A, GPIO.OUT)
GPIO.setup(ECHO_A, GPIO.IN)

GPIO.setup(TRIG_B, GPIO.OUT)
GPIO.setup(ECHO_B, GPIO.IN)

# --- LED Setup ---
green_led = LED(5)   # Green LED on GPIO 5
red_led = LED(6)     # Red LED on GPIO 6

# --- OLED Setup ---
i2c = busio.I2C(board.SCL, board.SDA)
oled = SSD1306_I2C(128, 64, i2c)

# Clear OLED screen
oled.fill(0)
oled.show()


def oled_show(line1, line2="", line3=""):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), line1, fill=255)
    draw.text((0, 16), line2, fill=255)
    draw.text((0, 32), line3, fill=255)
    oled.image(image)
    oled.show()

# --- TTS / Speaker Setup ---
def play_tts(text, lang="ko"):
    # generate tts
    tts = gTTS(text=text, lang=lang)
    tts.save("tts.mp3")

    # play in background
    def _play():
        os.system("mpg123 tts.mp3")

    threading.Thread(target=_play, daemon=True).start()

# ===== ULTRASONIC FUNCTION =====

MAX_DIST = 400.0   # cm
NEAR_DIST = 10.0   # cm (shoe / door area)

def get_distance_cm(TRIG, ECHO):
    """Measure distance in cm from one ultrasonic sensor. Returns None on timeout."""
    # small settling
    GPIO.output(TRIG, False)
    time.sleep(0.0002)

    # 10us pulse
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    # wait for echo start
    timeout = time.time() + 0.02  # 20ms
    while GPIO.input(ECHO) == 0:
        start = time.time()
        if time.time() > timeout:
            return None

    # wait for echo end
    timeout = time.time() + 0.02
    while GPIO.input(ECHO) == 1:
        end = time.time()
        if time.time() > timeout:
            return None

    duration = end - start
    distance = (duration * 34300) / 2  # cm
    if distance <= 0 or distance > MAX_DIST:
        return None
    return distance


# ===== LOGIC STATE =====

people_in_house = 0

# exit sequence: A (400→10) then B (10→400)
exit_phase = 0   # 0 = idle, 1 = A seeing person, 2 = A reached 10cm (shoes), wait for B

# enter sequence: B (400→10) then A (10→400)
enter_phase = 0  # 0 = idle, 1 = B seeing person, 2 = B reached 10cm (shoes), wait for A

# ===== MAIN LOGIC LOOP =====

try:
    oled_show("System ready", "person in house = 0")
    green_led.on()
    red_led.off()

    while True:
        dist_a = get_distance_cm(TRIG_A, ECHO_A)  # Sensor A (exit)
        dist_b = get_distance_cm(TRIG_B, ECHO_B)  # Sensor B (enter)

        # ---------- PERSON EXITING (A then B) ----------
        # Only start exit detection if not in enter sequence
        if enter_phase == 0:
            # Phase 0 -> 1: A sees person between 400cm and 10cm (approaching)
            if exit_phase == 0 and dist_a is not None and NEAR_DIST < dist_a <= MAX_DIST:
                exit_phase = 1
                green_led.off()
                red_led.on()

            # Phase 1 -> 2: A reaches near 10cm (shoes area)
            if exit_phase == 1 and dist_a is not None and dist_a <= NEAR_DIST:
                play_tts("have a nice day outside!", lang="en")  # or Korean if you want
                exit_phase = 2  # now wait for B

            # Phase 2 -> done: B goes from 10cm to 400cm (person leaving past B)
            if exit_phase == 2 and dist_b is not None and NEAR_DIST < dist_b <= MAX_DIST:
                people_in_house = 0
                oled_show("person in house = 0")
                green_led.on()
                red_led.off()
                exit_phase = 0  # reset

        # ---------- PERSON ENTERING (B then A) ----------
        # Only start enter detection if not in exit sequence
        if exit_phase == 0:
            # Phase 0 -> 1: B sees person between 400cm and 10cm (approaching)
            if enter_phase == 0 and dist_b is not None and NEAR_DIST < dist_b <= MAX_DIST:
                enter_phase = 1
                green_led.off()
                red_led.on()

            # Phase 1 -> 2: B reaches near 10cm (shoes area)
            if enter_phase == 1 and dist_b is not None and dist_b <= NEAR_DIST:
                play_tts("welcome home!", lang="en")  # or Korean if you want
                enter_phase = 2  # now wait for A

            # Phase 2 -> done: A goes from 10cm to 400cm (person entering past A)
            if enter_phase == 2 and dist_a is not None and NEAR_DIST < dist_a <= MAX_DIST:
                people_in_house = 1
                oled_show("person in house = 1")
                green_led.on()
                red_led.off()
                enter_phase = 0  # reset

        # (optional) debug print
        # print("A:", dist_a, "B:", dist_b, "people:", people_in_house,
        #       "exit_phase:", exit_phase, "enter_phase:", enter_phase)

        time.sleep(0.1)

except KeyboardInterrupt:
    pass

finally:
    oled.fill(0)
    oled.show()
    green_led.off()
    red_led.off()
    GPIO.cleanup()
