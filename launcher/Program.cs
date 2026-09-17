using System.Diagnostics;
using System.Windows.Forms;

var root = AppContext.BaseDirectory;
var python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
if (!File.Exists(python))
{
    MessageBox.Show("GestureFlow's Python environment is missing. Follow README.md in the project folder to install it.", "GestureFlow");
    return;
}
try
{
    var start = new ProcessStartInfo(python) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true };
    start.ArgumentList.Add(Path.Combine(root, "main.py"));
    foreach (var arg in args) start.ArgumentList.Add(arg);
    Process.Start(start);
}
catch (Exception ex)
{
    MessageBox.Show(ex.Message, "GestureFlow could not start");
}
