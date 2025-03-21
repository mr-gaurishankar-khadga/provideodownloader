from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp
import os
import uuid
import tempfile
import logging
import threading
import time
import json
import re
import subprocess
import hashlib
from datetime import datetime
import urllib3

app = Flask(__name__)
CORS(app)

# Configure connection pooling
urllib3.PoolManager(maxsize=10)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dictionary to store file paths with their UUID
downloaded_files = {}
# Dictionary to store download progress
download_tasks = {}
# Cache for video info
video_info_cache = {}
CACHE_TTL = 600  # 10 minutes

# Create download directory if it doesn't exist
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), 'video_downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class ProgressHook:
    def __init__(self, task_id):
        self.task_id = task_id
        
    def __call__(self, d):
        if d['status'] == 'downloading':
            # Extract download progress
            if 'total_bytes' in d and d['total_bytes'] > 0:
                percentage = (d['downloaded_bytes'] / d['total_bytes']) * 100
            elif 'total_bytes_estimate' in d and d['total_bytes_estimate'] > 0:
                percentage = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
            else:
                # If we can't calculate percentage, use downloaded MB as indication
                percentage = min(d['downloaded_bytes'] / 1048576, 100)  # 1MB increments up to 100
            
            download_tasks[self.task_id]['progress'] = round(percentage, 1)
            download_tasks[self.task_id]['eta'] = d.get('eta')
            download_tasks[self.task_id]['speed'] = d.get('speed')
            
        elif d['status'] == 'finished':
            download_tasks[self.task_id]['progress'] = 100
            download_tasks[self.task_id]['status'] = 'processing'
        
        elif d['status'] == 'error':
            download_tasks[self.task_id]['status'] = 'failed'
            download_tasks[self.task_id]['error'] = d.get('error', 'Download failed')

def format_date(date_str):
    """Convert YYYYMMDD to readable format"""
    if not date_str or len(date_str) != 8:
        return None
    try:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    except:
        return None

def clean_filename(title):
    """Clean up filenames to be safe for all operating systems"""
    if not title:
        return "video"
    # Replace invalid characters with underscore
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', title)
    # Limit length
    return cleaned[:100]

def convert_to_mp3(input_file, title=None):
    """Convert video file to MP3 audio using FFmpeg"""
    try:
        # Generate an output filename based on the input file
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}.mp3"
        
        # If FFmpeg is installed, use it for better quality conversion
        try:
            # Build a proper filename for the MP3
            safe_title = clean_filename(title) if title else os.path.basename(base_name)
            
            # Run FFmpeg command with optimized parameters
            cmd = [
                'ffmpeg',
                '-i', input_file,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '192k',  # Bitrate
                '-ar', '44100',  # Sample rate
                '-threads', '4',  # Use multiple threads for faster conversion
                '-preset', 'ultrafast',  # Use fastest encoding preset
                '-y',  # Overwrite output files
                output_file
            ]
            
            logger.info(f"Converting to MP3: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {stderr.decode()}")
                raise Exception("FFmpeg conversion failed")
                
            return output_file
            
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"FFmpeg failed or not found: {str(e)}. Falling back to yt-dlp for extraction.")
            raise
            
    except Exception as e:
        logger.error(f"Error converting to MP3: {str(e)}")
        raise

