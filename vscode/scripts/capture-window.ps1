# Capture the inside of the top-level window of a process (not its frame and title bar), or resize it,
# without bringing it to the front:
#   capture-window.ps1 -ProcessId 1234 -Out shot.png
#   capture-window.ps1 -ProcessId 1234 -Width 1600 -Height 1000
#   capture-window.ps1 -ProcessId 1234 -Dpi          prints the DPI of the window's monitor (96 is 100%)
# Used by screenshots.mjs. PrintWindow with PW_RENDERFULLCONTENT also draws Chromium (Electron) windows.
param(
  [Parameter(Mandatory = $true)] [int] $ProcessId,
  [string] $Out = "",
  [int] $Width = 0,
  [int] $Height = 0,
  [switch] $Dpi
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint f);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr Find(uint pid) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h) && GetWindowTextLength(h) > 0) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
[void][Win]::SetProcessDPIAware()
$hwnd = [Win]::Find([uint32]$ProcessId)
if ($hwnd -eq [IntPtr]::Zero) { Write-Error "no window of process $ProcessId"; exit 2 }
if ($Width -gt 0 -and $Height -gt 0) {
  [void][Win]::ShowWindow($hwnd, 9)          # SW_RESTORE: not maximized, so the size applies
  [void][Win]::SetWindowPos($hwnd, [IntPtr]::Zero, 40, 40, $Width, $Height, 0x0014)   # NOZORDER | NOACTIVATE
}
if ($Dpi) { [Win]::GetDpiForWindow($hwnd) }
if ($Out) {
  $r = New-Object Win+RECT
  [void][Win]::GetClientRect($hwnd, [ref]$r)
  $bmp = New-Object System.Drawing.Bitmap ($r.Right - $r.Left), ($r.Bottom - $r.Top)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [void][Win]::PrintWindow($hwnd, $hdc, 3)   # PW_CLIENTONLY | PW_RENDERFULLCONTENT
  $g.ReleaseHdc($hdc)
  $g.Dispose()
  $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
}
