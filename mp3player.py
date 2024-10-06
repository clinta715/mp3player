import sys
import json
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QListWidget, QFileDialog, 
                             QSlider, QLabel, QStyle)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.aac import AAC
from mutagen.oggvorbis import OggVorbis
from mutagen.ogg import OggFileType  # Use OggFileType for both Ogg Vorbis and Opus
from mutagen.aiff import AIFF
from mutagen.id3 import ID3
import pygame
import pyaudio
import struct
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import os
from PyQt6.QtWidgets import (QTableWidget, QTableWidgetItem, QHeaderView)

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

class SpectrumAnalyzer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set the widget's background color to black
        self.setStyleSheet("background-color: black;")
        
        self.figure = Figure(figsize=(5, 2), dpi=100)

        # Set the figure (canvas) background to black
        self.figure.patch.set_facecolor('black')

        self.canvas = FigureCanvas(self.figure)
        
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.ax = self.figure.add_subplot(111)

        # Set the plot area background to black and the line color to green
        self.ax.set_facecolor('black')
        self.line, = self.ax.plot([], [], color='lime')  # Green line

        # Set x and y axis limits
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, CHUNK)

        # Customize axis labels, ticks, and grid (optional)
        self.ax.tick_params(colors='lime')  # Tick labels in green
        self.ax.spines[:].set_color('lime')  # Axis edges in green
        self.ax.grid(False)  # No grid, but can enable if desired

    def update_plot(self, data):
        self.line.set_data(range(len(data)), data)
        self.ax.set_xlim(0, len(data))
        self.canvas.draw()

import random  # Import for shuffling the playlist

