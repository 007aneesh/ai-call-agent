import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv
import requests
from datetime import datetime
from models import create_booking
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
PORT = int(os.getenv('PORT', 8010))
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
current_datetime = datetime.now()
current_date = current_datetime.strftime("%d-%m-%Y")
current_time = current_datetime.strftime("%I:%M %p")
SYSTEM_MESSAGE = """
I am Cosmo, a healthcare diagnostic expert. I can assist you with healthcare queries and test bookings.

Test Booking Requirements:
- Phone Number (must be valid)
- Email Address (for booking confirmation)
- City
- Test Name
- Preferred Date
- Preferred Time
- Collection Type (Home Collection/In-Clinic Collection)

Key Behaviors:
1. Ask only one follow-up question at a time to gather required information
2. After collecting phone number, always ask for email address for booking confirmation
3. After test selection:
   - Suggest preparation guidelines
   - Recommend optimal timing based on current date ({current_date}) and time ({current_time})
4. Language Protocol:
   - Default: English
   - Switch to Hindi only if user communicates in Hindi/Hinglish
5. Persona: Female healthcare expert

Sample Interaction Flow:
User: "Can you book a test?"
Cosmo: "Of course! Are you booking this test for yourself or someone else?"
[If for self: Use existing user details]
[If for others: Collect name and email]

Booking Confirmation:
- Summarize all collected details
- Confirm booking
- Mention that a confirmation email will be sent

Note: Always verify phone numbers for validity before proceeding with booking.
"""

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

LOG_EVENT_TYPES = [
    'session.update',
    'conversation.item.create',
    'conversation.item.truncate',
    'response.create',
    'response.complete',
    'input_audio_buffer.speech_started',
    'input_audio_buffer.speech_stopped'
]

SHOW_TIMING_MATH = False
VOICE = "alloy"

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running 555!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    body = await request.body()
    print("Headers:", request.headers)
    print("Body:", body.decode())
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Hello there! I am an AI call assistant created by Aneesh")
    response.pause(length=1)
    response.say("O.K. you can start talking!")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    
    # Initialize booking details as None
    booking_details = {
        'phone': None,
        'email': None,
        'city': None,
        'test_name': None,
        'preferred_date': None,
        'preferred_time': None,
        'collection_type': None
    }
    
    # Store booking in database and send confirmation when all details are collected
    async def process_booking():
        try:
            booking = create_booking(
                phone=booking_details['phone'],
                email=booking_details['email'],
                city=booking_details['city'],
                test_name=booking_details['test_name'],
                preferred_date=booking_details['preferred_date'],
                preferred_time=booking_details['preferred_time'],
                collection_type=booking_details['collection_type'],
                booking_datetime=datetime.now()
            )
            print(f"Booking stored in database with ID: {booking.id}")
            
            # Send email confirmation
            confirmation_result = await send_booking_confirmation(booking)
            print(f"Email confirmation status: {confirmation_result['status']}")
            if confirmation_result['status'] == 'error':
                print(f"Email error: {confirmation_result['message']}")
                
        except Exception as e:
            print(f"Error processing booking: {e}")
    
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await initialize_session(openai_ws)

        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        
        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, latest_media_timestamp
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        latest_media_timestamp = int(data['media']['timestamp'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"Incoming stream has started {stream_sid}")
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def receive_from_openai():
            """Receive events from the OpenAI Realtime API, process conversation, and send audio back to Twilio."""
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    # Process conversation content for booking details
                    if response.get('type') == 'conversation.item.create':
                        content = response.get('item', {}).get('content', [])
                        for item in content:
                            if item.get('type') == 'text':
                                text = item.get('text', '').lower()
                                # Extract phone number
                                if any(word in text for word in ['phone', 'number', 'mobile']):
                                    import re
                                    phone_match = re.search(r'\b\d{10}\b', text)
                                    if phone_match:
                                        booking_details['phone'] = phone_match.group()
                                
                                # Extract email
                                if any(word in text for word in ['email', '@']):
                                    import re
                                    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                                    if email_match:
                                        booking_details['email'] = email_match.group()
                                
                                # Extract city
                                if 'city' in text:
                                    cities = ['bangalore', 'delhi', 'mumbai', 'chennai', 'kolkata']
                                    for city in cities:
                                        if city in text.lower():
                                            booking_details['city'] = city.title()
                                
                                # Extract test name
                                if 'test' in text:
                                    tests = ['blood test', 'urine test', 'covid test', 'diabetes test']
                                    for test in tests:
                                        if test in text.lower():
                                            booking_details['test_name'] = test.title()
                                
                                # Extract date
                                if any(word in text for word in ['date', 'day']):
                                    import re
                                    date_match = re.search(r'\d{2}[-/]\d{2}[-/]\d{4}', text)
                                    if date_match:
                                        booking_details['preferred_date'] = date_match.group()
                                
                                # Extract time
                                if any(word in text for word in ['time', 'timing', 'schedule']):
                                    import re
                                    time_match = re.search(r'\d{1,2}[:]\d{2}\s*(?:AM|PM|am|pm)', text)
                                    if time_match:
                                        booking_details['preferred_time'] = time_match.group().upper()
                                
                                # Extract collection type
                                if 'collection' in text:
                                    if 'home' in text.lower():
                                        booking_details['collection_type'] = 'Home Collection'
                                    elif 'clinic' in text.lower():
                                        booking_details['collection_type'] = 'In-Clinic Collection'
                                
                                # Check if all required fields are filled
                                if all(booking_details.values()):
                                    await process_booking()

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_payload
                            }
                        }
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp_twilio is None:
                            response_start_timestamp_twilio = latest_media_timestamp
                            if SHOW_TIMING_MATH:
                                print(f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                        await send_mark(websocket, stream_sid)

            except Exception as e:
                print(f"Error in receive_from_openai: {e}")

        async def handle_speech_started_event():
            """Handle interruption when the caller's speech starts."""
            nonlocal response_start_timestamp_twilio, last_assistant_item
            print("Handling speech started event.")
            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                if SHOW_TIMING_MATH:
                    print(f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms")

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms")

                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"}
                }
                await connection.send_json(mark_event)
                mark_queue.append('responsePart')

        await asyncio.gather(receive_from_twilio(), receive_from_openai())

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Hello there! I am an AI call assistant. How can I help you?'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))


async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    # Uncomment the next line to have the AI speak first
    # await send_initial_conversation_item(openai_ws)

async def send_booking_confirmation(booking):
    sender_email = SMTP_EMAIL
    receiver_email = booking.email  # We'll need to add email field to booking model
    
    message = MIMEMultipart("alternative")
    message["Subject"] = "Test Booking Confirmation"
    message["From"] = sender_email
    message["To"] = receiver_email

    # Create HTML version of message
    html = f"""
    <html>
        <body>
            <h2>Your test booking is confirmed!</h2>
            <p>Here are your booking details:</p>
            <ul>
                <li><b>Phone:</b> {booking.phone}</li>
                <li><b>City:</b> {booking.city}</li>
                <li><b>Test:</b> {booking.test_name}</li>
                <li><b>Date:</b> {booking.preferred_date}</li>
                <li><b>Time:</b> {booking.preferred_time}</li>
                <li><b>Collection Type:</b> {booking.collection_type}</li>
            </ul>
            <p>Thank you for choosing us!</p>
        </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, SMTP_PASSWORD)
            server.sendmail(sender_email, receiver_email, message.as_string())
        return {"status": "success", "message": "Confirmation email sent successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
