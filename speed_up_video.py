import subprocess
import os
from datetime import datetime

def speed_up_video(input_video='output_video.mp4', output_video='spedup_outputvideo.mp4', speed_factor=1.5):
    """Speed up a video using FFmpeg with enhanced smoothness settings"""
    try:
        # Print timestamp and user info
        print(f"Current Date and Time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Current User's Login: ItzSteveefr")
        print(f"\nStarting video speed-up process...")

        # Enhanced FFmpeg command for smoother playback
        ffmpeg_command = [
            'ffmpeg',
            '-i', input_video,
            '-filter_complex',
            # Use minterpolate filter for smoother motion
            f'[0:v]minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1[v1];'
            f'[v1]setpts={1/speed_factor}*PTS[v];'
            f'[0:a]atempo={speed_factor}[a]',
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '18',
            '-tune', 'film',
            '-profile:v', 'high',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-r', '60',  # Force 60fps output
            '-maxrate', '12M',
            '-bufsize', '24M',
            '-y',
            output_video
        ]
        
        print("Processing video with enhanced smoothness settings...")
        subprocess.run(ffmpeg_command, check=True)
        
        # Get and display file sizes
        original_size = os.path.getsize(input_video) / (1024 * 1024)  # Convert to MB
        new_size = os.path.getsize(output_video) / (1024 * 1024)  # Convert to MB
        
        print(f"\nSuccess! Video processing complete.")
        print(f"\nFile sizes:")
        print(f"Original: {original_size:.2f} MB")
        print(f"Sped-up version: {new_size:.2f} MB")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while processing the video: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    # Clean up spedup video if it exists
    if os.path.exists('spedup_outputvideo.mp4'):
        try:
            os.remove('spedup_outputvideo.mp4')
            print("Cleaned up previous spedup video")
        except Exception as e:
            print(f"Error cleaning up previous spedup video: {e}")
    
    speed_up_video()