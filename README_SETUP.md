# AI-Line-Bot Setup Guide

The project files have been set up in `C:\Users\user\.gemini\antigravity\scratch\AI-Line-Bot-main`.

## Prerequisites

1.  **Install Python 3.11+**:
    -   Download and install from [python.org](https://www.python.org/downloads/).
    -   **Important**: Check the box "Add Python to PATH" during installation.

2.  **Open Terminal/PowerShell**:
    -   Navigate to the project folder:
        ```powershell
        cd C:\Users\user\.gemini\antigravity\scratch\AI-Line-Bot-main
        ```

3.  **Install Dependencies**:
    Running this command will install all required libraries:
    ```powershell
    pip install -r requirements.local.txt
    ```

4.  **Configure Environment**:
    -   Open the `.env` file in the project folder.
    -   Add your `GEMINI_API_KEY`.
    -   (Optional) Add LINE channel secrets if connecting to LINE.

5.  **Run the Application**:
    ```powershell
    python main.py
    ```
    The application will start at `http://localhost:5000`.
