OpenVINO Studio для Linux
=========================

Быстрый запуск:
  ./launchers/linux/start-openvino-studio.sh

Добавить в меню приложений (один раз):
  ./launchers/linux/install-launcher.sh
После переноса папки ярлык нужно создать заново.

Требования:
• Python 3.10–3.14, пакеты python3-venv и python3-tk
  (Debian/Ubuntu: sudo apt install python3 python3-venv python3-tk).
• Для встроенного окна: Qt WebEngine ставится автоматически (PySide6).
  Нужны графические библиотеки: OpenGL и X11/Wayland
  (Debian/Ubuntu: sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0).
  На headless-сервере окно не откроется — будет сообщение с адресом.
• Интернет для установки OpenVINO и скачивания моделей.

Если окно не открылось автоматически, откройте адрес из
runtime/server.json вручную или смотрите runtime/logs/window.log.
