using System;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace MetaMind;

public partial class MainWindow : Window
{
    private const string AppVersion = "6.5";
    private static readonly string AppDataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "MetaMind");
    private static readonly string FirstRunFile = Path.Combine(AppDataDir, "first_run_flag.json");

    private readonly DispatcherTimer _scanTimer;
    private readonly Random _rng = new();

    public MainWindow()
    {
        InitializeComponent();
        Directory.CreateDirectory(AppDataDir);

        _scanTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(120) };
        _scanTimer.Tick += (_, _) =>
        {
            ScanProgress.Value = Math.Min(100, ScanProgress.Value + _rng.Next(1, 6));
            if (ScanProgress.Value >= 100)
            {
                _scanTimer.Stop();
                StatusText.Text = "Сканирование завершено";
                ShowToast("Сканирование завершено");
            }
        };

        if (IsFirstRun())
        {
            MessageBox.Show(
                "Привет! Добро пожаловать в MetaMind.\n\n" +
                "• Автосканирование\n• Контрпики\n• Мета-обновления\n• GSI/CV hooks\n\n" +
                "Это первый запуск.",
                "Welcome to MetaMind",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            MarkFirstRunCompleted();
        }

        ShowToast($"MetaMind v{AppVersion} запущен");
    }

    private static bool IsFirstRun() => !File.Exists(FirstRunFile);

    private static void MarkFirstRunCompleted()
    {
        var payload = JsonSerializer.Serialize(new { firstRunCompleted = true, at = DateTimeOffset.Now });
        File.WriteAllText(FirstRunFile, payload);
    }

    private void ShowToast(string message)
    {
        ToastText.Text = message;
        var fadeIn = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(180));
        var fadeOut = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(280))
        {
            BeginTime = TimeSpan.FromMilliseconds(1400)
        };
        var sb = new Storyboard();
        Storyboard.SetTarget(fadeIn, Toast);
        Storyboard.SetTargetProperty(fadeIn, new PropertyPath(OpacityProperty));
        Storyboard.SetTarget(fadeOut, Toast);
        Storyboard.SetTargetProperty(fadeOut, new PropertyPath(OpacityProperty));
        sb.Children.Add(fadeIn);
        sb.Children.Add(fadeOut);
        sb.Begin();
    }

    private void HeaderDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.LeftButton == MouseButtonState.Pressed)
            DragMove();
    }

    private void Minimize_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void GoCounterPage(object sender, RoutedEventArgs e)
    {
        PageTitle.Text = "Контрпики";
        StatusText.Text = "Открыт раздел контрпиков";
        ShowToast("Открыт раздел: Контрпики");
    }

    private void GoMetaPage(object sender, RoutedEventArgs e)
    {
        PageTitle.Text = "Мета героев";
        StatusText.Text = "Открыт раздел меты";
        ShowToast("Открыт раздел: Мета");
    }

    private void StartAutoScan(object sender, RoutedEventArgs e)
    {
        ScanProgress.Value = 0;
        StatusText.Text = "Сканирование запущено";
        ShowToast("Автоскан запущен");
        _scanTimer.Start();
    }

    private void RefreshMeta(object sender, RoutedEventArgs e)
    {
        StatusText.Text = "Запрошено обновление меты";
        ShowToast("Обновление меты запрошено");
    }
}
