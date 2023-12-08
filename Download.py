import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtGui import QFont, QIcon, QPixmap
from PyQt5.QtCore import QThread, Qt, pyqtSignal, QTimer
from pytube import YouTube
import ffmpeg
import os
import glob
import time
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM
import re

# 定义常量
VIDEO_FILE_PATTERN = 'vid*.mp4'
AUDIO_FILE_PATTERN = 'aud*.mp4'
WEBM_FILE_PATTERN = 'vid*.webm'
VIDEO_FILE_PREFIX = 'vid'
AUDIO_FILE_PREFIX = 'aud'

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)

    def __init__(self, vlink):
        super().__init__()
        self.vlink = vlink
        self.stopped = False  # 标志是否停止下载
        self.downloaded_files = []  # 存储已下载文件名的列表


    def download_and_concatenate(self, v, video_stream, audio_stream, title):
        # 添加时间戳到输出文件名
        timestamp = time.strftime("%Y%m%d%H%M%S")
        # 源音频
        audio_output_path = f'{timestamp}{AUDIO_FILE_PREFIX}_{title}.mp4'
        # 源视频
        webm_output_path = f'{timestamp}{VIDEO_FILE_PREFIX}_{title}.webm'
        # 合成视频
        video_output_path = f'{timestamp}_{title}.mp4'

        self.downloaded_files.extend([webm_output_path])
        vid_path = video_stream.download(filename_prefix=f'{timestamp}{VIDEO_FILE_PREFIX}_')
        self.downloaded_files.extend([audio_output_path])
        aud_path = audio_stream.download(filename_prefix=f'{timestamp}{AUDIO_FILE_PREFIX}_')

        # 检查是否应该停止下载
        if self.stopped:
            self.delete_files(self.downloaded_files)
            self.update_signal.emit('下载已终止！')
            return
        vid = ffmpeg.input(vid_path)
        aud = ffmpeg.input(aud_path)
        self.downloaded_files.extend([video_output_path])
        ffmpeg.concat(vid, aud, v=1, a=1).output(video_output_path).run()

        # 删除源视频和音频文件
        self.delete_files([audio_output_path,webm_output_path])
        self.update_signal.emit('下载完成！')

    def download(self):
        try:
            v = YouTube(self.vlink)

            video_stream = v.streams.filter(adaptive=True).first()
            audio_stream = v.streams.get_audio_only()

            # 并行下载视频和音频
            self.download_and_concatenate(v, video_stream, audio_stream, v.title)

        except Exception as e:
            self.update_signal.emit(f'发生错误: {str(e)}')

    def delete_files(self, filenames):
        for filename in filenames:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception as e:
                    print(f'删除文件时出错 {filename}: {e}')
            else:
                print(f'文件不存在: {filename}')


    def stop_download(self):
        self.delete_files(self.downloaded_files)
        for filename in self.downloaded_files:
            print(filename)
        self.stopped = True

    def run(self):
        self.download()

class VideoDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Youtube - 高质量视频下载器')
        self.setFixedSize(600, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        # 从SVG设置自定义图标
        icon_path = './youtube.svg'
        self.setWindowIcon(self.create_icon_from_svg(icon_path))

        main_layout = QVBoxLayout()

        input_layout = QHBoxLayout()

        label = QLabel('视频链接:')
        label.setFont(QFont('楷体', 16, QFont.Bold))
        input_layout.addWidget(label)

        self.link_line_edit = QLineEdit()
        self.link_line_edit.setFont(QFont('楷体', 14))
        input_layout.addWidget(self.link_line_edit)

        main_layout.addLayout(input_layout)

        self.download_button = QPushButton('下载')
        self.download_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: 1px solid #4CAF50;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 16px;
                font-family: 楷体;
            }
            QPushButton:disabled {
                background-color: #aaaaaa;
                color: #555555;
                border: 1px solid #aaaaaa;
            }
            """
        )
        self.download_button.clicked.connect(self.start_download)

        main_layout.addWidget(self.download_button)

        self.setLayout(main_layout)

        self.download_thread = None
        self.downloading = False
        self.download_counter = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_button_text)

    def start_download(self):
        vlink = self.link_line_edit.text()
        if vlink and not self.downloading:
            if self.is_valid_youtube_link(vlink):
                self.downloading = True
                self.download_button.setEnabled(False)
                self.link_line_edit.setEnabled(False)

                self.download_thread = DownloadThread(vlink)
                self.download_thread.finished.connect(self.download_complete)
                self.download_thread.update_signal.connect(self.update_status)
                self.download_thread.start()

                self.timer.start(500)

            else:
                QMessageBox.warning(self, '错误', '请输入有效的YouTube视频链接！')

    def is_valid_youtube_link(self, link):
            youtube_regex = (
                r'(https?://)?(www\.)?'
                '(youtube|youtu|youtube-nocookie)\.(com|be)/'
                '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')

            youtube_match = re.match(youtube_regex, link)
            return youtube_match is not None

    def download_complete(self):
        self.downloading = False
        self.download_button.setEnabled(True)
        self.link_line_edit.setEnabled(True)
        self.timer.stop()

    def update_status(self, message):
        self.download_button.setText(message)
        if "合并完成" in message:
            title = self.link_line_edit.text().split("v=")[1]
            QMessageBox.information(self, '提示', message)
            
            # 使用记录的文件名删除已下载的文件
            self.delete_files(self.download_thread.downloaded_files, title)

    def update_button_text(self):
        dots = ['.', '..', '...']
        self.download_button.setText(f'正在下载{dots[self.download_counter % 3]}')
        self.download_counter += 1

    def delete_files(self, files, title):
        delete = [x for x in files if title not in x]

        for filename in delete:
            try:
                os.remove(filename)
            except Exception as e:
                print(f'删除文件时出错 {filename}: {e}')

    def closeEvent(self, event):
        if self.downloading:
            reply = QMessageBox.question(self, '提示', '下载正在进行中，是否终止下载并关闭应用？',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.download_thread:
                    self.download_thread.stop_download()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    @staticmethod
    def create_icon_from_svg(svg_path):
        drawing = svg2rlg(svg_path)
        image = renderPM.drawToPIL(drawing)

        image.save("temp.png")
        pixmap = QPixmap("temp.png")

        os.remove("temp.png")

        icon = QIcon(pixmap)
        return icon

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoDownloader()

    window.link_line_edit.setText("https://www.youtube.com/watch?v=QdBZY2fkU-0")

    window.show()
    sys.exit(app.exec_())
