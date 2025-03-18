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
import google.generativeai as genai
from speech_handler import SpeechHandler

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SMS_KEY = os.getenv('SMS_KEY')
PORT = int(os.getenv('PORT', 8010))
current_datetime = datetime.now()
current_date = current_datetime.strftime("%d-%m-%Y")
current_time = current_datetime.strftime("%I:%M %p")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

SYSTEM_MESSAGE = """
I am Cosmo, a healthcare diagnostic expert. I can assist you with healthcare queries and test bookings.

Test Booking Requirements:
- Phone Number (must be valid)
- City
- Test Name
- Preferred Date
- Preferred Time
- Collection Type (Home Collection/In-Clinic Collection)

Key Behaviors:
1. Ask only one follow-up question at a time to gather required information
2. After test selection:
   - Suggest preparation guidelines
   - Recommend optimal timing based on current date ({current_date}) and time ({current_time})
3. Language Protocol:
   - Default: English
   - Switch to Hindi only if user communicates in Hindi/Hinglish
4. Persona: Female healthcare expert

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
speech_handler = None

@app.on_event("startup")
async def startup_event():
    global speech_handler
    try:
        speech_handler = SpeechHandler()
        print("Speech recognition system initialized")
    except Exception as e:
        print(f"Error initializing speech recognition: {e}")
        print("Please run setup_model.py first to download the required model")

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    body = await request.body()
    print("Headers:", request.headers)
    print("Body:", body.decode())
    response = VoiceResponse()
    response.say("Hello there! I am Cosmo, your healthcare diagnostic expert.")
    response.pause(length=1)
    response.say("How can I assist you with your healthcare needs today?")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections for the conversation."""
    if not speech_handler:
        print("Speech recognition not initialized!")
        return
    
    print("Client connected")
    await websocket.accept()
    
    chat = model.start_chat(history=[])
    
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            if data['event'] == 'media':
                # Process audio with Vosk
                text = speech_handler.process_audio(data['media']['payload'])
                if text:
                    print(f"Recognized: {text}")
                    
                    # Get response from Gemini
                    response = await asyncio.to_thread(
                        chat.send_message,
                        text
                    )
                    
                    print(f"AI Response: {response.text}")
                    
                    # Check for booking confirmation
                    if "confirm" in text.lower() and "booking" in text.lower():
                        # Example booking details - in real app, extract from conversation
                        phone = "8295371847"
                        city = "Bangalore"
                        test_name = "Blood Test"
                        preferred_date = "06-12-2025"
                        preferred_time = "10:00AM"
                        collection_type = "In-Clinic Collection"
                        
                        try:
                            # Store booking in database
                            booking = create_booking(
                                phone=phone,
                                city=city,
                                test_name=test_name,
                                preferred_date=preferred_date,
                                preferred_time=preferred_time,
                                collection_type=collection_type,
                                booking_datetime=datetime.now()
                            )
                            print(f"Booking stored in database with ID: {booking.id}")
                            
                            # Send SMS confirmation
                            url = "https://www.fast2sms.com/dev/bulkV2"
                            api_key = "WOfGCbYeFN7rynSxqPRpXMhJZu2g406mjBi3tlavUdkQ5IK1A9CqMnKYXaVxAEWd6N1u3OfTP9mSG7Je"
                            msg = f'Your test booking is confirmed! Details: \nPhone: {phone} \nCity: {city} \nTest: {test_name} \nDate: {preferred_date} \nTime: {preferred_time} \nCollection: {collection_type} \nThank you for choosing us!'
                            
                            querystring = {
                                "authorization": api_key,
                                "message": msg,
                                "language": "english",
                                "route": "q",
                                "numbers": phone
                            }
                            headers = {
                                'cache-control': "no-cache"
                            }
                            response = requests.request("GET", url, headers=headers, params=querystring)
                            print(f"SMS Status: {response.status_code}")
                            print(response.text)
                            
                        except Exception as e:
                            print(f"Error in booking process: {e}")
                    
                    # Convert AI response to speech using Twilio's TTS
                    twiml = VoiceResponse()
                    twiml.say(response.text)
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": data.get('streamSid'),
                        "media": {
                            "payload": str(twiml)
                        }
                    })
            
            elif data['event'] == 'stop':
                print("Call ended")
                break
                
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in websocket handler: {e}")
        if not websocket.client_state.disconnected:
            await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
