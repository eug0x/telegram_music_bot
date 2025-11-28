# Telegram Music Bot: YouTube Audio Downloader

<div align="center">
<img src="static/header.png" alt="FloppyMusicBot Header Image" align="center" style="width: 100%; border-radius: 10px;" />
</div>

<br>



## ⚡ Features Summary

* **⚡ Fast Downloads:** Get your audio tracks delivered in just **5–15 seconds**.

* **🧹 Clean Interface:** Bot auto-deletes the user command, keeping your chat tidy.

* **🔎 Simple Command:** Use the direct **`music <song name>`** format for instant search.

* **💡 Intelligent Metadata:** Interactive button displays rich track details (author, views, likes, etc.).

* **🔄 Instant Alternatives:** Found the wrong version? A quick button allows re-selection from the top 10 search results.

* **🛡️ Robust & Stable:** Features built-in limits on file size/duration and a strong anti-spam system.




## 📸  Workflow

### 1. Song Download and Interactive Buttons


* **(`🎵 Requester Name`)**: Click to view detailed information about the song
* **(`🔎 Not the right song?`):** Click to view alternative versions.

<p align="center">
    <img src="static/1.png" alt="Screenshot 1: Main Download Interface with Buttons" style="max-width: 600px; border-radius: 8px;">
</p>

### 2. Detailed Song Metadata

Clicking the requester's name reveals a detailed pop-up alert containing statistics and metadata.
* **Custom Fact:** Includes a random, funny/interesting music history fact.

<p align="center">
    <img src="static/2.png" alt="Screenshot 2: Song Information Pop-up" style="max-width: 400px; border-radius: 8px;">
</p>

### 3. Alternative Search

If the first track is incorrect, the right button replaces the message buttons with a list of the next 10 search results for quick selection.

<p align="center">
    <img src="static/3.png" alt="Screenshot 3: Alternative Search Results List" style="max-width: 400px; border-radius: 8px;">
</p>




## 🛠️ Technical Highlights

1.  **Zero-Conversion (Maximum Speed):** The bot leverages Telegram's ability to play various audio formats by simply **renaming the extension to `.mp3`**. This eliminates CPU-heavy transcoding (no FFMpeg dependency), ensuring **near-instantaneous processing**

2.  **Asynchronous Core:** Built on the high-performance `aiogram`

3.  **Self-Updating Dependency:** The **`yt-dlp`** core is automatically checked and updated every **24 hours** (`core/yt_dlp_manager.py`), ensuring the bot's download functionality never breaks


## ⚙️ Customization (via `core/strings.py`)

The bot's interface and command structure can be fully customized by editing **`core/strings.py`**:

* **Command Prefix:** Change the bot's command trigger (e.g., replace `"music "` with `"search "` or `"download "`) by modifying the `COMMAND_PREFIX` variable.

* **Interface Language:** Change the bot's entire language interface by translating variables like `STATUS_SEARCHING`, `ERROR_PREFIX`, and all button texts.

* **Fun Facts/Taglines:** You can easily update the **list of random facts (`tagline`)** that appear at the bottom of the song information message. Add your own list of funny or interesting musical trivia to personalize the bot's output

---

### 📂 File Structure

```bash
│   main.py                 # start
│
├───core/                 
│   │   config.py           # Config, limits, and logging.
│   │   data_manager.py     # Data/cache storage.
│   │   mu.py               # Telegram handlers / Business logic.
│   │   strings.py          # Text messages.
│   │   youtube_downloader.py # Download and search functions.
│   │   yt_dlp_manager.py   # Handles yt-dlp update/download.
│
├───data/                  
│   │   .env                # Environment variables.
│   │   bot.log             # Error log file.
│   │   songs_info.json     # metadata 
│
├───temp/                   # for files being actively downloaded and processed.
│
└───yt_dlp/                
        yt-dlp.exe          # yt-dlp executable.
```


## ⚙️ Configuration

Set up your bot by creating a `data/.env` file and filling out the necessary parameters:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Your Telegram Bot Token from BotFather. | `YOUR_BOT_TOKEN` |
| `ALLOWED_CHAT_ID` | Access control. Comma-separated list of Chat IDs. <br>• **`Empty`:** Allowed in ALL public chats.<br>• **`false`:** Restricted from all public chats. | `false` |
| `ALLOW_PRIVATE_CHAT`| Enables/disables usage in private chats **(DMs)**. | `true` |
| `MAX_FILE_SIZE_MB` | Maximum allowed file size for download (in MB). | `20` |
| `MAX_SONG_DURATION_MIN`| Maximum allowed song duration (in minutes). | `15` |
| `CONCURRENT_DOWNLOAD_LIMIT` | Max number of parallel downloads the bot can handle. (Controlled by asyncio.Semaphore). | `5` |
| `ANTI_SPAM_INTERVAL` | Minimum pause between requests from one user (in seconds). | `15` |
| `INFO_EXPIRATION_HOURS`| Cache expiration time for song data to manage memory. | `10` |
| `BLOCKED_USER_IDS` | Comma-separated list of Telegram User IDs to block. | `1234567890,` |

---

## 🚀 Installation & Run

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/eug0x/telegram_music_bot
    cd FloppyMusicBot
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Setup Environment:**
    Create and configure the `data/.env` file based on the table above.

4.  **Run the bot:**
    ```bash
    python main.py
    ```
    *(The `yt-dlp` executable will be downloaded automatically on the first run.)*
