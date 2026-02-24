# MetaMind C# (WPF redesign)

Полный визуальный слой перенесён на **C# WPF** с современной стилизацией (frameless, glow, toast, welcome-first-run), без вмешательства в существующую Python-техническую логику проекта.

## Что внутри
- `MainWindow.xaml` — новый premium UI.
- `MainWindow.xaml.cs` — first-run логика, анимации, hooks-кнопки (`Автоскан`, `Обновить мету`).
- `App.xaml` — глобальные стили и палитра.

## Требования
- Windows 10/11
- .NET SDK 8.0+

## Как запустить
```bash
cd MetaMindCSharp
dotnet restore
dotnet run
```

## Как собрать EXE
```bash
cd MetaMindCSharp
dotnet publish -c Release -r win-x64 --self-contained true /p:PublishSingleFile=true
```

Готовый EXE будет в папке:
`bin/Release/net8.0-windows/win-x64/publish/`

## Что не упущено
- First-run файл создаётся отдельно от версии: `%AppData%/MetaMind/first_run_flag.json`.
- Версия UI зафиксирована в окне как `v6.5`.
- Есть закрытие/сворачивание, навигация, toast, анимируемый прогресс скана, hooks под backend.

## Что подключить дальше (если нужно 1:1 с Python логикой)
- В `StartAutoScan` и `RefreshMeta` подключить реальную CV/GSI/OpenDota-логику через:
  1. gRPC/HTTP к Python-сервису, или
  2. прямой порт логики на C#.


## Если `dotnet run` "висит" в CMD
1. Сначала проверь SDK:
```bash
dotnet --info
```
2. Выполни restore/build отдельно (так видно, где именно стоп):
```bash
dotnet restore -v minimal
dotnet build -v minimal
```
3. Запусти с логом:
```bash
dotnet run -v minimal
```
4. Если процесс запустился, но окна нет — после этого обновления окно стартует через `StartupUri="MainWindow.xaml"` в `App.xaml`.
5. Если всё ещё тишина:
   - отключи первый запуск без NuGet-кеша: `dotnet nuget locals all --clear`
   - проверь, что папка проекта не в OneDrive/с ограничениями
   - попробуй `dotnet run --no-restore` после успешного `dotnet build`.
