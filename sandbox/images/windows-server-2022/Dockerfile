# ─────────────────────────────────────────────────────────────────────────────
# Windows Server 2022 Sandbox Image
#
# Uses Windows Server Core with Python + VNC (TightVNC) for remote desktop.
# The sandbox server runs the same FastAPI app as the Linux images.
#
# NOTE: This Dockerfile must be built on a Windows Docker host or using
# a CI pipeline that supports Windows container builds.
#
# Build context should be the sandbox/ root so COPY paths work:
#   docker build -f images/windows-server-2022/Dockerfile -t sandbox-windows-2022 .
# ─────────────────────────────────────────────────────────────────────────────

# escape=`
FROM mcr.microsoft.com/windows/servercore:ltsc2022

SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

# ── Install Python ───────────────────────────────────────────────────────────
RUN Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe" `
    -OutFile "python-installer.exe" ; `
    Start-Process -FilePath "python-installer.exe" `
        -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" `
        -Wait -NoNewWindow ; `
    Remove-Item "python-installer.exe"

# ── Install Git ──────────────────────────────────────────────────────────────
RUN Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe" `
    -OutFile "git-installer.exe" ; `
    Start-Process -FilePath "git-installer.exe" `
        -ArgumentList "/SILENT /NORESTART" `
        -Wait -NoNewWindow ; `
    Remove-Item "git-installer.exe"

# ── Install TightVNC (VNC server for Windows) ────────────────────────────────
RUN Invoke-WebRequest -Uri "https://www.tightvnc.com/download/2.8.84/tightvnc-2.8.84-gpl-setup-64bit.msi" `
    -OutFile "tightvnc.msi" ; `
    Start-Process msiexec -ArgumentList "/i tightvnc.msi /quiet /norestart SET_USEVNCAUTHENTICATION=1 VALUE_OF_USEVNCAUTHENTICATION=0" `
        -Wait -NoNewWindow ; `
    Remove-Item "tightvnc.msi"

# ── Install Google Chrome ────────────────────────────────────────────────────
RUN Invoke-WebRequest -Uri "https://dl.google.com/chrome/install/GoogleChromeStandaloneEnterprise64.msi" `
    -OutFile "chrome.msi" ; `
    Start-Process msiexec -ArgumentList "/i chrome.msi /quiet /norestart" `
        -Wait -NoNewWindow ; `
    Remove-Item "chrome.msi"

# ── Copy sandbox server ─────────────────────────────────────────────────────
COPY server/ C:/sandbox-server/

RUN pip install --no-cache-dir -r C:/sandbox-server/requirements.txt

# ── Copy Windows entrypoint ──────────────────────────────────────────────────
COPY images/windows-server-2022/entrypoint.ps1 C:/entrypoint.ps1

WORKDIR C:/sandbox-server

EXPOSE 8080

ENTRYPOINT ["powershell", "-File", "C:\\entrypoint.ps1"]
