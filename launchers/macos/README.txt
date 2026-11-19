OpenVINO Studio для macOS
=========================

1. Распакуйте архив целиком. Запускайте «OpenVINO Studio.app» из папки
   launchers/macos — рядом должна оставаться папка app.
   Не перетаскивайте один .app в «Программы»: он не найдёт файлы приложения.
2. Первый запуск: правый клик по приложению → «Открыть» → «Открыть».
   Это нужно, потому что приложение не подписано сертификатом Apple.
   Если macOS пишет «повреждено» или ничего не происходит, выполните в Терминале:
   xattr -dr com.apple.quarantine "/путь/к/OpenVINO Studio/launchers/macos/OpenVINO Studio.app"
3. Нужен Python 3.10–3.14 с python.org или Homebrew. Проверка: python3 --version.
4. Приложение работает локально и открывает интерфейс в браузере.
   Если окно не появилось, смотрите runtime/logs/bootstrap.log и macos-launcher.log.

Все данные хранятся рядом с папкой проекта (runtime/ и models/).
