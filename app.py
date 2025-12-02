import os
import time
import threading
import subprocess
import board
import busio
import adafruit_si4713
import RPi.GPIO as GPIO
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import pygame

# --- Configuration (Unchanged) ---
AUDIO_DIR = '/home/pi/ghost_radio/audio'
GHOST_DIR = os.path.join(AUDIO_DIR, 'ghosts')
STATIC_SOUND_PATH = os.path.join(AUDIO_DIR, 'static.mp3')
RESET_PIN_BCM = 18
TRANSMIT_POWER = 115
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'wma', 'm4a', 'ogg', 'flac'}

# --- Global App Variables (Unchanged) ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = GHOST_DIR
current_fm_frequency = 0.0

# --- Pygame Audio Setup (Unchanged) ---
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
pygame.mixer.set_num_channels(2)
static_sound_object = pygame.mixer.Sound(STATIC_SOUND_PATH)

# --- Helper and Conversion Functions (Unchanged) ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_mp3(original_filepath):
    try:
        filename_without_ext = os.path.splitext(os.path.basename(original_filepath))[0]
        new_mp3_filepath = os.path.join(GHOST_DIR, f"{filename_without_ext}.mp3")
        print(f"Starting conversion for: {original_filepath}")
        command = ['ffmpeg', '-i', original_filepath, '-ac', '1', '-ar', '44100', '-b:a', '128k', new_mp3_filepath]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Conversion successful for {new_mp3_filepath}")
        os.remove(original_filepath)
        print(f"Deleted original file: {original_filepath}")
    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        if os.path.exists(original_filepath):
            os.remove(original_filepath)

# --- FM Transmitter and Audio Player Functions (Unchanged) ---
def setup_fm_transmitter():
    # ... (This function remains exactly the same as before)
    global current_fm_frequency; print("Setting up Si4713..."); GPIO.setmode(GPIO.BCM); GPIO.setup(RESET_PIN_BCM, GPIO.OUT); GPIO.output(RESET_PIN_BCM, GPIO.LOW); time.sleep(0.1); GPIO.output(RESET_PIN_BCM, GPIO.HIGH); i2c = busio.I2C(board.SCL, board.SDA)
    try: si4713 = adafruit_si4713.SI4713(i2c)
    except Exception as e: print(f"Failed to initialize Si4713: {e}"); current_fm_frequency = 102.3; return
    print("Scanning FM band..."); best_freq_khz, max_noise = 0, -1
    for freq_khz in range(88100, 107900, 200):
        try:
            noise = si4713.received_noise_level(freq_khz);
            if noise > max_noise: max_noise, best_freq_khz = noise, freq_khz
        except Exception: pass
    if best_freq_khz == 0: best_freq_khz = 102300
    current_fm_frequency = best_freq_khz / 1000.0; print(f"Broadcasting on: {current_fm_frequency} MHz"); si4713.tx_frequency_khz, si4713.tx_power = best_freq_khz, TRANSMIT_POWER

def play_ghost_sound(filename):
    filepath = os.path.join(GHOST_DIR, filename)
    if os.path.exists(filepath):
        print(f"Playing ghost sound: {filename}")
        try:
            ghost_sound_object = pygame.mixer.Sound(filepath)
            pygame.mixer.Channel(1).play(ghost_sound_object)
        except Exception as e: print(f"Error playing sound: {e}")

# --- Flask Web Server Routes ---
@app.route('/')
def index():
    ghost_files = sorted([f for f in os.listdir(GHOST_DIR) if f.endswith('.mp3')])
    return render_template('index.html', files=ghost_files, freq=current_fm_frequency)

@app.route('/play', methods=['POST'])
def play_button_click():
    file_to_play = request.form['filename']
    play_ghost_sound(file_to_play)
    return ('', 204)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'ghostfile' not in request.files: return redirect(url_for('index'))
    file = request.files['ghostfile']
    if file.filename == '' or not allowed_file(file.filename): return redirect(url_for('index'))
    original_filename = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)
    file.save(save_path)
    print(f"File '{original_filename}' uploaded. Starting background conversion.")
    conversion_thread = threading.Thread(target=convert_to_mp3, args=(save_path,))
    conversion_thread.start()
    return redirect(url_for('index'))

# --- NEW: Route for deleting files ---
@app.route('/delete', methods=['POST'])
def delete_file():
    # Get the filename from the form
    file_to_delete = request.form['filename']
    # Sanitize the filename to prevent security issues
    filename = secure_filename(file_to_delete)
    
    # Construct the full, safe path
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Check if the file exists and delete it
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"Deleted file: {filename}")
        except Exception as e:
            print(f"Error deleting file {filename}: {e}")
    else:
        print(f"Attempted to delete non-existent file: {filename}")
        
    # Redirect back to the main page to see the updated list
    return redirect(url_for('index'))

# --- Main Execution (Unchanged) ---
if __name__ == '__main__':
    try:
        setup_fm_transmitter()
        print("Starting static loop...")
        pygame.mixer.Channel(0).play(static_sound_object, -1)
        print(f"Flask server running. Access at http://<your_pi_ip>:5000")
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        GPIO.cleanup()
