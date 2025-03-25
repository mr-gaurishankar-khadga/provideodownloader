import os
import uuid
import logging
import subprocess
from flask import Flask, request, send_file, jsonify, abort
from flask_cors import CORS
import yt_dlp

# Ensure /tmp directory exists and is writable
os.makedirs('/tmp', exist_ok=True)

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Add near the app configuration
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max payload

# Modify logging to be more production-friendly
logging.basicConfig(
    level=logging.ERROR,  # Change to ERROR for production
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/app.log', mode='a')
    ]
)
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
            subprocess.run(strategy, shell=True, check=True, capture_output=True)
            
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
        ydl_opts = {
            'format': format_code or 'bestvideo+bestaudio/best',
            'nooverwrites': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'no_color': True,
            'noplaylist': True,
            'restrictfilenames': True,
            'max_filesize': 2 * 1024 * 1024 * 1024,  # 2GB max
            'outtmpl': '/tmp/%(title)s_%(id)s.%(ext)s'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, extract info to get available formats
            info_dict = ydl.extract_info(url, download=False)
            
            # Validate URL
            if not info_dict:
                raise ValueError("Unable to extract video information")

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
                    try:
                        subprocess.run(f'ffmpeg -i "{filename}" -vn -acodec libmp3lame "{audio_filename}"', 
                                       shell=True, check=True, capture_output=True)
                    except Exception as e:
                        logger.error(f"Direct audio extraction failed: {e}")
                        raise
                
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
            'quiet': False,
            'no_warnings': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            
            # Validate URL
            if not info_dict:
                raise ValueError("Unable to extract video information")
            
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
        logger.error(f"Video info error: {str(e)}")
        return []

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok", 
        "message": "ProVideoDownloader is running"
    }), 200

@app.route('/analyze-video', methods=['POST'])
def analyze_video():
    """Analyze video endpoint"""
    try:
        url = request.json.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        options = get_video_info(url)
        
        if not options:
            return jsonify({'error': 'Unable to extract video information'}), 404

        return jsonify({'options': options})
    
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return jsonify({'error': 'Failed to analyze video'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Download video/audio endpoint"""
    try:
        url = request.json.get('url')
        format_type = request.json.get('format')
        download_type = request.json.get('type', 'video')

        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        filename = download_video(url, format_type, download_type)
        
        if not filename or not os.path.exists(filename):
            return jsonify({'error': 'Download failed'}), 500

        return send_file(filename, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Global error handler
@app.errorhandler(Exception)
def handle_global_error(e):
    """Global error handler for unhandled exceptions"""
    logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({"error": "Internal Server Error"}), 500

# Cleanup temporary files before shutdown
def cleanup_temp_files():
    """Clean up temporary files in /tmp directory"""
    for filename in os.listdir('/tmp'):
        filepath = os.path.join('/tmp', filename)
        try:
            if os.path.isfile(filepath) and filepath.startswith('/tmp'):
                os.unlink(filepath)
        except Exception as e:
            logger.error(f"Error removing {filepath}: {e}")




def get_video_info(url):
    """
    Comprehensive video information extraction with robust error handling
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'no_color': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info_dict = ydl.extract_info(url, download=False)
            except Exception as e:
                logger.error(f"Video extraction failed: {str(e)}")
                return []

            # Validate URL and video availability
            if not info_dict or 'formats' not in info_dict:
                logger.error(f"Unable to extract video information for URL: {url}")
                return []
            
            formats = info_dict.get('formats', [])
            options = []
            unique_resolutions = set()

            for f in formats:
                height = f.get('height', 0)
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

            # Sort options by resolution
            options.sort(key=lambda x: int(x['resolution'][:-1]), reverse=True)
            
            return options

    except Exception as e:
        logger.error(f"Unexpected error in video info: {str(e)}")
        return []


# Register cleanup function
import atexit
atexit.register(cleanup_temp_files)

if __name__ == '__main__':
    app.run(
        host='0.0.0.0', 
        port=int(os.environ.get('PORT', 5000)), 
        debug=False
    )