class MP3Player(QMainWindow):
    def __init__(self):
        # Keep existing initialization code...
        super().__init__()
        self.setWindowTitle("MP3 Player")
        self.setGeometry(100, 100, 800, 600)

        self.config = self.load_config()
        self.songs = []
        self.current_song = None
        self.current_index = -1
        self.is_playing = False
        self.current_song_length = 0
        self.last_known_position = 0
        
        # Add sorting tracking
        self.current_sort_column = 0
        self.current_sort_order = Qt.SortOrder.AscendingOrder

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

        # Replace song list with table
        self.song_table = QTableWidget()
        self.song_table.setColumnCount(4)
        self.song_table.setHorizontalHeaderLabels(['Track', 'Title', 'Filename', 'Path'])
        self.song_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.song_table.horizontalHeader().setSortIndicatorShown(True)
        self.song_table.horizontalHeader().sectionClicked.connect(self.sort_table)
        self.song_table.itemDoubleClicked.connect(self.play_selected_song)
        self.song_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.song_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.song_table.clicked.connect(self.on_cell_clicked)
        self.song_table.verticalHeader().setVisible(False)
        layout.addWidget(self.song_table)

        # Spectrum Analyzer
        self.spectrum_analyzer = SpectrumAnalyzer()
        layout.addWidget(self.spectrum_analyzer)

        # Create a horizontal layout for the toggle and shuffle buttons
        button_layout = QHBoxLayout()

        # Add the toggle button for spectrum analyzer
        self.toggle_spectrum_button = QPushButton("Hide Spectrum Analyzer")
        self.toggle_spectrum_button.clicked.connect(self.toggle_spectrum_analyzer)
        button_layout.addWidget(self.toggle_spectrum_button)

        # Add the shuffle playlist button
        self.shuffle_button = QPushButton("Shuffle Playlist")
        self.shuffle_button.clicked.connect(self.shuffle_playlist)
        button_layout.addWidget(self.shuffle_button)

        # Add the button layout to the main layout
        layout.addLayout(button_layout)

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

    def toggle_spectrum_analyzer(self):
        """Toggle the visibility of the spectrum analyzer."""
        if self.spectrum_analyzer.isVisible():
            self.spectrum_analyzer.setVisible(False)
            self.toggle_spectrum_button.setText("Show Spectrum Analyzer")
        else:
            self.spectrum_analyzer.setVisible(True)
            self.toggle_spectrum_button.setText("Hide Spectrum Analyzer")

    def shuffle_playlist(self):
        if self.song_table.rowCount() == 0:
            return
            
        # Remember current playing track path
        current_path = self.get_current_track_path()
        
        # Get all rows data
        rows_data = []
        for row in range(self.song_table.rowCount()):
            row_data = []
            for col in range(self.song_table.columnCount()):
                item = self.song_table.item(row, col)
                row_data.append(item.text() if item else "")
            rows_data.append(row_data)
        
        # Shuffle the rows
        random.shuffle(rows_data)
        
        # Clear and repopulate table
        self.song_table.setRowCount(0)
        for row_data in rows_data:
            row = self.song_table.rowCount()
            self.song_table.insertRow(row)
            for col, text in enumerate(row_data):
                self.song_table.setItem(row, col, QTableWidgetItem(text))
        
        # Update current track index to match new order
        if current_path:
            self.current_index = self.find_track_index(current_path)
            if self.current_index != -1:
                self.song_table.selectRow(self.current_index)

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
        self.song_table.setRowCount(0)

        supported_formats = {
            '.mp3': MP3,
            '.flac': FLAC,
            '.aac': AAC,
            '.m4a': AAC,
            '.ogg': OggFileType,
            '.opus': OggFileType,
            '.aiff': AIFF,
        }

        for root, dirs, files in os.walk(self.config["folder"]):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_formats:
                    full_path = os.path.join(root, file)
                    try:
                        audio = supported_formats[ext](full_path)
                        title = audio.get('TIT2', file)
                        track_num = audio.get('TRCK', (0,))
                        if isinstance(track_num, tuple):
                            track_num = track_num[0]
                        track = int(str(track_num).split('/')[0]) if track_num else 0
                        song_data = {
                            'filename': file,
                            'title': str(title),
                            'track': track,
                            'path': full_path  # Store full path
                        }
                        self.songs.append(song_data)
                    except Exception as e:
                        print(f"Error loading tags for {file}: {e}")
                        self.songs.append({
                            'filename': file,
                            'title': file,
                            'track': 0,
                            'path': full_path
                        })

        # Sort songs and populate table
        self.songs.sort(key=lambda x: (x['track'], x['filename']))
        self.update_table_display()


    def update_table_display(self):
        self.song_table.setRowCount(0)
        for song in self.songs:
            row = self.song_table.rowCount()
            self.song_table.insertRow(row)
            self.song_table.setItem(row, 0, QTableWidgetItem(f"{song['track']:02d}"))
            self.song_table.setItem(row, 1, QTableWidgetItem(song['title']))
            self.song_table.setItem(row, 2, QTableWidgetItem(song['filename']))
            self.song_table.setItem(row, 3, QTableWidgetItem(song['path']))
        
        # Hide the path column as it's just for internal use
        self.song_table.setColumnHidden(3, True)
        
    def sort_table(self, column):
        if self.current_sort_column == column:
            self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.current_sort_column = column
            self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        self.song_table.sortItems(column, self.current_sort_order)
        
        # Update current track index to match new order if a song is playing
        if self.current_index != -1:
            current_path = self.get_current_track_path()
            self.current_index = self.find_track_index(current_path)
            
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

    def get_current_track_path(self):
        if self.current_index != -1:
            return self.song_table.item(self.current_index, 3).text()
        return None

    def find_track_index(self, path):
        for row in range(self.song_table.rowCount()):
            if self.song_table.item(row, 3).text() == path:
                return row
        return -1

    def on_cell_clicked(self, index):
        self.song_table.selectRow(index.row())

    def play_selected_song(self, item):
        self.current_index = item.row()
        self.play_song()
        
    def play_song(self, resume=False):
        if 0 <= self.current_index < self.song_table.rowCount():
            self.current_song = self.song_table.item(self.current_index, 3).text()  # Get path from table
            try:
                if not resume:
                    pygame.mixer.music.load(self.current_song)
                    self.current_song_length = MP3(self.current_song).info.length
                    self.last_known_position = 0
                pygame.mixer.music.play(start=self.last_known_position)
                self.is_playing = True
                self.update_play_button()
                self.update_song_info()
                # Ensure the current song is visible and selected in the table
                self.song_table.selectRow(self.current_index)
                self.song_table.scrollToItem(self.song_table.item(self.current_index, 0))
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