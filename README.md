# 📞 AI Call Agent for Appointment Scheduling

## 🚀 Overview
AI Call Agent is an intelligent voice assistant that handles appointment scheduling via phone calls. It interacts with users in real-time, processes speech-to-text conversion, extracts booking details, and schedules appointments using an AI-driven conversation flow.

## 🏗️ Features
- **Real-time AI-powered conversation**
- **Speech-to-text transcription** for call processing
- **Appointment booking** based on user inputs
- **Twilio integration** for call handling
- **Automated email confirmations**
- **Multi-language support (English/Hindi)**
- **Database-backed scheduling system**

## 🛠️ Tech Stack
- **Backend:** FastAPI, Python
- **AI Model:** OpenAI GPT-4o Realtime API
- **Telephony:** Twilio Voice API, WebSockets
- **Database:** PostgreSQL / SQLite

## 📜 API Endpoints

### 1 **Incoming Call Handler**
```http
POST /incoming-call
```
### 2 **WebSocket Media Stream**
```http
/ws/media-stream
```

### 3 **Booking Storage**
```http
POST /create-booking
```
