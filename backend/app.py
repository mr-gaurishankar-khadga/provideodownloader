import os
import uuid
import logging
import subprocess
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Clean up filename to prevent potential issues"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_')).rstrip()

def convert_to_audio(input_file, output_file):
    """
    Robust audio conversion with multiple fallback strategies
    """
    conversion_strategies = [
        # Primary conversion strategy
        f'ffmpeg -i "{input_file}" -vn -acodec libmp3lame -q:a 2 "{output_file}"',
        
        # Alternate strategy with explicit audio mapping
        f'ffmpeg -i "{input_file}" -map 0:a:0 -acodec libmp3lame "{output_file}"',
        
        # Fallback extraction method
        f'ffmpeg -i "{input_file}" -vn -acodec mp3 -ab 192k "{output_file}"'
    ]

    for strategy in conversion_strategies:
        try:
            subprocess.run(strategy, shell=True, check=True)
            
            # Verify audio file
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                return output_file
        except Exception as e:
            logger.error(f"Conversion attempt failed: {e}")
    
    raise ValueError("Failed to convert audio")

def download_video(url, format_code=None, download_type='video'):
    """
    Enhanced video download with comprehensive error handling
    """
    try:
        os.makedirs('/tmp', exist_ok=True)

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'nooverwrites': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'no_color': True,
            'noplaylist': True,
            'restrictfilenames': True,
            'max_filesize': 2 * 1024 * 1024 * 1024,  # 2GB max
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, extract info to get available formats
            info_dict = ydl.extract_info(url, download=False)
            
            # If a specific format is requested, verify it exists
            if format_code:
                available_formats = [f['format_id'] for f in info_dict.get('formats', [])]
                if format_code not in available_formats:
                    # Fall back to best available format
                    format_code = None

            # Update format if not specified
            if not format_code:
                ydl_opts['format'] = 'bestvideo+bestaudio/best'

            # Perform download
            info_dict = ydl.extract_info(url, download=True)
            
            title = sanitize_filename(info_dict.get('title', 'video'))
            filename = ydl.prepare_filename(info_dict)

            if download_type == 'audio':
                audio_filename = os.path.join('/tmp', f'{title}_{uuid.uuid4()}.mp3')
                
                # Try converting video to audio
                try:
                    converted_audio = convert_to_audio(filename, audio_filename)
                except Exception as audio_error:
                    logger.error(f"Audio conversion failed: {audio_error}")
                    # Attempt direct audio extraction if conversion fails
                    subprocess.run(f'ffmpeg -i "{filename}" -vn -acodec libmp3lame "{audio_filename}"', shell=True, check=True)
                
                # Clean up original file
                if os.path.exists(filename):
                    os.remove(filename)
                
                return audio_filename

            return filename

    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

def get_video_info(url):
    """
    Comprehensive video information extraction
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            
            formats = info_dict.get('formats', [])
            options = []
            unique_resolutions = set()

            for f in formats:
                height = f.get('height')
                ext = f.get('ext')
                
                if height and ext and height not in unique_resolutions and height >= 360:
                    filesize = f.get('filesize_approx') or f.get('filesize') or 'Unknown'
                    if filesize != 'Unknown':
                        filesize = f"{filesize / (1024*1024):.2f} MB"

                    options.append({
                        'resolution': f'{height}p',
                        'format': ext,
                        'filesize': filesize,
                        'format_id': f.get('format_id')
                    })
                    unique_resolutions.add(height)

            options.sort(key=lambda x: int(x['resolution'][:-1]), reverse=True)
            
            return options

    except Exception as e:
        logger.error(f"Video info error: {e}")
        return []

@app.route('/analyze-video', methods=['POST'])
def analyze_video():
    url = request.json.get('url')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        options = get_video_info(url)
        return jsonify({'options': options})
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({'error': 'Failed to analyze video'}), 500

@app.route('/download', methods=['POST'])
def download():
    url = request.json.get('url')
    format_type = request.json.get('format')
    download_type = request.json.get('type', 'video')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        filename = download_video(url, format_type, download_type)
        
        if not filename or not os.path.exists(filename):
            return jsonify({'error': 'Download failed'}), 500

        return send_file(filename, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)