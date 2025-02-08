import sys
import asyncio
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QTextEdit, QPushButton, QComboBox, 
                              QLabel, QSpinBox, QMessageBox, QFileDialog, QSystemTrayIcon, QSlider)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize, QTimer, QEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon
import resources_rc
from edge_tts import Communicate

class CustomButton(QPushButton):
    def __init__(self, icon_path, tooltip, parent=None, is_import=False, button_size=None):
        super().__init__(parent)
        self.setIcon(QIcon(icon_path))
        self.setToolTip(tooltip)
        
        size = button_size or (40 if is_import else 50)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(size * 0.5, size * 0.5))
        
        radius = size // 2
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #0A84FF;
                border: none;
                border-radius: {radius}px;
            }}
            QPushButton:hover {{
                background-color: #007AFF;
            }}
            QPushButton:pressed {{
                background-color: #0066CC;
            }}
            QPushButton:disabled {{
                background-color: #E5E5EA;
            }}
            QPushButton[active="true"] {{
                background-color: #FF3B30;
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)

class TTSThread(QThread):
    finished = Signal(bool)
    error = Signal(str)
    
    def __init__(self, text, voice, rate, volume, filename):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.filename = filename
        self.is_cancelled = False
        self._loop = None
        self.max_retries = 3

    def run(self):
        retries = 0
        while retries < self.max_retries:
            try:
                async def tts_task():
                    communicate = Communicate(self.text, self.voice, rate=self.rate, volume=self.volume)
                    await communicate.save(self.filename)

                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                
                if not self.is_cancelled:
                    self._loop.run_until_complete(tts_task())
                    self.finished.emit(True)
                    return
                    
            except Exception as e:
                error_msg = str(e)
                retries += 1
                if retries < self.max_retries:
                    print(f"转换失败，正在重试 ({retries}/{self.max_retries}): {error_msg}")
                    self.msleep(1000)  # 等待1秒后重试
                    continue
                else:
                    print(f"转换错误: {error_msg}")
                    self.error.emit(f"转换失败: {error_msg}")
                    self.finished.emit(False)
                    return
            finally:
                if self._loop:
                    self._loop.close()
                    self._loop = None

    def cancel(self):
        """取消转换"""
        self.is_cancelled = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

class AudioPlayThread(QThread):
    finished = Signal()
    error = Signal(str)
    
    def __init__(self, player):
        super().__init__()
        self.player = player
        self.is_cancelled = False
    
    def run(self):
        try:
            while not self.is_cancelled and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.msleep(100)  # 每100ms检查一次状态
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
    
    def cancel(self):
        self.is_cancelled = True

class TTSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文本转语音")
        self.setMinimumSize(800, 600)
        
        # 创建主窗口部件和布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 初始化状态
        self.is_playing = False
        self.is_paused = False
        self.is_converting = False
        self.is_busy = False
        self.tts_thread = None
        self.audio_thread = None
        self.output_path = "output.mp3"
        
        # 初始化UI
        self.setup_ui(layout)
        
        # 设置媒体播放器
        self.setup_media_player()
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(QIcon(':/icons/main.ico'))
        self.tray_icon.setToolTip("TTS文本转语音")
        self.tray_icon.show()

    def setup_ui(self, layout):
        # 文本输入区域
        text_container = QWidget()
        text_container.setObjectName("textContainer")
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(20, 20, 20, 20)
        text_layout.setSpacing(10)
        
        # 标题栏
        header_layout = QHBoxLayout()
        input_label = QLabel("输入文本")
        input_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_layout.addWidget(input_label)
        header_layout.addStretch()
        
        # 清除和导入按钮
        self.clear_btn = CustomButton(":/icons/clear.svg", "清除文本", is_import=True)
        self.clear_btn.clicked.connect(self.clear_text)
        self.import_btn = CustomButton(":/icons/import.svg", "导入文本文件", is_import=True)
        self.import_btn.clicked.connect(self.import_text)
        
        header_layout.addWidget(self.clear_btn)
        header_layout.addWidget(self.import_btn)
        text_layout.addLayout(header_layout)
        
        # 文本编辑区
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("请输入要转换的文本...")
        self.text_edit.setMinimumHeight(400)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                line-height: 1.6;
            }
            QTextEdit:focus {
                border: 1px solid rgba(10, 132, 255, 0.3);
                box-shadow: 0 0 5px rgba(10, 132, 255, 0.2);
            }
        """)
        self.text_edit.installEventFilter(self)
        text_layout.addWidget(self.text_edit)
        
        layout.addWidget(text_container, stretch=1)

        # 控制面板
        controls_widget = QWidget()
        controls_widget.setObjectName("controlsWidget")
        controls_widget.setFixedHeight(80)
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(20, 15, 20, 15)
        controls_layout.setSpacing(15)

        # 左侧控制组
        left_controls = QHBoxLayout()
        left_controls.setSpacing(15)

        # 语音选择
        self.voice_combo = QComboBox()
        self.setup_voice_options()
        self.voice_combo.setFixedWidth(150)
        left_controls.addWidget(self.voice_combo)

        # 语速控制
        rate_layout = QHBoxLayout()
        rate_label = QLabel("语速")
        rate_label.setFixedWidth(30)
        
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(10)
        self.rate_slider.setFixedWidth(80)
        
        self.rate_value_label = QLabel("10%")
        self.rate_value_label.setFixedWidth(35)
        
        rate_layout.addWidget(rate_label)
        rate_layout.addWidget(self.rate_slider)
        rate_layout.addWidget(self.rate_value_label)
        
        # 音量控制
        volume_layout = QHBoxLayout()
        volume_label = QLabel("音量")
        volume_label.setFixedWidth(30)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(80)
        
        self.volume_value_label = QLabel("70%")
        self.volume_value_label.setFixedWidth(35)
        
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_value_label)

        # 连接滑块信号
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        self.volume_slider.valueChanged.connect(self.update_volume_label)
        
        left_controls.addLayout(rate_layout)
        left_controls.addLayout(volume_layout)
        controls_layout.addLayout(left_controls)
        controls_layout.addStretch()

        # 按钮组
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.convert_btn = CustomButton(":/icons/convert.svg", "转换为语音", button_size=40)
        self.convert_btn.clicked.connect(self.start_conversion)
        
        self.play_btn = CustomButton(":/icons/play.svg", "播放", button_size=40)
        self.play_btn.clicked.connect(self.play_audio)
        self.play_btn.setEnabled(False)
        
        button_layout.addWidget(self.convert_btn)
        button_layout.addWidget(self.play_btn)
        
        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_widget)

        # 底部链接
        self.about_label = QLabel(
            '<p><a href="https://www.allfather.top">愿代码流畅无阻，愿调试轻松自如</a></p>'
        )
        self.about_label.setAlignment(Qt.AlignRight)
        self.about_label.setOpenExternalLinks(True)
        layout.addWidget(self.about_label)

    def setup_voice_options(self):
        voice_options = {
            '晓晓（女）': 'zh-CN-XiaoxiaoNeural',
            '云希（男）': 'zh-CN-YunxiNeural',
            '云扬（男）': 'zh-CN-YunyangNeural',
            '云健（男）': 'zh-CN-YunjianNeural',
            '晓忆（女）': 'zh-CN-XiaoyiNeural',
            '云霞（女）': 'zh-CN-YunxiaNeural',
            '晓北（女）': 'zh-CN-XiaobeiNeural',
            '晓曼（女，香港）': 'zh-HK-HiuMaanNeural',
            '云龙（男，香港）': 'zh-HK-WanLungNeural',
            '晓佳（女，香港）': 'zh-HK-HiuGaaiNeural',
            '晓晨（女，台湾）': 'zh-TW-HsiaoChenNeural',
            '云哲（男，台湾）': 'zh-TW-YunJheNeural',
            '晓宇（女，台湾）': 'zh-TW-HsiaoYuNeural'
        }
        for name, value in voice_options.items():
            self.voice_combo.addItem(name, value)

    def setup_media_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.volume_slider.value() / 100)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)

    def eventFilter(self, obj, event):
        if obj == self.text_edit and event.type() == QEvent.Type.KeyPress:
            if (event.key() == Qt.Key.Key_Return and 
                not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                if (self.text_edit.toPlainText().strip() and 
                    not self.is_converting and 
                    not self.is_busy):
                    self.start_conversion()
                    return True
        return super().eventFilter(obj, event)

    def update_rate_label(self, value):
        self.rate_value_label.setText(f"{value}%")

    def update_volume_label(self, value):
        self.volume_value_label.setText(f"{value}%")
        self.audio_output.setVolume(value / 100)

    def clear_text(self):
        self.text_edit.clear()

    def import_text(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文本文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    self.text_edit.setText(file.read())
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法读取文件：{str(e)}")

    def start_conversion(self):
        if self.is_converting:
            return

        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "警告", "请输入要转换的文本！")
            return

        try:
            # 停止当前播放
            self.stop_audio()
            QApplication.processEvents()

            # 更新状态和UI
            self.is_converting = True
            self.convert_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.text_edit.setEnabled(False)
            self.voice_combo.setEnabled(False)

            # 创建转换线程
            voice = self.voice_combo.currentData()
            rate = f"{self.rate_slider.value():+d}%"
            volume = f"{self.volume_slider.value():+d}%"

            self.tts_thread = TTSThread(text, voice, rate, volume, self.output_path)
            self.tts_thread.finished.connect(self.on_conversion_finished)
            self.tts_thread.error.connect(self.on_conversion_error)
            self.tts_thread.start()

        except Exception as e:
            self.on_conversion_error(str(e))

    def on_conversion_finished(self, success):
        self.is_converting = False
        self.convert_btn.setEnabled(True)
        self.text_edit.setEnabled(True)
        self.voice_combo.setEnabled(True)

        if success and os.path.exists(self.output_path):
            self.play_btn.setEnabled(True)
            QTimer.singleShot(100, self.play_audio)
        else:
            self.play_btn.setEnabled(False)
            QMessageBox.warning(self, "错误", "转换失败，请检查网络连接或稍后重试！")

    def on_conversion_error(self, error_msg):
        QMessageBox.warning(self, "错误", error_msg)
        self.is_converting = False
        self.convert_btn.setEnabled(True)
        self.text_edit.setEnabled(True)
        self.voice_combo.setEnabled(True)
        self.play_btn.setEnabled(False)

    def play_audio(self):
        if not os.path.exists(self.output_path):
            QMessageBox.warning(self, "错误", "音频文件不存在！")
            return

        try:
            if self.is_playing:
                self.pause_audio()
                return

            if self.is_paused:
                self.player.play()
            else:
                self.player.setSource(QUrl.fromLocalFile(os.path.abspath(self.output_path)))
                self.player.play()

            self.is_playing = True
            self.is_paused = False
            self.play_btn.setIcon(QIcon(":/icons/pause.svg"))
            self.play_btn.setToolTip("暂停")

            # 启动音频监控线程
            self.start_audio_thread()

        except Exception as e:
            QMessageBox.warning(self, "错误", f"播放失败: {str(e)}")
            self.stop_audio()

    def pause_audio(self):
        if self.is_playing:
            self.player.pause()
            self.is_playing = False
            self.is_paused = True
            self.play_btn.setIcon(QIcon(":/icons/play.svg"))
            self.play_btn.setToolTip("继续播放")

    def stop_audio(self):
        try:
            # 停止音频监控线程
            if self.audio_thread and self.audio_thread.isRunning():
                self.audio_thread.cancel()
                self.audio_thread.wait()

            # 停止播放器
            self.player.stop()
            self.player.setSource(QUrl())
            
            # 重置状态
            self.is_playing = False
            self.is_paused = False
            self.play_btn.setIcon(QIcon(":/icons/play.svg"))
            self.play_btn.setToolTip("播放")
            
            QApplication.processEvents()
            
        except Exception as e:
            print(f"停止音频时出错: {str(e)}")

    def start_audio_thread(self):
        if self.audio_thread and self.audio_thread.isRunning():
            self.audio_thread.cancel()
            self.audio_thread.wait()
        
        self.audio_thread = AudioPlayThread(self.player)
        self.audio_thread.finished.connect(self.on_audio_finished)
        self.audio_thread.error.connect(self.on_audio_error)
        self.audio_thread.start()

    def on_audio_finished(self):
        self.is_playing = False
        self.is_paused = False
        self.play_btn.setIcon(QIcon(":/icons/play.svg"))
        self.play_btn.setToolTip("播放")

    def on_audio_error(self, error_msg):
        print(f"音频播放错误: {error_msg}")
        self.stop_audio()

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.is_playing = False
            self.is_paused = False
            self.play_btn.setIcon(QIcon(":/icons/play.svg"))
            self.play_btn.setToolTip("播放")

    def closeEvent(self, event):
        # 停止所有操作
        if self.is_converting and self.tts_thread:
            self.tts_thread.cancel()
            self.tts_thread.wait()
        
        self.stop_audio()
        
        # 关闭系统托盘图标
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(":/icons/main.ico"))
    window = TTSWindow()
    window.show()
    sys.exit(app.exec())