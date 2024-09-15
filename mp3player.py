import sys
import os
import json
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QListWidget, QFileDialog, 
                             QSlider, QLabel, QStyle)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import pygame
import pyaudio
import struct
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

class SpectrumAnalyzer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 2), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        self.ax = self.figure.add_subplot(111)
        self.line, = self.ax.plot([], [])
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, CHUNK)
        self.ax.set_title('Audio Spectrum')
        self.ax.set_xlabel('Frequency')
        self.ax.set_ylabel('Amplitude (dB)')

    def update_plot(self, data):
        self.line.set_data(range(len(data)), data)
        self.ax.set_xlim(0, len(data))
        self.canvas.draw()

class MP3Player(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enhanced MP3 Player with Spectrum Analyzer")
        self.setGeometry(100, 100, 800, 600)

        self.config = self.load_config()
        self.songs = []
        self.current_song = None
        self.current_index = -1
        self.is_playing = False
        self.current_song_length = 0
        self.last_known_position = 0

        pygame.mixer.init()

        self.init_ui()
        self.load_songs()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_position)
        self.timer.start(1000)

        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  input=True,
                                  frames_per_buffer=CHUNK)

        self.spectrum_timer = QTimer(self)
        self.spectrum_timer.timeout.connect(self.update_spectrum)
        self.spectrum_timer.start(50)

        # Set up event to check for song end
        SONG_END = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(SONG_END)

        # Timer to check for song end
        self.end_timer = QTimer(self)
        self.end_timer.timeout.connect(self.check_song_end)
        self.end_timer.start(500)  # Check every 500ms

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        # Song list
        self.song_list = QListWidget()
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)
        layout.addWidget(self.song_list)

        # Spectrum Analyzer
        self.spectrum_analyzer = SpectrumAnalyzer()
        layout.addWidget(self.spectrum_analyzer)

        # Playback position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 100)
        self.position_slider.sliderReleased.connect(self.seek_position)
        layout.addWidget(self.position_slider)

        # Time labels
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("0:00")
        self.total_time_label = QLabel("0:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time_label)
        layout.addLayout(time_layout)

        # Playback control buttons
        control_layout = QHBoxLayout()
        
        self.previous_button = QPushButton()
        self.previous_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.previous_button.clicked.connect(self.previous_song)
        control_layout.addWidget(self.previous_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.clicked.connect(self.play_pause)
        control_layout.addWidget(self.play_button)

        self.next_button = QPushButton()
        self.next_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.next_button.clicked.connect(self.next_song)
        control_layout.addWidget(self.next_button)

        layout.addLayout(control_layout)

        # Folder selection button
        self.select_folder_button = QPushButton("Select Folder")
        self.select_folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_folder_button)

        central_widget.setLayout(layout)

    def update_spectrum(self):
        if pygame.mixer.music.get_busy():
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                actual_chunk_size = len(data) // 2  # Each sample is 2 bytes
                data_int = struct.unpack(f'{actual_chunk_size}h', data)
                data_np = np.array(data_int, dtype='h')
                
                # Perform FFT and get the magnitude spectrum
                fft_data = np.fft.fft(data_np)
                magnitude_spectrum = np.abs(fft_data[:actual_chunk_size // 2])
                
                # Convert to decibels
                magnitude_spectrum = 20 * np.log10(magnitude_spectrum + 1e-10)
                
                # Normalize
                magnitude_spectrum = np.clip(magnitude_spectrum, 0, 100)
                
                self.spectrum_analyzer.update_plot(magnitude_spectrum)
                
                print(f"Processed chunk size: {actual_chunk_size}")
            except struct.error as e:
                print(f"Struct error: {e}")
                print(f"Received data length: {len(data)} bytes")
            except Exception as e:
                print(f"Error updating spectrum: {e}")

    def load_config(self):
        try:
            with open("config.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {"folder": "."}

    def save_config(self):
        with open("config.json", "w") as file:
            json.dump(self.config, file)

    def load_songs(self):
        self.songs = []
        self.song_list.clear()
        for file in os.listdir(self.config["folder"]):
            if file.endswith(".mp3"):
                full_path = os.path.join(self.config["folder"], file)
                try:
                    audio = MP3(full_path, ID3=ID3)
                    title = audio.get('TIT2', file)
                    track_num = audio.get('TRCK', (0,))
                    if isinstance(track_num, tuple):
                        track_num = track_num[0]
                    self.songs.append({
                        'filename': file,
                        'title': str(title),
                        'track': int(str(track_num).split('/')[0]) if track_num else 0
                    })
                except:
                    self.songs.append({
                        'filename': file,
                        'title': file,
                        'track': 0
                    })
        
        # Sort songs based on track number or filename
        self.songs.sort(key=lambda x: (x['track'], x['filename']))
        
        for song in self.songs:
            self.song_list.addItem(song['title'])

    def play_selected_song(self, item):
        self.current_index = self.song_list.row(item)
        self.play_song()

    def play_pause(self):
        if not self.is_playing:
            if self.current_song:
                self.play_song(resume=True)
            elif self.songs:
                self.current_index = 0
                self.play_song()
        else:
            pygame.mixer.music.pause()
            self.is_playing = False
        self.update_play_button()

    def play_song(self, resume=False):
        if 0 <= self.current_index < len(self.songs):
            self.current_song = os.path.join(self.config["folder"], self.songs[self.current_index]['filename'])
            try:
                if not resume:
                    pygame.mixer.music.load(self.current_song)
                    self.current_song_length = MP3(self.current_song).info.length
                    self.last_known_position = 0
                pygame.mixer.music.play(start=self.last_known_position)
                self.is_playing = True
                self.update_play_button()
                self.update_song_info()
                print(f"Playing song from position: {self.last_known_position:.2f} seconds")
            except Exception as e:
                print(f"Error playing song: {e}")
                self.is_playing = False

    def check_song_end(self):
        if self.is_playing and not pygame.mixer.music.get_busy():
          self.next_song()

    def seek_position(self):
        if self.current_song and self.current_song_length > 0:
            percentage = self.position_slider.value()
            new_position = (percentage / 100) * self.current_song_length
            
            print(f"Seeking to position: {new_position:.2f} seconds")
            
            # Stop the current playback
            pygame.mixer.music.stop()
            
            # Start playing from the new position
            pygame.mixer.music.play(start=new_position)
            self.last_known_position = new_position
            self.is_playing = True
            self.update_play_button()

    def update_play_button(self):
        icon = QStyle.StandardPixmap.SP_MediaPause if self.is_playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def update_position(self):
        if self.current_song and self.is_playing:
            try:
                current_time = pygame.mixer.music.get_pos() / 1000  # get_pos() returns milliseconds
                if current_time < 0:  # get_pos() returns -1 if the music has stopped
                    self.is_playing = False
                    self.update_play_button()
                    return
                
                current_time += self.last_known_position
                percentage = (current_time / self.current_song_length) * 100
                self.position_slider.setValue(int(percentage))
                self.current_time_label.setText(self.format_time(current_time))
                self.total_time_label.setText(self.format_time(self.current_song_length))
                print(f"Current position: {current_time:.2f} seconds, Percentage: {percentage:.2f}%")
            except Exception as e:
                print(f"Error updating position: {e}")

    def update_song_info(self):
        if self.current_song:
            self.current_song_length = MP3(self.current_song).info.length
            self.total_time_label.setText(self.format_time(self.current_song_length))
            print(f"Song length: {self.current_song_length:.2f} seconds")

    def stop(self):
        pygame.mixer.music.stop()
        self.update_play_button()

    def next_song(self):
        if self.songs:
            self.current_index = (self.current_index + 1) % len(self.songs)
            self.play_song()

    def previous_song(self):
        if self.songs:
            self.current_index = (self.current_index - 1) % len(self.songs)
            self.play_song()

    def set_volume(self, value):
        pygame.mixer.music.set_volume(value / 100)
        self.volume_label.setText(f"{value}%")

    def set_position_after_start(self, new_pos):
        try:
            pygame.mixer.music.set_pos(new_pos)
        except Exception as e:
            print(f"Error setting position after start: {e}")

    def apply_queued_seek(self):
        if self.queued_seek_position is not None and self.is_playing:
            try:
                duration = MP3(self.current_song).info.length
                new_pos = self.queued_seek_position * duration / 1000
                pygame.mixer.music.set_pos(new_pos)
                print(f"Seeking to position: {new_pos:.2f} seconds")
            except Exception as e:
                print(f"Error setting position: {e}")
            self.queued_seek_position = None

    def format_time(self, seconds):
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes}:{seconds:02d}"

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.config["folder"] = folder
            self.save_config()
            self.load_songs()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = MP3Player()
    player.show()
    sys.exit(app.exec())