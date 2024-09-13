import sys
import os
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QListWidget, QFileDialog, 
                             QSlider, QLabel, QStyle)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from pygame import mixer
from mutagen.mp3 import MP3

class MP3Player(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enhanced MP3 Player")
        self.setGeometry(100, 100, 500, 400)

        self.config = self.load_config()
        self.songs = []
        self.current_song = None
        self.current_index = -1

        self.init_ui()
        self.load_songs()

        mixer.init()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_position)
        self.timer.start(1000)  # Update every second

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        # Song list
        self.song_list = QListWidget()
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)
        layout.addWidget(self.song_list)

        # Playback position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.sliderMoved.connect(self.set_position)
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

        self.stop_button = QPushButton()
        self.stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.clicked.connect(self.stop)
        control_layout.addWidget(self.stop_button)

        self.next_button = QPushButton()
        self.next_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.next_button.clicked.connect(self.next_song)
        control_layout.addWidget(self.next_button)

        layout.addLayout(control_layout)

        # Volume control
        volume_layout = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.valueChanged.connect(self.set_volume)
        
        self.volume_label = QLabel("50%")
        volume_layout.addWidget(QLabel("Volume:"))
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_label)
        
        layout.addLayout(volume_layout)

        # Folder selection button
        self.select_folder_button = QPushButton("Select Folder")
        self.select_folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_folder_button)

        central_widget.setLayout(layout)

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
                self.songs.append(file)
                self.song_list.addItem(file)

    def play_selected_song(self, item):
        self.current_index = self.song_list.row(item)
        self.play_song()

    def play_pause(self):
        if not mixer.music.get_busy():
            if self.current_song:
                mixer.music.unpause()
            elif self.songs:
                self.current_index = 0
                self.play_song()
        else:
            mixer.music.pause()
        self.update_play_button()

    def play_song(self):
        if 0 <= self.current_index < len(self.songs):
            self.current_song = os.path.join(self.config["folder"], self.songs[self.current_index])
            mixer.music.load(self.current_song)
            mixer.music.play()
            self.update_play_button()
            self.update_song_info()

    def update_play_button(self):
        icon = QStyle.StandardPixmap.SP_MediaPause if mixer.music.get_busy() else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def stop(self):
        mixer.music.stop()
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
        mixer.music.set_volume(value / 100)
        self.volume_label.setText(f"{value}%")

    def set_position(self, position):
        if self.current_song:
            duration = MP3(self.current_song).info.length
            mixer.music.set_pos(position * duration / 1000)

    def update_position(self):
        if self.current_song and mixer.music.get_busy():
            current_time = mixer.music.get_pos() / 1000
            total_time = MP3(self.current_song).info.length
            self.position_slider.setValue(int(current_time * 1000 / total_time))
            self.current_time_label.setText(self.format_time(current_time))
            self.total_time_label.setText(self.format_time(total_time))

    def update_song_info(self):
        if self.current_song:
            duration = MP3(self.current_song).info.length
            self.position_slider.setRange(0, int(duration * 1000))
            self.total_time_label.setText(self.format_time(duration))

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
