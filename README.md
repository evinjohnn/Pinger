﻿# Pinger

<div align="center">
  <div style="width: 400px; height: 400px; background-color: #f0f2f5; border-radius: 30px; display: flex; align-items: center; justify-content: center; margin: 30px 0 60px 0;">
    <span style="font-size: 300px; line-height: 4;">📡</span>
  </div>
  <p>
    <a href="https://github.com/evinjohnn/pinger/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="license" />
    </a>
    <a href="https://github.com/evinjohnn/pinger/actions/workflows/pinger.yaml">
      <img src="https://github.com/evinjohnn/pinger/actions/workflows/pinger.yaml/badge.svg" alt="ci status" />
    </a>
    <img src="https://img.shields.io/badge/Python-3.9%2B-blue.svg" alt="python version" />
    <a href="https://vercel.com">
      <img src="https://img.shields.io/badge/Vercel-Powered-black?logo=vercel" alt="powered by vercel" />
    </a>
  </p>
  <h1 align="center">Pinger</h1>
  <p align="center">
    A lightweight, secure, and serverless monitoring service to keep your applications alive.<br />
    <a href="#-how-it-works"><strong>Explore the architecture »</strong></a><br /><br />
    <a href="https://pinger-evinjohnns-projects.vercel.app/">View Live Service</a>
    ·
    <a href="https://github.com/evinjohnn/pinger/issues">Report Bug</a>
    ·
    <a href="https://github.com/evinjohnn/pinger/issues">Request Feature</a>
  </p>
</div>

---

## 📍 About The Project

Many free hosting platforms (like Render, Heroku) put applications to "sleep" after inactivity, causing cold starts that delay user experience.
**Pinger** is a **set-it-and-forget-it** service that keeps your apps awake by automatically pinging them, ensuring they're always ready for visitors.

---

## ✨ Core Features

- ⏱️ **24/7 Uptime**: Pings your URLs at a consistent interval to prevent sleeping.
- 🔐 **Secure Management**: Unique removal keys are generated for each URL, preventing unauthorized deletions.
- 🧠 **Persistent Storage**: URLs are saved in a serverless Redis database (via Upstash).
- ⚙️ **Serverless**: Hosted on Vercel — no server maintenance, and it's free.
- 🧼 **Simple UI**: A clean, user-friendly interface to add and remove your URLs.
- 📦 **Open Source**: Use it, fork it, and improve it. Your contributions are welcome!

---

## 🚀 Live Service

You can use the public version for free. No sign-up required.

➡️ **https://pinger-evinjohnns-projects.vercel.app** ⬅️

---

## 🛠️ Technology Stack

- **Backend**: Python 3.9+, Flask, aiohttp
- **Database**: Redis (via Upstash)
- **Hosting**: Vercel (for frontend and serverless functions)
- **CI/CD**: GitHub Actions (for the cron job trigger)
- **Frontend**: Vanilla JavaScript, HTML, CSS

---

## 🔧 How It Works

The architecture is designed for simplicity, security, and scalability.

1. **Add URL**: A user submits a URL through the frontend.
2. **Generate Key**: The `/api/add-url` Flask endpoint generates a unique, secret **removal key**.
3. **Store Securely**: The URL and its removal key are stored as a pair in a Redis Hash.
4. **Return Key**: The API returns the removal key to the user. **This key is required to remove the URL later.**
5. **Remove URL**: To remove a URL, the user must provide both the URL and its corresponding removal key to the `/api/remove-url` endpoint for verification.
6. **Automated Pinging**: A GitHub Actions cron job triggers the `/api/ping-all` endpoint every few minutes.
7. **Concurrent Pinging**: The API retrieves all URLs from Redis and pings them concurrently using `aiohttp` for high efficiency.

### Architecture Diagram

```mermaid
flowchart TD
    subgraph "User Interaction"
        User["👤 User"] -->|"1. Submits URL"| AddAPI["/api/add-url"]
        AddAPI -->|"3. Returns Removal Key"| User
        User -->|"4. Submits URL + Key"| RemoveAPI["/api/remove-url"]
    end

    subgraph "Backend & Storage"
        AddAPI -->|"2. Generates Key & Stores"| Redis["💾 Redis Hash<URL, Key>"]
        RemoveAPI -->|"5. Verifies & Deletes"| Redis
    end

    subgraph "Automated Pinging"
        Cron["🤖 GitHub Actions Cron"] -->|"6. Triggers every 3 mins"| PingAPI["/api/ping-all"]
        PingAPI -->|"7. Reads all URLs"| Redis
        PingAPI -->|"8. Pings concurrently"| TargetApps["🚀 Target Apps"]
        TargetApps -->|"Stays Awake!"| Done(["✓"])
    end
```

---

## 🏠 Local Development & Setup

### Prerequisites
- Git
- Python 3.9+

### Setup

```sh
# Clone the repository
git clone https://github.com/evinjohnn/pinger.git
cd pinger

# Create and activate a virtual environment (macOS/Linux)
python3 -m venv venv
source venv/bin/activate

# Create and activate a virtual environment (Windows)
python -m venv venv
.\venv\Scripts\activate

# Install dependencies and run the app
pip install -r requirements.txt
python api/index.py
```

Visit [http://127.0.0.1:5001](http://127.0.0.1:5001) in your browser. The local environment uses an in-memory mock database and does not require Redis.

---

## ☁️ Deployment

### One-click Deploy

Deploy your own private instance of Pinger to Vercel with a single click.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/project?template=https://github.com/evinjohnn/pinger)

### Manual Steps

1. Fork this repository.
2. Create a new Vercel project and link it to your forked repository.
3. Add the Upstash Redis integration from the Vercel Marketplace. This will automatically set the `REDIS_URL` environment variable.
4. Add the following environment variables to your Vercel project settings:

| Variable    | Description                                 | Example                                      |
|-------------|---------------------------------------------|----------------------------------------------|
| REDIS_URL   | Redis connection URL (set by Upstash).      | redis://default:xxx@region.upstash.io        |
| CRON_SECRET | A secret token to protect the /api/ping-all.| generate_a_long_random_secret_string         |
| PING_URL    | The full URL for your deployed ping endpoint.| https://your-app.vercel.app/api/ping-all     |

5. In your forked repository, edit the `.github/workflows/pinger.yaml` file and update the `PING_URL` and `CRON_SECRET` to match the values you set in Vercel.

---

## 🤝 Contributing

Contributions make the open-source community an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📜 License

Distributed under the MIT License. See [LICENSE](https://github.com/evinjohnn/pinger/blob/main/LICENSE) for more information.

<p align="center">
<small>Crafted with ❤️ by Evin John</small>
</p>
