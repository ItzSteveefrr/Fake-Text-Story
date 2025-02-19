from flask import Flask, request, jsonify, send_file, render_template, session
from flask_cors import CORS
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, CompositeAudioClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import tempfile
import time
import os
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import numpy as np
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import subprocess
from datetime import datetime
import json     
import traceback
import shutil

app = Flask(__name__)
CORS(app)

# Global list to track temporary files for cleanup
temp_files = []

# Add these configuration variables at the top with your other constants
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID')

VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.45,
    "style": 0.40,
}
SOUND_EFFECTS = {
    'vineboom': os.path.join('static', 'sfx', 'vineboom.mp3'),
    'notification': os.path.join('static', 'sfx', 'notification.mp3'),
    'rizz': os.path.join('static', 'sfx', 'rizz.mp3'),
    'imessage_text': os.path.join('static', 'sfx', 'iMessage Text.mp3'),
}

GOOGLE_DRIVE_SETTINGS = {
    'folder_id': '1Q-w2JOD4fiEhI8bs8btcF0zsE92SuXv5',  # The Google Drive folder ID where videos will be uploaded
    'credentials_path': 'service-account.json'  # Path to your service account JSON file
}

def get_google_drive_service():
    """Get Google Drive service using service account"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_DRIVE_SETTINGS['credentials_path'],
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        print(f"Error creating Drive service: {str(e)}")
        return None

def upload_to_drive(file_path, file_name):
    """Upload file to Google Drive using service account"""
    try:
        service = get_google_drive_service()
        if not service:
            return None

        file_metadata = {
            'name': file_name,
            'parents': [GOOGLE_DRIVE_SETTINGS['folder_id']] if GOOGLE_DRIVE_SETTINGS['folder_id'] else None
        }
        
        media = MediaFileUpload(
            file_path,
            mimetype='video/mp4',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return {
            'id': file.get('id'),
            'link': file.get('webViewLink')
        }
        
    except Exception as e:
        print(f"Error uploading to Google Drive: {str(e)}")
        return None
        
@app.route('/')
def index():
    return render_template('index.html')

def generate_default_profile_image(name, size=200):
    """Generate a default profile image with the first letter of the name"""
    try:
        # Create a new image with a light blue background (iOS-like)
        background_color = (0, 122, 255)  # iOS blue color
        image = Image.new('RGB', (size, size), background_color)
        draw = ImageDraw.Draw(image)
        
        # Get the first letter and make it uppercase
        letter = name[0].upper() if name else '?'
        
        # Calculate font size (approximately half the image size)
        font_size = int(size * 0.5)
        
        # Create font object
        try:
            # Try to use a system font similar to iOS
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            # Fallback to default font
            font = ImageFont.load_default()
            font_size = 50  # Adjust default font size
        
        # Calculate text size and position to center it
        text_bbox = draw.textbbox((0, 0), letter, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2
        
        # Draw the letter in white
        draw.text((x, y), letter, fill='white', font=font)
        
        # Convert to bytes
        img_byte_array = io.BytesIO()
        image.save(img_byte_array, format='PNG')
        img_byte_array.seek(0)
        
        # Convert to base64
        import base64
        return f"data:image/png;base64,{base64.b64encode(img_byte_array.getvalue()).decode()}"
        
    except Exception as e:
        print(f"Error generating default profile image: {e}")
        return None

def capture_chat_interface(messages, show_header=True, header_data=None):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--hide-scrollbars')
    chrome_options.add_argument('--force-device-scale-factor=1')
    chrome_options.add_argument('--window-size=414,900')
    
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get('http://127.0.0.1:8080')
        
        # Wait for elements
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "dynamic-container"))
        )
        
        # Apply theme if provided
        if header_data and header_data.get('theme') == 'dark':
            driver.execute_script("""
                document.querySelector('.container').classList.add('dark-theme');
            """)
            time.sleep(0.5)  # Wait for theme to apply
        
        # Set back button position from localStorage
        driver.execute_script("""
            const backButton = document.querySelector('.header-left');
            if (backButton) {
                const savedPosition = localStorage.getItem('backButtonPosition');
                if (savedPosition) {
                    const position = JSON.parse(savedPosition);
                    backButton.style.position = 'absolute';
                    backButton.style.left = position.left;
                    backButton.style.top = position.top;
                    backButton.style.zIndex = '1000';
                }
            }
        """)
        time.sleep(0.5)  # Wait for position to apply
        
        # Apply header data if provided
        if header_data:
            # Get profile image or generate default
            profile_image = header_data.get('profileImage', '')
            header_name = header_data.get('headerName', 'John Doe')
            
            if not profile_image or profile_image.endswith('profile.jpg'):
                # Generate default profile image with first letter
                profile_image = generate_default_profile_image(header_name)
            
            # Set the profile image
            if profile_image:
                driver.execute_script("""
                    const imgElement = document.getElementById('profileImage');
                    if (imgElement) {
                        imgElement.src = arguments[0];
                        // Ensure image is loaded before proceeding
                        return new Promise((resolve) => {
                            imgElement.onload = resolve;
                            imgElement.onerror = resolve;
                        });
                    }
                """, profile_image)
                time.sleep(1)  # Wait for image to load
            
            # Set the header name
            if header_name:
                driver.execute_script("""
                    const headerNameElement = document.getElementById('headerName');
                    if (headerNameElement) {
                        headerNameElement.textContent = arguments[0];
                        headerNameElement.offsetHeight;
                        headerNameElement.style.display = 'none';
                        headerNameElement.offsetHeight;
                        headerNameElement.style.display = '';
                        headerNameElement.offsetHeight;
                    }
                """, header_name)
                time.sleep(0.5)  # Wait for name to update
        
        # Set transparent background
        driver.execute_script("""
            document.body.style.background = 'transparent';
            document.documentElement.style.background = 'transparent';
        """)
        
        # Modified JavaScript to properly handle sound effects
        driver.execute_script("""
            const messages = arguments[0];
            const showHeader = arguments[1];
            
            // Remove input area
            const inputArea = document.querySelector('.input-area');
            if (inputArea) inputArea.remove();
            
            const container = document.querySelector('.container');
            const messageContainer = document.getElementById('messageContainer');
            const header = document.querySelector('.header');
            const dynamicContainer = messageContainer.querySelector('.dynamic-container');
            
            // Show/hide header
            if (header) {
                header.style.display = showHeader ? 'flex' : 'none';
            }
            
            // Reset container styles
            container.style.minHeight = 'unset';
            container.style.height = 'auto';
            messageContainer.style.height = 'auto';
            messageContainer.style.maxHeight = 'none';
            messageContainer.style.minHeight = 'unset';
            
            // Clear existing messages
            dynamicContainer.innerHTML = '';
            
            messages.forEach(msg => {
                if (msg && msg.text) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message ${msg.is_sender ? 'sender' : 'receiver'} ${msg.type === 'picture' ? 'picture' : ''}`;
                    messageDiv.setAttribute('data-id', msg.id);
                    
                    if (msg.type === 'picture') {
                        const img = document.createElement('img');
                        img.src = msg.text;
                        img.style.maxWidth = '100%';
                        img.style.borderRadius = '12px';
                        messageDiv.appendChild(img);
                    } else {
                        messageDiv.textContent = msg.text.trim();
                    }
                    
                    if (msg.soundEffect) {
                        messageDiv.setAttribute('data-sound-effect', msg.soundEffect);
                    }
                    
                    dynamicContainer.appendChild(messageDiv);
                }
            });

            // Force layout recalculation
            container.offsetHeight;
        """, messages, show_header)
        
        # Wait for messages to render
        time.sleep(1.5)
        
        # Take screenshot
        container = driver.find_element(By.CLASS_NAME, "container")
        screenshot = container.screenshot_as_png
        image = Image.open(io.BytesIO(screenshot))
        
        # Convert to RGBA to handle transparency
        image = image.convert('RGBA')
        
        # Create a mask for rounded corners
        mask = Image.new('L', image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([(0, 0), (image.size[0]-1, image.size[1]-1)], 20, fill=255)
        
        # Apply the mask
        output = Image.new('RGBA', image.size, (0, 0, 0, 0))
        output.paste(image, mask=mask)
        
        # Crop to content
        bbox = output.getbbox()
        if bbox:
            output = output.crop(bbox)
        
        return output
        
    except Exception as e:
        print(f"Error capturing chat interface: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        driver.quit()

def generate_audio_eleven_labs(text, voice_id, api_key):
    """Generate audio using ElevenLabs API with retry mechanism"""
    print(f"\nGenerating audio for voice_id: {voice_id}")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": VOICE_SETTINGS
    }
    
    max_retries = 5
    base_delay = 3  # Start with 3 seconds delay
    
    for attempt in range(max_retries):
        try:
            print(f"Making API request (attempt {attempt + 1}/{max_retries})...")
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                temp_files.append(temp_audio.name)
                temp_audio.write(response.content)
                temp_audio.close()
                return temp_audio.name
            
            # If system is busy, implement exponential backoff
            if response.status_code == 429 or "system_busy" in response.text:
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"System busy. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
            
            # For other errors, raise exception immediately
            print(f"Error response: {response.text}")
            raise Exception(f"ElevenLabs API error: {response.text}")
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Network error. Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            raise Exception(f"Network error after {max_retries} attempts: {str(e)}")
    
    raise Exception(f"Failed to generate audio after {max_retries} attempts. System may be too busy.")

def get_voice_ids(api_key):
    try:
        print("\nFetching voices from ElevenLabs...")
        voice_map = {}
        headers = {"xi-api-key": api_key}
        
        # Initialize hardcoded voice IDs
        hardcoded_voices = {
            'adam': 'pNInz6obpgDQGcFmaJgB',    # Adam Legacy
            'antoni': 'ErXwobaYiN019PkySvjV',   # Antoni hardcoded ID
            'jessica': 'cgSgspJ2msm6clMCkdW9',  # Jessica from your list
            'brian': 'nPczCjzI2devNBz1zQrb',    # Brian from your list
            'laura': 'FGY2WhTYpPnrIDTdsKH5'     # Laura from your list
        }
        
        # Get regular voices
        response = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch voices: {response.text}")
            
        voices = response.json()
        
        print("\nAvailable voices in ElevenLabs:")
        for voice in voices["voices"]:
            print(f"Name: {voice['name']}, ID: {voice['voice_id']}")
            name_lower = voice['name'].lower()
            
            # Map voices based on their names
            if 'adam' in name_lower:
                voice_map['adam'] = voice['voice_id']
                print(f"Found Adam voice: {voice['name']}")
            elif 'jessica' in name_lower:
                voice_map['jessica'] = voice['voice_id']
                print(f"Found Jessica voice: {voice['name']}")
            elif 'brian' in name_lower:
                voice_map['brian'] = voice['voice_id']
                print(f"Found Brian voice: {voice['name']}")
            elif 'laura' in name_lower:
                voice_map['laura'] = voice['voice_id']
                print(f"Found Laura voice: {voice['name']}")
        
        # Use hardcoded IDs for missing voices
        for voice_name, voice_id in hardcoded_voices.items():
            if voice_name not in voice_map:
                voice_map[voice_name] = voice_id
                print(f"Using hardcoded {voice_name.capitalize()} voice ID: {voice_id}")
        
        print("\nFinal voice map:", voice_map)
        
        # Update required voices list
        required_voices = ['adam', 'antoni', 'jessica', 'brian', 'laura']
        missing_voices = [voice for voice in required_voices if voice not in voice_map]
        
        if missing_voices:
            all_voices = "\nAll available voices:\n" + "\n".join([f"- {v['name']} ({v['voice_id']})" for v in voices["voices"]])
            raise Exception(f"Missing required voices: {', '.join(missing_voices)}.{all_voices}")
        
        return voice_map
        
    except Exception as e:
        print(f"Error fetching voice IDs: {str(e)}")
        raise

def generate_video(messages, header_data):
    try:
        # Get voice settings from header data
        voice_settings = header_data.get('voiceSettings', {})
        api_key = voice_settings.get('apiKey')
        
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
            
        # Fetch voice IDs
        voice_map = get_voice_ids(api_key)
        
        if not voice_map:
            raise ValueError("No voices found in your ElevenLabs account")
        
        # Map 'male'/'female' to specific voices
        gender_to_voice = {
            'male': 'adam',  # Map 'male' to 'adam'
            'female': 'jessica',  # Map 'female' to 'jessica'
            'brian': 'brian',
            'laura': 'laura',
            'antoni': 'antoni'
        }
            
        # Get selected voice types and map them to specific voices
        sender_type = voice_settings.get('sender', 'male').lower()
        receiver_type = voice_settings.get('receiver', 'female').lower()
        
        # Convert gender to specific voice names
        sender_voice = gender_to_voice.get(sender_type, sender_type)
        receiver_voice = gender_to_voice.get(receiver_type, receiver_type)
        
        # Get corresponding voice IDs
        sender_voice_id = voice_map.get(sender_voice)
        receiver_voice_id = voice_map.get(receiver_voice)
        
        if not sender_voice_id or not receiver_voice_id:
            raise ValueError(f"Could not find voice IDs for sender ({sender_type} -> {sender_voice}) or receiver ({receiver_type} -> {receiver_voice}). Available voices: {voice_map}")
        
        print(f"Using voice IDs - Sender: {sender_voice_id}, Receiver: {receiver_voice_id}")
        
        # Cloudinary video URLs (updated with working URLs)
        CLOUDINARY_VIDEOS = {
            'background': 'https://res.cloudinary.com/dokndhglh/video/upload/c_scale,h_1080,q_100/v1739342327/h3mqdaupaop1eprdcld3.mp4',
            'background_1': 'https://res.cloudinary.com/dokndhglh/video/upload/c_scale,h_1080,q_100/v1739342660/f1bhluhc6si77uapdawe_slowed_oq2v20.mp4',
            'background_2': 'https://res.cloudinary.com/dokndhglh/video/upload/c_scale,h_1080,q_100/v1739343309/dxo2rlb7kckps0fnfvv4_slowed_mmptbq.mp4',
            'background_3': 'https://res.cloudinary.com/dokndhglh/video/upload/c_scale,h_1080,q_100/v1739343390/pytgss2oi9idgch1xhrw_slowed_ku8hde.mp4',
            'background_4': 'https://res.cloudinary.com/dokndhglh/video/upload/v1739599641/Minecraft_Jump_and_Run_Gameplay_TIKTOK_Format_60fps_1440p_HD_No_Ads_No_Credits_3_-_Minecraft_Gameplay_1080p_h264_mute_youtube_online-video-cutter.com_1_eprmyf.mp4'
        }
        
        # Get the selected background video
        selected_bg = header_data.get('backgroundVideo', 'background')
        bg_url = CLOUDINARY_VIDEOS.get(selected_bg)
        
        if not bg_url:
            raise ValueError(f"Invalid background video: {selected_bg}")

        print(f"Downloading background video from: {bg_url}")
        
        # Download the video using requests with retry logic
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Attempt the download up to 3 times
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(bg_url, stream=True, headers=headers, timeout=30)
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    block_size = 8192
                    downloaded = 0
                    
                    for chunk in response.iter_content(chunk_size=block_size):
                        if chunk:
                            downloaded += len(chunk)
                            temp_video.write(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\rDownloading background video: {percent:.1f}%", end='')
                    
                    print("\nDownload completed successfully")
                    break
                except requests.exceptions.RequestException as e:
                    print(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to download video after {max_retries} attempts: {str(e)}")
                    print("Retrying download...")
                    time.sleep(5)
            
            temp_video_path = temp_video.name
            temp_files.append(temp_video_path)

        # Load the background video and get its duration
        background = VideoFileClip(temp_video_path, audio=False)
        
        # Calculate total duration needed for all messages
        video_clips = []
        audio_clips = []
        total_duration = 0
        
        # First pass to calculate total duration needed
        for i in range(0, len(messages), 5):
            sequence = messages[i:i+5]
            for j in range(len(sequence)):
                msg = sequence[j]
                if msg.get('type') == 'text':
                    # Estimate audio duration
                    voice_id = sender_voice_id if msg['is_sender'] else receiver_voice_id
                    audio_path = generate_audio_eleven_labs(msg['text'], voice_id, api_key)
                    voice_audio = AudioFileClip(audio_path)
                    
                    if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                        effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                        clip_duration = max(voice_audio.duration + 0.1, effect_audio.duration)
                    else:
                        clip_duration = voice_audio.duration
                        
                    total_duration += clip_duration + 0.09
                else:  # Picture message
                    if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                        effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                        total_duration += effect_audio.duration + 0.04
                    else:
                        total_duration += 0.54  # Default duration for picture messages

        # Choose a random start point that ensures we have enough video duration
        max_start_time = max(0, background.duration - total_duration - 1)  # -1 for safety margin
        if max_start_time > 0:
            start_time = np.random.uniform(0, max_start_time)
            print(f"\nChose random start time: {start_time:.2f} seconds")
            background = background.subclip(start_time)
        
        current_time = 0
        message_count = 0

        # Process messages in sequences of 5
        for i in range(0, len(messages), 5):
            sequence = messages[i:i+5]
            
            for j in range(len(sequence)):
                current_window = sequence[:j+1]
                message_count += 1
                
                msg = sequence[j]
                
                # Handle text messages with voice over
                if msg.get('type') == 'text':
                    voice_id = sender_voice_id if msg['is_sender'] else receiver_voice_id
                    audio_path = generate_audio_eleven_labs(msg['text'], voice_id, api_key)
                    voice_audio = AudioFileClip(audio_path)
                    
                    # Add sound effect if specified
                    if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                        print(f"Adding sound effect: {msg['soundEffect']}")
                        effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                        # Combine voice and effect (effect plays slightly before voice)
                        combined_audio = CompositeAudioClip([
                            effect_audio.with_start(0),
                            voice_audio.with_start(0.1)  # Slight delay for voice
                        ])
                        audio_duration = max(voice_audio.duration + 0.1, effect_audio.duration)
                    else:
                        combined_audio = voice_audio
                        audio_duration = voice_audio.duration
                    
                    clip_duration = audio_duration + 0.09  # Reduced pause between messages
                
                # Handle picture messages with sound effects only
                elif msg.get('type') == 'picture':
                    if msg.get('soundEffect') and msg['soundEffect'] in SOUND_EFFECTS:
                        print(f"Adding sound effect: {msg['soundEffect']}")
                        effect_audio = AudioFileClip(SOUND_EFFECTS[msg['soundEffect']])
                        combined_audio = effect_audio
                        audio_duration = effect_audio.duration
                    else:
                        combined_audio = None
                        audio_duration = 0.5  # Default duration for picture messages
                    
                    clip_duration = audio_duration + 0.04
                
                # Show header only for the first five messages
                show_header = (message_count <= 5)
                
                # Capture current chat interface
                current_image = capture_chat_interface(current_window, show_header=show_header, header_data=header_data)
                if current_image is None:
                    print(f"Failed to capture chat interface for message {i + 1}")
                    continue

                # Resize image to fit the background
                target_width = int(background.w * 0.85)
                width_scale = target_width / current_image.width
                new_height = int(current_image.height * width_scale)
                current_image = current_image.resize((target_width, new_height), Image.LANCZOS)
                current_array = np.array(current_image)

                # Calculate position to center
                x_center = background.w // 2 - target_width // 2
                y_top = background.h // 8  # Position moved higher
                
                # Create clip for current message state
                current_clip = (ImageClip(current_array)
                                .with_duration(clip_duration)
                                .with_position((x_center, y_top)))
                
                video_clips.append(current_clip.with_start(current_time))
                if combined_audio:
                    audio_clips.append(combined_audio.with_start(current_time))

                current_time += clip_duration

        if not video_clips:
            raise Exception("No valid messages to generate video.")

        if current_time > background.duration:
            n_loops = int(np.ceil(current_time / background.duration))
            bg_clips = [background] * n_loops
            background_extended = concatenate_videoclips(bg_clips)
            background_extended = background_extended.subclipped(0, current_time)
        else:
            background_extended = background.subclipped(0, current_time)

        final = CompositeVideoClip(
            [background_extended] + video_clips,
            size=background_extended.size
        )

        if audio_clips:
            final = final.with_audio(CompositeAudioClip(audio_clips))

        output_path = "output_video.mp4"
        final.write_videofile(output_path, 
                            fps=60,                    # Increased to 60fps for smoothness
                            codec='libx264',
                            audio_codec='aac',
                            bitrate="20000k",          # Increased bitrate for quality
                            preset='slow',             # 'slow' gives better quality than 'slower'
                            threads=4,
                            audio_bitrate="320k",      # Higher audio quality
                            ffmpeg_params=[
                                '-crf', '17',          # Lower CRF for higher quality (17-18 is very high quality)
                                '-pix_fmt', 'yuv420p', # Best compatibility
                                '-profile:v', 'high',  # High profile for better quality
                                '-movflags', '+faststart'
                            ])
        
        return output_path
        
    except Exception as e:
        print(f"Error generating video: {str(e)}")
        traceback.print_exc()
        raise

def cleanup_temp_files():
    for file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            print(f"Warning: Error cleaning up {file_path}: {e}")

def log_video_info(video_path):
    try:
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        print(f"\nVideo Information:")
        print(f"Path: {video_path}")
        print(f"Size: {size_mb:.2f} MB")
        clip = VideoFileClip(video_path)
        print(f"Duration: {clip.duration:.2f} seconds")
        print(f"FPS: {clip.fps}")
        print(f"Size: {clip.size}")
        clip.close()
    except Exception as e:
        print(f"Error logging video info: {e}")

@app.route('/api/validate-key', methods=['POST'])
def validate_key():
    try:
        data = request.json
        api_key = data.get('apiKey')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
            
        # Test the API key with ElevenLabs
        response = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key}
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Invalid API key'}), 401
            
        return jsonify({'status': 'success', 'message': 'API key is valid'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def generate_endpoint():
    try:
        data = request.json
        messages = data['messages']
        
        # Get voice settings and validate API key
        voice_settings = data.get('voiceSettings', {})
        api_key = voice_settings.get('apiKey')
        
        if not api_key:
            return jsonify({
                'status': 'error',
                'error': 'ElevenLabs API key is required'
            }), 400
        
        # Create header_data dictionary
        header_data = {
            'profileImage': data.get('profileImage', ''),
            'headerName': data.get('headerName', 'John Doe'),
            'voiceSettings': voice_settings,
            'backgroundVideo': data.get('backgroundVideo', 'background'),
            'theme': data.get('theme', 'light')
        }
        
        # Generate the initial video
        print("\nGenerating initial video...")
        video_path = generate_video(messages, header_data)
        log_video_info(video_path)
        
        # Enhance video quality using AI
        print("\nEnhancing video quality with AI...")
        enhanced_video_path = "enhanced_" + os.path.basename(video_path)
        if enhance_video_quality(video_path, enhanced_video_path):
            print("Using AI-enhanced video for further processing")
            # Replace original video with enhanced version
            shutil.move(enhanced_video_path, video_path)
        else:
            print("Warning: AI enhancement failed, using original video")
        
        # Upload original video to Google Drive
        print("\nUploading enhanced video to Google Drive...")
        drive_result = upload_to_drive(video_path, 'output_video.mp4')
        
        # Initialize response data
        response_data = {
            'status': 'success',
            'message': 'Video generated, enhanced, and processed successfully',
            'original_video_id': drive_result.get('id', ''),
            'original_video_link': f"https://drive.google.com/file/d/{drive_result.get('id', '')}/view?usp=drivesdk",
            'spedup_video_id': '',
            'spedup_video_link': ''
        }

        # Run the speed-up script
        try:
            print("\nStarting video speed-up process...")
            subprocess.run(['python', 'speed_up_video.py'], check=True)
            
            if os.path.exists('spedup_outputvideo.mp4'):
                # Enhance the sped-up video as well
                print("\nEnhancing sped-up video quality with AI...")
                enhanced_spedup_path = "enhanced_spedup_outputvideo.mp4"
                if enhance_video_quality('spedup_outputvideo.mp4', enhanced_spedup_path):
                    print("Using AI-enhanced sped-up video")
                    shutil.move(enhanced_spedup_path, 'spedup_outputvideo.mp4')
                else:
                    print("Warning: AI enhancement of sped-up video failed, using original")
                
                print("\nUploading enhanced sped-up video to Google Drive...")
                spedup_drive_result = upload_to_drive('spedup_outputvideo.mp4', 'spedup_outputvideo.mp4')
                
                response_data.update({
                    'spedup_video_id': spedup_drive_result.get('id', ''),
                    'spedup_video_link': f"https://drive.google.com/file/d/{spedup_drive_result.get('id', '')}/view?usp=drivesdk"
                })
                
                # Handle Discord webhook if URL is provided
                discord_webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
                if discord_webhook_url:
                    try:
                        # Send original video link
                        webhook_data = {
                            'content': f"🎥 **New video generated by {header_data['headerName']}**\n\n" \
                                     f"📝 **Original Video**\n" \
                                     f"🔗 Drive Link: {drive_result['link']}\n\n" \
                                     f"⏱️ **Sped-up Version (1.75x)**\n" \
                                     f"🔗 Drive Link: {spedup_drive_result['link']}"
                        }
                        
                        response = requests.post(discord_webhook_url, json=webhook_data)
                        if response.status_code != 204:
                            print(f"Warning: Discord webhook returned status code {response.status_code}")
                            
                    except Exception as webhook_error:
                        print(f"Warning: Error sending to Discord webhook: {str(webhook_error)}")
                
                # Clean up temporary files
                try:
                    if os.path.exists('output_video.mp4'):
                        os.remove('output_video.mp4')
                    if os.path.exists('spedup_outputvideo.mp4'):
                        os.remove('spedup_outputvideo.mp4')
                    print("\nTemporary files cleaned up")
                except Exception as e:
                    print(f"Warning: Error cleaning up temporary files: {str(e)}")
                    
        except Exception as e:
            print(f"Error in speed-up process: {str(e)}")
            response_data['message'] = f"Video generated and enhanced but speed-up failed: {str(e)}"

        print("\nProcess completed successfully!")
        return jsonify(response_data)

    except Exception as e:
        print(f"Error in generate endpoint: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/fetch-voices', methods=['POST'])
def fetch_voices():
    try:
        data = request.json
        api_key = data.get('apiKey')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
            
        response = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key}
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch voices'}), response.status_code
            
        voices = response.json()
        voice_list = [{'name': voice['name'], 'id': voice['voice_id']} 
                     for voice in voices['voices']]
                     
        return jsonify(voice_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search-images')
def search_images():
    try:
        query = request.args.get('q')
        page = request.args.get('page', '1')  # Get page number, default to 1
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400

        if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
            return jsonify({'error': 'Google API configuration is missing'}), 500

        # Calculate start index for pagination (1, 11, 21, etc.)
        # Google CSE allows max 10 results per request
        start_index = (int(page) - 1) * 10 + 1

        # Make request to Google Custom Search API
        url = 'https://www.googleapis.com/customsearch/v1'
        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CSE_ID,
            'q': query,
            'searchType': 'image',
            'num': 10,  # Maximum allowed by Google CSE
            'start': start_index,
            'imgSize': 'medium',  # Get medium sized images
            'safe': 'active'  # Safe search setting
        }

        response = requests.get(url, params=params)
        data = response.json()

        if 'items' not in data:
            return jsonify({'error': 'No images found'}), 404

        # Extract relevant image information
        images = [{
            'url': item['link'],
            'title': item['title'],
            'thumbnail': item.get('image', {}).get('thumbnailLink', item['link']),
            'context': item.get('image', {}).get('contextLink', ''),  # Add source context
            'height': item.get('image', {}).get('height', ''),
            'width': item.get('image', {}).get('width', '')
        } for item in data['items']]

        # Add pagination info
        response_data = {
            'images': images,
            'currentPage': int(page),
            'hasMore': 'queries' in data and 'nextPage' in data['queries'],
            'totalResults': min(int(data.get('searchInformation', {}).get('totalResults', 0)), 100)  # Google CSE limits to 100
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in image search: {str(e)}")
        return jsonify({'error': 'Failed to search images'}), 500

def enhance_video_quality(input_path, output_path):
    """Optimize video quality while maintaining clarity and sharpness"""
    try:
        print("\nOptimizing video quality...")
        
        # Extract video info
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate',
            '-of', 'json',
            input_path
        ]
        
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        video_info = json.loads(probe_result.stdout)
        
        # Calculate target resolution (1080p)
        target_height = 1080
        current_height = int(video_info['streams'][0]['height'])
        scale_factor = target_height / current_height
        
        # Calculate target width and ensure it's even
        raw_target_width = int(int(video_info['streams'][0]['width']) * scale_factor)
        target_width = raw_target_width + (raw_target_width % 2)  # Make sure width is even
        
        print(f"Processing video to {target_width}x{target_height}")
        
        # Simple, high-quality scaling without aggressive filters
        complex_filter = (
            f"scale={target_width}:{target_height}:flags=lanczos"
        )
        
        # High quality encoding settings focused on preserving quality
        enhance_cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', complex_filter,
            '-c:v', 'libx264',
            '-preset', 'medium',     # Balance between quality and speed
            '-crf', '18',           # High quality, visually lossless
            '-maxrate', '15M',
            '-bufsize', '15M',
            '-profile:v', 'high',
            '-level', '4.1',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-b:a', '256k',
            '-ar', '48000',
            '-y',
            output_path
        ]
        
        print("\nProcessing video with optimized settings...")
        subprocess.run(enhance_cmd, check=True)
        
        print("Video processing completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during video processing: {str(e)}")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    # Run Flask on all interfaces with port 8080 for Google Cloud
    app.run(debug=True, host='0.0.0.0', port=8080)