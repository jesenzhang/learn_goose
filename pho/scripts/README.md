# Pho Startup Scripts

This directory contains standalone startup scripts for the Pho API server and Workflow Editor.

## Directory Structure

```
pho/
├── scripts/
│   ├── start_api.py      # Python API server script
│   ├── start_api.ps1     # PowerShell API server script
│   ├── start_api.bat     # Batch API server script
│   ├── start_api.sh      # Bash API server script
│   ├── start_editor.py   # Python editor script
│   ├── start_editor.ps1  # PowerShell editor script
│   ├── start_editor.bat  # Batch editor script
│   └── start_editor.sh   # Bash editor script
├── web/
│   ├── react-editor/     # React frontend
│   └── logs/             # Log files
└── src/                  # Python source code
```

## Quick Start

### Windows (PowerShell)

**Terminal 1 - Start API Server:**
```powershell
cd D:\WorkSpace\learn_goose\pho\scripts
.\start_api.ps1
```

**Terminal 2 - Start Editor:**
```powershell
cd D:\WorkSpace\learn_goose\pho\scripts
.\start_editor.ps1
```

### Windows (Batch)

**Terminal 1 - Start API Server:**
```cmd
cd D:\WorkSpace\learn_goose\pho\scripts
start_api.bat
```

**Terminal 2 - Start Editor:**
```cmd
cd D:\WorkSpace\learn_goose\pho\scripts
start_editor.bat
```

### Linux/macOS (Bash)

**Terminal 1 - Start API Server:**
```bash
cd /path/to/pho/scripts
./start_api.sh
```

**Terminal 2 - Start Editor:**
```bash
cd /path/to/pho/scripts
./start_editor.sh
```

### Python (Cross-platform)

**Terminal 1 - Start API Server:**
```bash
cd /path/to/pho/scripts
python start_api.py
```

**Terminal 2 - Start Editor:**
```bash
cd /path/to/pho/scripts
python start_editor.py
```

## API Server Scripts

### start_api.py
```bash
python start_api.py [--host HOST] [--port PORT] [--log-level LEVEL] [--reload]

# Examples
python start_api.py                                    # Default: 127.0.0.1:8300
python start_api.py --host 0.0.0.0 --port 9000         # Custom host/port
python start_api.py --log-level debug                  # Debug logging
python start_api.py --reload                           # Auto-reload for development
```

### start_api.ps1
```powershell
.\start_api.ps1 [-Host HOST] [-Port PORT] [-LogLevel LEVEL] [-Reload]

# Examples
.\start_api.ps1                                        # Default: 127.0.0.1:8300
.\start_api.ps1 -Host "0.0.0.0" -Port 9000             # Custom host/port
.\start_api.ps1 -LogLevel "debug"                      # Debug logging
.\start_api.ps1 -Reload                                # Auto-reload for development
```

### start_api.bat
```cmd
start_api.bat [HOST] [PORT] [LOG_LEVEL]

# Examples
start_api.bat                                          # Default: 127.0.0.1:8300
start_api.bat 0.0.0.0 9000                             # Custom host/port
start_api.bat 127.0.0.1 8300 debug                     # Debug logging
```

### start_api.sh
```bash
./start_api.sh [HOST] [PORT] [LOG_LEVEL]

# Examples
./start_api.sh                                         # Default: 127.0.0.1:8300
./start_api.sh 0.0.0.0 9000                            # Custom host/port
./start_api.sh 127.0.0.1 8300 debug                    # Debug logging
```

## Editor Scripts

### start_editor.py
```bash
python start_editor.py [--port PORT] [--api-url API_URL]

# Examples
python start_editor.py                                 # Default: port 3000, API at 127.0.0.1:8300
python start_editor.py --port 8300                     # Custom port
python start_editor.py --port 3000 --api-url http://localhost:9000
```

### start_editor.ps1
```powershell
.\start_editor.ps1 [-Port PORT] [-ApiUrl API_URL]

# Examples
.\start_editor.ps1                                     # Default: port 3000, API at 127.0.0.1:8300
.\start_editor.ps1 -Port 8300                          # Custom port
.\start_editor.ps1 -Port 3000 -ApiUrl "http://localhost:9000"
```

### start_editor.bat
```cmd
start_editor.bat [PORT] [API_URL]

# Examples
start_editor.bat                                       # Default: port 3000, API at 127.0.0.1:8300
start_editor.bat 8300                                  # Custom port
start_editor.bat 3000 http://localhost:9000
```

### start_editor.sh
```bash
./start_editor.sh [PORT] [API_URL]

# Examples
./start_editor.sh                                      # Default: port 3000, API at 127.0.0.1:8300
./start_editor.sh 8300                                 # Custom port
./start_editor.sh 3000 http://localhost:9000
```

## Default Configuration

| Setting | API Server | Editor |
|---------|-----------|--------|
| Host    | 127.0.0.1  | -      |
| Port    | 8300      | 3000   |
| Log Level | info   | -      |
| Log File | `../web/logs/api-server.log` | - |

## Access Points

Once both servers are running:

| Service | URL |
|---------|-----|
| React Editor | http://localhost:3000 |
| API Server | http://127.0.0.1:8300 |
| API Docs | http://127.0.0.1:8300/docs |
| Health Check | http://127.0.0.1:8300/health |

## Troubleshooting

### Port Already in Use
If you get a "port already in use" error:
1. Use a different port: `.\start_api.ps1 -Port 8301`
2. Or stop the process using the port:
   ```powershell
   netstat -ano | findstr :8300
   taskkill /PID <PID> /F
   ```

### API Server Not Starting
1. Check the log file: `pho/web/logs/api-server.log`
2. Verify Python is installed: `python --version`
3. Ensure dependencies are installed: `pip install -r requirements.txt`

### Editor Not Connecting to API
1. Verify API server is running: `curl http://127.0.0.1:8300/health`
2. Check the API_URL parameter matches the API server address
3. Check browser console for CORS errors

### UTF-8 Encoding Errors (Windows)
If you see encoding errors with emoji characters:
- The PowerShell scripts automatically set `PYTHONIOENCODING=utf-8`
- For manual execution: `$env:PYTHONIOENCODING = "utf-8"`
