import sys
import os
import json
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QPushButton, QListWidget, QFileDialog,
                             QSlider, QLabel, QStyle, QTextEdit, QSpinBox)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import pygame.mixer
import pyaudio
import struct
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import librosa

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

class SpectrumAnalyzer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 2), dpi=100, facecolor='black')
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        self.ax = self.figure.add_subplot(111)
        
        self.line, = self.ax.plot([], [], color='#00FF00', linewidth=2)
        
        self.ax.set_facecolor('black')
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, CHUNK // 2)
        self.ax.set_title('Audio Spectrum', color='white')
        self.ax.set_xlabel('Frequency', color='white')
        self.ax.set_ylabel('Amplitude (dB)', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        
        self.canvas.draw()

    def update_plot(self, data):
        self.ax.clear()  # Clear the entire axes
        self.ax.set_facecolor('black')
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, CHUNK // 2)
        self.ax.set_title('Audio Spectrum', color='white')
        self.ax.set_xlabel('Frequency', color='white')
        self.ax.set_ylabel('Amplitude (dB)', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        
        self.ax.plot(range(len(data)), data, color='#00FF00', linewidth=2)
        self.canvas.draw()

class SpectrogramProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 2), dpi=100, facecolor='black')
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('black')
        self.ax.set_title('Song Spectrogram', color='white')
        self.ax.set_xlabel('Time', color='white')
        self.ax.set_ylabel('Frequency', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.progress_line = self.ax.axvline(x=0, color='r', linestyle='--')
        self.background = None
        self.canvas.draw()  # Draw once to set up the canvas

    def plot_spectrogram(self, y, sr):
        self.ax.clear()
        D = librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max)
        img = librosa.display.specshow(D, y_axis='linear', x_axis='time', sr=sr, ax=self.ax, cmap='viridis')
        self.figure.colorbar(img, ax=self.ax, format="%+2.0f dB")
        self.ax.set_title('Song Spectrogram', color='white')
        self.ax.set_xlabel('Time', color='white')
        self.ax.set_ylabel('Frequency', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.progress_line = self.ax.axvline(x=0, color='r', linestyle='--')
        self.canvas.draw()
        self.background = self.canvas.copy_from_bbox(self.ax.bbox)

    def update_progress(self, progress):
        if self.background is not None:
            self.canvas.restore_region(self.background)
            self.progress_line.set_xdata([progress, progress])
            self.ax.draw_artist(self.progress_line)
            self.canvas.blit(self.ax.bbox)
            self.canvas.flush_events()

class MetadataWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Song Metadata")
        self.setGeometry(200, 200, 400, 300)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        layout = QVBoxLayout()
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        layout.addWidget(self.metadata_text)
        
        self.central_widget.setLayout(layout)

    def update_metadata(self, metadata):
        self.metadata_text.clear()
        for key, value in metadata.items():
            self.metadata_text.append(f"{key}: {value}")

class AudioProcessorThread(QThread):
    spectrum_data_signal = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.audio_buffer = []
        self.buffer_size = 10  # Adjust buffer size as needed

    def run(self):
        if self.stream is None:
            self.stream = self.p.open(format=FORMAT,
                                      channels=CHANNELS,
                                      rate=RATE,
                                      input=True,
                                      frames_per_buffer=CHUNK)
        while True:
            data = self.stream.read(CHUNK, exception_on_overflow=False)
            data_int = struct.unpack(f'{CHUNK}h', data)
            self.audio_buffer.append(data_int)
            if len(self.audio_buffer) > self.buffer_size:
                self.audio_buffer.pop(0)
            self.process_audio_data(data_int)
            self.msleep(50)

    def process_audio_data(self, data_int):
        data_np = np.array(data_int, dtype='h')
        fft_data = np.fft.fft(data_np)
        magnitude_spectrum = np.abs(fft_data[:CHUNK // 2])
        magnitude_spectrum = 20 * np.log10(magnitude_spectrum + 1e-10)
        magnitude_spectrum = np.clip(magnitude_spectrum, 0, 100)
        self.spectrum_data_signal.emit(list(magnitude_spectrum))

class MP3Player(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Optimized MP3 Player with Spectrogram and Progress Slider")
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
        self.timer.start(100)  # Update more frequently

        self.audio_processor = AudioProcessorThread()
        self.audio_processor.spectrum_data_signal.connect(self.update_spectrum)
        self.audio_processor.start()

        self.end_timer = QTimer(self)
        self.end_timer.timeout.connect(self.check_song_end)
        self.end_timer.start(500)

        self.metadata_window = None

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        self.song_list = QListWidget()
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)
        layout.addWidget(self.song_list)

        self.spectrum_analyzer = SpectrumAnalyzer()
        layout.addWidget(self.spectrum_analyzer)

        self.spectrogram_progress = SpectrogramProgress()
        layout.addWidget(self.spectrogram_progress)

        # Add progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.sliderReleased.connect(self.seek_position)
        layout.addWidget(self.progress_slider)

        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("0:00")
        self.total_time_label = QLabel("0:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time_label)
        layout.addLayout(time_layout)

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

        # Shuffle Button
        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.clicked.connect(self.shuffle_playlist)
        control_layout.addWidget(self.shuffle_button)

        self.metadata_button = QPushButton("Show Metadata")
        self.metadata_button.clicked.connect(self.toggle_metadata_window)
        control_layout.addWidget(self.metadata_button)

        layout.addLayout(control_layout)

        # Volume control
        volume_layout = QHBoxLayout()
        self.volume_label = QLabel("Volume:")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)  # Default volume
        self.volume_slider.valueChanged.connect(self.set_volume)
        volume_layout.addWidget(self.volume_label)
        volume_layout.addWidget(self.volume_slider)
        layout.addLayout(volume_layout)

        self.select_folder_button = QPushButton("Select Folder")
        self.select_folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_folder_button)

        central_widget.setLayout(layout)

    def shuffle_playlist(self):
        random.shuffle(self.songs)
        self.song_list.clear()
        for song in self.songs:
            self.song_list.addItem(song['title'])

    def play_song(self, resume=False):
        if 0 <= self.current_index < len(self.songs):
            self.current_song = os.path.join(self.config["folder"], self.songs[self.current_index]['filename'])
            try:
                if not resume:
                    pygame.mixer.music.load(self.current_song)
                    self.current_song_length = MP3(self.current_song).info.length
                    self.last_known_position = 0
                    self.generate_spectrogram()
                pygame.mixer.music.play(start=self.last_known_position)
                self.is_playing = True
                self.update_play_button()
                self.update_song_info()
                self.update_metadata_window()
                print(f"Playing song from position: {self.last_known_position:.2f} seconds")
            except Exception as e:
                print(f"Error playing song: {e}")
                self.is_playing = False

    def seek_position(self):
        if self.current_song and self.current_song_length > 0:
            percentage = self.progress_slider.value()
            new_position = (percentage / 100) * self.current_song_length
            
            print(f"Seeking to position: {new_position:.2f} seconds")
            
            pygame.mixer.music.stop()
            pygame.mixer.music.play(start=new_position)
            self.last_known_position = new_position
            self.is_playing = True
            self.update_play_button()

    def update_spectrum(self):
        if pygame.mixer.music.get_busy():
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                data_int = struct.unpack(f'{CHUNK}h', data)
                data_np = np.array(data_int, dtype='h')
                
                fft_data = np.fft.fft(data_np)
                magnitude_spectrum = np.abs(fft_data[:CHUNK // 2])
                
                magnitude_spectrum = 20 * np.log10(magnitude_spectrum + 1e-10)
                magnitude_spectrum = np.clip(magnitude_spectrum, 0, 100)
                
                self.spectrum_analyzer.update_plot(magnitude_spectrum)
            except Exception as e:
                print(f"Error updating spectrum: {e}")

    def update_position(self):
        if self.current_song and self.is_playing:
            try:
                current_time = pygame.mixer.music.get_pos() / 1000
                if current_time < 0:
                    self.is_playing = False
                    self.update_play_button()
                    return
                
                current_time += self.last_known_position
                progress = current_time / self.current_song_length
                self.progress_slider.setValue(int(progress * 100))
                self.spectrogram_progress.update_progress(current_time)
                self.current_time_label.setText(self.format_time(current_time))
            except Exception as e:
                print(f"Error updating position: {e}")

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
                    self.generate_spectrogram()
                pygame.mixer.music.play(start=self.last_known_position)
                self.is_playing = True
                self.update_play_button()
                self.update_song_info()
                self.update_metadata_window()
                print(f"Playing song from position: {self.last_known_position:.2f} seconds")
            except Exception as e:
                print(f"Error playing song: {e}")
                self.is_playing = False

    def generate_spectrogram(self):
        if self.current_song:
            y, sr = librosa.load(self.current_song)
            self.spectrogram_progress.plot_spectrogram(y, sr)

    def check_song_end(self):
        if self.is_playing and not pygame.mixer.music.get_busy():
            self.next_song()

    def update_play_button(self):
        icon = QStyle.StandardPixmap.SP_MediaPause if self.is_playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def update_position(self):
        if self.current_song and self.is_playing:
            try:
                current_time = pygame.mixer.music.get_pos() / 1000
                if current_time < 0:
                    self.is_playing = False
                    self.update_play_button()
                    return
                
                current_time += self.last_known_position
                progress = current_time / self.current_song_length
                self.progress_slider.setValue(int(progress * 100))
                self.spectrogram_progress.update_progress(current_time)
                self.current_time_label.setText(self.format_time(current_time))
            except Exception as e:
                print(f"Error updating position: {e}")

    def update_spectrum(self):
        if pygame.mixer.music.get_busy():
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                data_int = struct.unpack(f'{CHUNK}h', data)
                data_np = np.array(data_int, dtype='h')
                
                fft_data = np.fft.fft(data_np)
                magnitude_spectrum = np.abs(fft_data[:CHUNK // 2])
                
                magnitude_spectrum = 20 * np.log10(magnitude_spectrum + 1e-10)
                magnitude_spectrum = np.clip(magnitude_spectrum, 0, 100)
                
                self.spectrum_analyzer.update_plot(magnitude_spectrum)
            except Exception as e:
                print(f"Error updating spectrum: {e}")

    def update_spectrum(self, data):
        self.spectrum_analyzer.update_plot(data)

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

    def format_time(self, seconds):
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes}:{seconds:02d}"

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.config["folder"] = folder
            self.save_config()
            self.load_songs()

    def toggle_metadata_window(self):
        if self.metadata_window is None:
            self.metadata_window = MetadataWindow()
            self.update_metadata_window()
            self.metadata_window.show()
        else:
            self.metadata_window.close()
            self.metadata_window = None

    def update_metadata_window(self):
        if self.metadata_window and self.current_song:
            try:
                audio = MP3(self.current_song, ID3=ID3)
                metadata = {
                    "Title": str(audio.get('TIT2', 'Unknown')),
                    "Artist": str(audio.get('TPE1', 'Unknown')),
                    "Album": str(audio.get('TALB', 'Unknown')),
                    "Year": str(audio.get('TDRC', 'Unknown')),
                    "Genre": str(audio.get('TCON', 'Unknown')),
                    "Track": str(audio.get('TRCK', 'Unknown')),
                    "Length": f"{audio.info.length:.2f} seconds",
                    "Bitrate": f"{audio.info.bitrate / 1000:.0f} kbps",
                    "Sample Rate": f"{audio.info.sample_rate} Hz",
                    "Channels": audio.info.channels
                }
                self.metadata_window.update_metadata(metadata)
            except Exception as e:
                print(f"Error updating metadata: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = MP3Player()
    player.show()
    sys.exit(app.exec())