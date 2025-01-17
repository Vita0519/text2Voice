import sys
import asyncio
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QTextEdit, QPushButton, QComboBox, 
                              QLabel, QSpinBox, QMessageBox, QFileDialog,QSystemTrayIcon, QSlider)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon, QColor
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
    
    def __init__(self, text, voice, rate, volume, filename):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.filename = filename
        self.is_cancelled = False
        self._loop = None  # 添加事件循环引用

    def run(self):
        try:
            async def tts_task():
                communicate = Communicate(self.text, self.voice, rate=self.rate, volume=self.volume)
                await communicate.save(self.filename)

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            if not self.is_cancelled:
                self._loop.run_until_complete(tts_task())
                self.finished.emit(True)
        except Exception as e:
            print(f"转换错误: {str(e)}")
            self.finished.emit(False)
        finally:
            if self._loop:
                self._loop.close()
                self._loop = None

    def cancel(self):
        """取消转换"""
        self.is_cancelled = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

class TTSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文本转语音")
        self.setMinimumSize(600, 400)
        
        # 设置窗口样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QWidget {
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }
            QTextEdit {
                background-color: white;
                border: none;
                border-radius: 16px;
                padding: 20px;
                font-size: 14px;
                selection-background-color: #0A84FF;
                color: #333333;
                line-height: 1.6;
            }
            QTextEdit:focus {
                outline: none;
                border: 2px solid rgba(0, 122, 255, 0.2);
            }
            QComboBox {
                background-color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 15px;
                min-width: 200px;
                color: #333333;
                font-size: 14px;
            }
            QComboBox:hover {
                background-color: #f8f9fa;
            }
            QComboBox:focus {
                border: 1px solid #007AFF;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
            }
            QSpinBox {
                background-color: white;
                border: none;
                border-radius: 10px;
                padding: 10px;
                min-width: 120px;
                color: #333333;
                font-size: 14px;
            }
            QSpinBox:hover {
                background-color: #f8f9fa;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                border: none;
                background-color: transparent;
                width: 16px;
            }
            QLabel {
                color: #1d1d1f;
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 6px;
            }
            QWidget#controlsWidget {
                background-color: white;
                border-radius: 16px;
            }
            QWidget#textContainer {
                background-color: white;
                border-radius: 16px;
            }
        """)
        
        # 创建主窗口部件和布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 初始化其他组件
        self.setup_ui(layout)
        
        # 设置默认输出路径
        self.output_path = "output.mp3"
        
        # 初始化状态和播放器
        self.is_playing = False
        self.is_paused = False
        self.tts_thread = None
        self.setup_media_player()
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.is_converting = False  # 添加转换状态标记
        
        # 添加状态保护锁
        self.is_busy = False
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(QIcon(':/icons/main.ico'))
        self.tray_icon.setToolTip("TTS文本转语音")
        self.tray_icon.show()
        
    def safe_state_change(self, action):
        """安全的状态切换装饰器"""
        if self.is_busy:
            return
        self.is_busy = True
        try:
            action()
        finally:
            self.is_busy = False

    def setup_ui(self, layout):
        # 文本输入区
        text_container = QWidget()
        text_container.setObjectName("textContainer")
        text_container.setStyleSheet("""
            QWidget#textContainer {
                background-color: white;
                border-radius: 16px;
                border: 1px solid rgba(0, 0, 0, 0.08);
            }
        """)
        
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(25, 25, 25, 25)
        text_layout.setSpacing(15)
        
        # 标题栏布局
        header_layout = QHBoxLayout()
        
        input_label = QLabel("输入文本")
        input_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #1d1d1f;
            }
        """)
        header_layout.addWidget(input_label)
        header_layout.addStretch()
        
        # 添加清除按钮
        self.clear_btn = CustomButton(":/icons/clear.svg", "清除文本", is_import=True)
        self.clear_btn.clicked.connect(self.clear_text)
        header_layout.addWidget(self.clear_btn)
        
        # 添加导入按钮
        self.import_btn = CustomButton(":/icons/import.svg", "导入文本文件", is_import=True)
        self.import_btn.clicked.connect(self.import_text)
        header_layout.addWidget(self.import_btn)
        
        text_layout.addLayout(header_layout)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("请输入要转换的文本...")
        self.text_edit.setMinimumHeight(200)
        text_layout.addWidget(self.text_edit)
        
        layout.addWidget(text_container)

        # 控制面板
        controls_widget = QWidget()
        controls_widget.setObjectName("controlsWidget")
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(20, 15, 20, 15)
        controls_layout.setSpacing(15)

        # 左侧控制组
        left_controls = QHBoxLayout()
        left_controls.setSpacing(15)

        # 语音选择（去掉标签）
        self.voice_combo = QComboBox()
        self.setup_voice_options()
        self.voice_combo.currentIndexChanged.connect(self.on_voice_changed)
        self.voice_combo.setFixedWidth(150)
        left_controls.addWidget(self.voice_combo)

        # 语速滑块布局
        rate_layout = QHBoxLayout()
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(10)
        self.rate_slider.setFixedWidth(100)
        self.rate_slider.setToolTip("调节语音速度")
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        
        self.rate_label = QLabel("10%")
        self.rate_label.setFixedWidth(40)
        self.rate_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 12px;
                padding: 0 5px;
            }
        """)
        
        rate_layout.addWidget(self.rate_slider)
        rate_layout.addWidget(self.rate_label)
        left_controls.addLayout(rate_layout)

        # 音量滑块布局
        volume_layout = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(-100, 100)
        self.volume_slider.setValue(10)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setToolTip("调节语音音量")
        self.volume_slider.valueChanged.connect(self.update_volume_label)
        
        self.volume_label = QLabel("10%")
        self.volume_label.setFixedWidth(40)
        self.volume_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 12px;
                padding: 0 5px;
            }
        """)
        
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_label)
        left_controls.addLayout(volume_layout)

        controls_layout.addLayout(left_controls)
        controls_layout.addStretch()

        # 按钮组（更紧凑的布局）
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        # 调整按钮大小
        button_size = 40
        
        self.convert_btn = CustomButton(":/icons/convert.svg", "转换为语音", button_size=button_size)
        self.convert_btn.clicked.connect(self.start_conversion)
        
        self.play_btn = CustomButton(":/icons/play.svg", "播放", button_size=button_size)
        self.play_btn.clicked.connect(self.play_audio)
        
        self.pause_btn = CustomButton(":/icons/pause.svg", "暂停", button_size=button_size)
        self.pause_btn.clicked.connect(self.pause_audio)
        
        button_layout.addWidget(self.convert_btn)
        button_layout.addWidget(self.play_btn)
        button_layout.addWidget(self.pause_btn)
        
        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_widget)
        
         # 创建一个 QLabel 并设置其文本为 HTML 格式，包含一个可点击的链接
        self.about_label = QLabel(
            '<p><a href="https://www.allfather.top">愿代码流畅无阻，愿调试轻松自如</a></p>',
            self
        )
        # self.about_label.setStyleSheet("background: lightblue")
        self.about_label.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        self.about_label.setOpenExternalLinks(True)  # 允许 QLabel 中的链接被点击跳转
        # 将 QLabel 添加到布局中
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

    def on_voice_changed(self):
        """当选择新的声音时，重置播放状态"""
        def _change():
            # 如果正在转换，取消当前转换
            if self.is_converting:
                self.cancel_conversion()
                
            # 如果正在播放，先停止播放
            if self.is_playing or self.is_paused:
                self.stop_audio()
            
            self.play_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            
            if self.text_edit.toPlainText():
                self.convert_btn.setEnabled(True)

        self.safe_state_change(_change)

    def play_audio(self):
        """播放音频"""
        def _play():
            if not os.path.exists(self.output_path):
                QMessageBox.warning(self, "错误", "音频文件不存在！")
                return

            if not self.is_playing:
                if self.is_paused:
                    self.player.play()
                else:
                    file_path = QUrl.fromLocalFile(os.path.abspath(self.output_path))
                    self.player.setSource(file_path)
                    self.player.play()
                
                self.is_playing = True
                self.is_paused = False
                self.play_btn.setEnabled(False)
                self.pause_btn.setEnabled(True)

        self.safe_state_change(_play)

    def pause_audio(self):
        """暂停音频"""
        def _pause():
            if self.is_playing:
                self.player.pause()
                self.is_playing = False
                self.is_paused = True
                self.play_btn.setEnabled(True)
                self.pause_btn.setEnabled(False)

        self.safe_state_change(_pause)

    def stop_audio(self):
        """停止音频播放"""
        def _stop():
            self.player.stop()
            self.player.setSource(QUrl())
            self.is_playing = False
            self.is_paused = False
            self.play_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)

        self.safe_state_change(_stop)

    def on_playback_state_changed(self, state):
        """处理播放器状态变化"""
        def _state_change():
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.is_playing = False
                self.is_paused = False
                self.play_btn.setEnabled(True)
                self.pause_btn.setEnabled(False)
            elif state == QMediaPlayer.PlaybackState.PlayingState:
                self.is_playing = True
                self.is_paused = False
                self.play_btn.setEnabled(False)
                self.pause_btn.setEnabled(True)
            elif state == QMediaPlayer.PlaybackState.PausedState:
                self.is_playing = False
                self.is_paused = True
                self.play_btn.setEnabled(True)
                self.pause_btn.setEnabled(False)

        self.safe_state_change(_state_change)

    def start_conversion(self):
        """开始转换"""
        def _convert():
            if self.is_converting:
                return

            text = self.text_edit.toPlainText()
            if not text:
                QMessageBox.warning(self, "警告", "请输入要转换的文本！")
                return

            # 如果正在播放或暂停，先停止
            if self.is_playing or self.is_paused:
                self.stop_audio()
            else:
                # 即使没在播放，也清除之前的播放源
                self.player.setSource(QUrl())

            self.is_converting = True
            self.convert_btn.setEnabled(False)
            self.convert_btn.setProperty("active", "true")
            self.convert_btn.style().unpolish(self.convert_btn)
            self.convert_btn.style().polish(self.convert_btn)
            self.play_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            
            # 禁用语音选择和文本编辑
            self.voice_combo.setEnabled(False)
            self.text_edit.setEnabled(False)

            voice = self.voice_combo.currentData()
            rate = f"{self.rate_slider.value():+d}%"
            volume = f"{self.volume_slider.value():+d}%"

            self.tts_thread = TTSThread(text, voice, rate, volume, self.output_path)
            self.tts_thread.finished.connect(self.on_conversion_finished)
            self.tts_thread.start()

        self.safe_state_change(_convert)

    def on_conversion_finished(self, success):
        """转换完成的处理"""
        def _finish():
            self.is_converting = False
            self.convert_btn.setEnabled(True)
            self.convert_btn.setProperty("active", "false")
            self.convert_btn.style().unpolish(self.convert_btn)
            self.convert_btn.style().polish(self.convert_btn)
            
            # 恢复语音选择和文本编辑
            self.voice_combo.setEnabled(True)
            self.text_edit.setEnabled(True)
            
            if success:
                if os.path.exists(self.output_path):
                    self.play_btn.setEnabled(True)
                    self.pause_btn.setEnabled(False)
                    # 使用 QTimer 延迟一小段时间后播放
                    QTimer.singleShot(100, self.play_audio)
            else:
                QMessageBox.warning(self, "错误", "转换失败，请检查网络连接或稍后重试！")

        self.safe_state_change(_finish)

    def import_text(self):
        """导入文本文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文本文件",
            "",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
                    self.text_edit.setText(text)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法读取文件：{str(e)}")

    def setup_media_player(self):
        """初始化媒体播放器"""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)

    def clear_text(self):
        """清除文本"""
        self.text_edit.clear()

    def update_rate_label(self, value):
        """更新语速标签"""
        self.rate_label.setText(f"{value}%")

    def update_volume_label(self, value):
        """更新音量标签"""
        self.volume_label.setText(f"{value}%")

    def cancel_conversion(self):
        """取消当前转换"""
        if self.tts_thread and self.is_converting:
            self.tts_thread.cancel()
            self.tts_thread.quit()
            
            # 使用定时器来检查线程是否结束
            check_timer = QTimer()
            check_timer.setSingleShot(True)
            check_timer.timeout.connect(lambda: self.force_stop_thread(check_timer))
            check_timer.start(200)  # 200ms后检查
            
            # 立即恢复界面状态
            self.restore_ui_state()

    def force_stop_thread(self, timer):
        """强制停止线程"""
        if self.tts_thread and self.tts_thread.isRunning():
            self.tts_thread.terminate()
            self.tts_thread.wait(100)
        timer.stop()

    def restore_ui_state(self):
        """恢复界面状态"""
        self.is_converting = False
        self.convert_btn.setEnabled(True)
        self.convert_btn.setProperty("active", "false")
        self.convert_btn.style().unpolish(self.convert_btn)
        self.convert_btn.style().polish(self.convert_btn)
        self.voice_combo.setEnabled(True)
        self.text_edit.setEnabled(True)

    def closeEvent(self, event):
        """窗口关闭时的处理"""
        def _close():
            # 如果正在转换，取消转换
            if self.is_converting:
                self.cancel_conversion()
            
            # 停止播放
            if self.is_playing or self.is_paused:
                self.stop_audio()
            
            # 关闭系统托盘图标
            if hasattr(self, 'tray_icon'):
                self.tray_icon.hide()
            
            # 确保应用退出
            QApplication.quit()
        
        self.safe_state_change(_close)
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(":/icons/main.ico"))  # 设置任务栏图标
    window = TTSWindow()
    window.show()
    sys.exit(app.exec()) 
    
    # 打包
    # pyside6-rcc resources.qrc -o resources_rc.py                                     
    # pyarmor gen TTS_GUI.py resources_rc.py    
    # cd dist
    #pyinstaller --upx-dir "D:\upx" --clean --onefile --hidden-import DrissionPage --hidden-import PySide6.QtWidgets --hidden-import PySide6.QtCore --hidden-import edge_tts --hidden-import PySide6.QtMultimedia --add-data "pyarmor_runtime_000000;." --add-data "resources_rc.py;."  --name=text2Voice --icon=main.ico --windowed --strip .\TTS_GUI.py