def convert_with_ffmpeg_stream(url, output_file, format_id, task_id):
    """Use FFmpeg to download and convert in one step"""
    try:
        # First, get the direct media URL from yt-dlp
        with yt_dlp.YoutubeDL({
            'quiet': True, 
            'format': format_id,
            'socket_timeout': 10,
            'nocheckcertificate': True
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_url = info.get('url')
            
            if not direct_url:
                # Fall back to normal download if direct URL extraction fails
                raise Exception("Could not get direct URL")
            
        # Then use FFmpeg to stream directly to MP3
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file
            '-loglevel', 'error',  # Minimal logging
            '-i', direct_url,  # Input URL
            '-vn',  # No video
            '-acodec', 'libmp3lame',
            '-ab', '192k',
            '-ar', '44100',
            '-threads', '4',  # Use multiple threads
            output_file
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Monitor progress by file size
        def monitor_progress():
            while process.poll() is None:
                if os.path.exists(output_file):
                    size = os.path.getsize(output_file)
                    # Estimate progress (imprecise but gives user feedback)
                    if size > 0:
                        download_tasks[task_id]['progress'] = min(95, size / 1048576)  # Size in MB as progress indicator
                time.sleep(0.5)
        
        progress_thread = threading.Thread(target=monitor_progress)
        progress_thread.daemon = True
        progress_thread.start()
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg streaming error: {stderr.decode()}")
            raise Exception(f"FFmpeg error: {stderr.decode()}")
            
        return output_file
    except Exception as e:
        logger.error(f"Streaming conversion error: {str(e)}")
        raise

def get_cache_key(url):
    return hashlib.md5(url.encode()).hexdigest()

@app.route('/api/info', methods=['POST'])
def get_video_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    # Check cache first
    cache_key = get_cache_key(url)
    current_time = time.time()
    
    if cache_key in video_info_cache:
        cache_entry = video_info_cache[cache_key]
        if current_time - cache_entry['timestamp'] < CACHE_TTL:
            return jsonify(cache_entry['data'])
    
    try:
        # Optimized options for yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': True,  # Only extract basic info initially
            'format': 'best',
            'socket_timeout': 10,  # Reduce socket timeouts
            'nocheckcertificate': True,  # Skip SSL cert verification
        }
        
        # Extract info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting info for: {url}")
            info = ydl.extract_info(url, download=False)
            
            # Filter and format the response
            formats = []
            for format in info.get('formats', []):
                # Include more format details
                format_data = {
                    'format_id': format.get('format_id'),
                    'ext': format.get('ext'),
                    'resolution': format.get('resolution', 'unknown'),
                    'filesize': format.get('filesize'),
                    'filesize_approx': format.get('filesize_approx'),
                    'format_note': format.get('format_note', ''),
                    'vcodec': format.get('vcodec', 'none'),
                    'acodec': format.get('acodec', 'none'),
                    'width': format.get('width'),
                    'height': format.get('height'),
                    'fps': format.get('fps'),
                }
                formats.append(format_data)
            
            # Sort formats by quality
            formats.sort(key=lambda x: (x.get('height') or 0, x.get('filesize') or x.get('filesize_approx') or 0), reverse=True)
            
            # Format upload date
            upload_date = format_date(info.get('upload_date'))
            
            # Prepare result
            result = {
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats,
                'platform': info.get('extractor', 'unknown').replace('_', ' ').title(),
                'view_count': info.get('view_count'),
                'upload_date': upload_date
            }
            
            # Store in cache
            video_info_cache[cache_key] = {
                'timestamp': current_time,
                'data': result
            }
            
            return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error extracting info: {str(e)}")
        return jsonify({"error": f"Could not fetch video information: {str(e)}"}), 500

def download_worker(task_id, url, format_id, convert_to_mp3_flag=False):
    """Background worker for downloading videos"""
    try:
        # Create a unique filename
        file_id = task_id
        output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
        
        # Try direct streaming for mp3 conversion
        if convert_to_mp3_flag and not download_tasks[task_id].get('convert_with_ytdlp', False):
            try:
                download_tasks[task_id]['status'] = 'downloading'
                mp3_output = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp3")
                
                convert_with_ffmpeg_stream(url, mp3_output, format_id, task_id)
                
                # Get info for filename
                with yt_dlp.YoutubeDL({'quiet': True, 'socket_timeout': 5}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    filename = clean_filename(info.get('title', 'audio'))
                
                # Store the file info
                downloaded_files[file_id] = {
                    'path': mp3_output,
                    'filename': f"{filename}.mp3",
                    'created': time.time()
                }
                
                # Update task status
                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['progress'] = 100
                download_tasks[task_id]['file_url'] = f"/api/files/{file_id}"
                download_tasks[task_id]['filename'] = f"{filename}.mp3"
                
                return
            except Exception as e:
                logger.warning(f"Direct streaming failed, falling back to standard download: {str(e)}")
                # Continue with standard download method
        
        # Define optimized options for yt-dlp
        ydl_opts = {
            'format': format_id,
            'outtmpl': output_template,
            'progress_hooks': [ProgressHook(task_id)],
            'quiet': True,
            'no_warnings': True,
            'retries': 3,  # Reduced retries for faster failure
            'fragment_retries': 3,
            'ignoreerrors': False,
            'socket_timeout': 10,
            'nocheckcertificate': True,
            'noprogress': True,  # Disable progress bar for speed
        }
        
        # If we're going to extract audio with yt-dlp directly
        if convert_to_mp3_flag and 'convert_with_ytdlp' in download_tasks[task_id]:
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        
        # Update task status
        download_tasks[task_id]['status'] = 'downloading'
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading: {url} with format {format_id}")
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # If the extension is different due to yt-dlp's postprocessing
            if convert_to_mp3_flag and 'convert_with_ytdlp' in download_tasks[task_id]:
                base_name = os.path.splitext(downloaded_file)[0]
                downloaded_file = f"{base_name}.mp3"
            
            # Check if file exists
            if not os.path.exists(downloaded_file):
                # If mp3 conversion was requested, the extension might be different
                if convert_to_mp3_flag:
                    base_name = os.path.splitext(downloaded_file)[0]
                    possible_mp3 = f"{base_name}.mp3"
                    if os.path.exists(possible_mp3):
                        downloaded_file = possible_mp3
                    else:
                        # Try looking for the original file
                        for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                            possible_file = f"{base_name}{ext}"
                            if os.path.exists(possible_file):
                                downloaded_file = possible_file
                                break
                        else:
                            # Still not found
                            download_tasks[task_id]['status'] = 'failed'
                            download_tasks[task_id]['error'] = 'File not found after download'
                            return
                else:
                    download_tasks[task_id]['status'] = 'failed'
                    download_tasks[task_id]['error'] = 'File not found after download'
                    return
            
            # Get safe filename
            filename = clean_filename(info.get('title', 'video'))
            extension = os.path.splitext(downloaded_file)[1]
            
            # Convert to MP3 if requested and file is not already an MP3
            if convert_to_mp3_flag and extension.lower() != '.mp3' and 'convert_with_ytdlp' not in download_tasks[task_id]:
                try:
                    # Update task status
                    download_tasks[task_id]['status'] = 'converting'
                    download_tasks[task_id]['progress'] = 99  # Show progress is almost done
                    
                    # Convert to MP3
                    mp3_file = convert_to_mp3(downloaded_file, info.get('title'))
                    
                    # Update file info
                    downloaded_file = mp3_file
                    extension = '.mp3'
                except Exception as e:
                    logger.error(f"MP3 conversion error: {str(e)}")
                    # Continue with the original file if conversion fails
                    download_tasks[task_id]['error'] = f"MP3 conversion failed: {str(e)}"
            
            safe_filename = f"{filename}{extension}"
            
            # Store the file info
            downloaded_files[file_id] = {
                'path': downloaded_file,
                'filename': safe_filename,
                'created': time.time()
            }
            
            # Update task status
            download_tasks[task_id]['status'] = 'completed'
            download_tasks[task_id]['progress'] = 100
            download_tasks[task_id]['file_url'] = f"/api/files/{file_id}"
            download_tasks[task_id]['filename'] = safe_filename
            
            logger.info(f"Download completed: {downloaded_file}")
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        download_tasks[task_id]['status'] = 'failed'
        download_tasks[task_id]['error'] = str(e)

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id')
    convert_to_mp3_flag = data.get('convert_to_mp3', False)
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    if not format_id:
        return jsonify({"error": "Format ID is required"}), 400
    
    try:
        # Create a task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task status
        download_tasks[task_id] = {
            'status': 'queued',
            'progress': 0,
            'url': url,
            'format_id': format_id,
            'convert_to_mp3': convert_to_mp3_flag,
            'created': time.time()
        }
        
        # Attempt to use yt-dlp's built-in audio extraction for certain platforms
        if convert_to_mp3_flag and (
            'youtube' in url.lower() or 
            'soundcloud' in url.lower() or
            'vimeo' in url.lower()
        ):
            download_tasks[task_id]['convert_with_ytdlp'] = True
        
        # Start download in background
        thread = threading.Thread(
            target=download_worker,
            args=(task_id, url, format_id, convert_to_mp3_flag)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "task_id": task_id,
            "status": "queued"
        })
        
    except Exception as e:
        logger.error(f"Error starting download: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/progress/<task_id>', methods=['GET'])
def check_progress(task_id):
    """Check the progress of a download task"""
    if task_id not in download_tasks:
        return jsonify({"error": "Task not found"}), 404
    
    task = download_tasks[task_id]
    
    return jsonify(task)

@app.route('/api/files/<file_id>', methods=['GET'])
def serve_file(file_id):
    """Serve downloaded file"""
    # Get the actual file info from our dictionary
    file_info = downloaded_files.get(file_id)
    
    if not file_info or not os.path.exists(file_info['path']):
        return jsonify({"error": "File not found"}), 404
    
    try:
        # Determine the MIME type based on file extension
        mimetype = 'application/octet-stream'
        if file_info['path'].endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif file_info['path'].endswith('.mp4'):
            mimetype = 'video/mp4'
        elif file_info['path'].endswith('.webm'):
            mimetype = 'video/webm'
        
        return send_file(
            file_info['path'], 
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype=mimetype
        )
    except Exception as e:
        logger.error(f"Error serving file: {str(e)}")
        return jsonify({"error": f"Error serving file: {str(e)}"}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "ok",
        "version": "2.1.0",
        "yt_dlp_version": yt_dlp.version.__version__
    })

# Optimized cleanup function to prevent filling up disk space
def cleanup_old_files():
    """Remove old files (older than 2 hours)"""
    current_time = time.time()
    expiry_time = 7200  # 2 hours in seconds
    
    # Batch processing for better performance
    files_to_delete = []
    ids_to_remove = []
    
    # Clean up downloaded files
    for file_id, file_info in list(downloaded_files.items()):
        if current_time - file_info['created'] > expiry_time:
            file_path = file_info['path']
            if os.path.exists(file_path):
                files_to_delete.append(file_path)
            ids_to_remove.append(file_id)
    
    # Batch file deletion
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            logger.info(f"Removed old file: {file_path}")
        except Exception as e:
            logger.error(f"Error removing file {file_path}: {str(e)}")
    
    # Batch dictionary updates
    for file_id in ids_to_remove:
        downloaded_files.pop(file_id, None)
    
    # Clean up task records
    tasks_to_remove = [task_id for task_id, task_info in download_tasks.items() 
                      if current_time - task_info['created'] > expiry_time]
    
    for task_id in tasks_to_remove:
        download_tasks.pop(task_id, None)
    
    # Clean up cache
    cache_keys_to_remove = [k for k, v in video_info_cache.items() 
                           if current_time - v['timestamp'] > CACHE_TTL]
    
    for key in cache_keys_to_remove:
        video_info_cache.pop(key, None)

# Start cleanup thread
def start_cleanup_thread():
    """Start background thread for periodic cleanup"""
    def cleanup_worker():
        while True:
            cleanup_old_files()
            time.sleep(1800)  # Run every 30 minutes
    
    thread = threading.Thread(target=cleanup_worker)
    thread.daemon = True
    thread.start()

# Start cleanup on app startup
start_cleanup_thread()

if __name__ == "__main__":
    # Use a production WSGI server for better performance
    try:
        from waitress import serve
        logger.info("Starting server with Waitress")
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except ImportError:
        logger.info("Waitress not available, using Flask development server")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
