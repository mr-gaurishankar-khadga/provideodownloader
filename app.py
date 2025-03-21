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
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dictionary to store file paths with their UUID
downloaded_files = {}
# Dictionary to store download progress
download_tasks = {}

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

@app.route('/api/info', methods=['POST'])
def get_video_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    try:
        # Define options for yt-dlp to extract info
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,
            'format': 'best',
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
            
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats,
                'platform': info.get('extractor', 'unknown').replace('_', ' ').title(),
                'view_count': info.get('view_count'),
                'upload_date': upload_date
            })
    
    except Exception as e:
        logger.error(f"Error extracting info: {str(e)}")
        return jsonify({"error": f"Could not fetch video information: {str(e)}"}), 500

def download_worker(task_id, url, format_id):
    """Background worker for downloading videos"""
    try:
        # Create a unique filename
        file_id = task_id
        output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
        
        # Define options for yt-dlp to download
        ydl_opts = {
            'format': format_id,
            'outtmpl': output_template,
            'progress_hooks': [ProgressHook(task_id)],
            'quiet': False,
            'no_warnings': True,
            'retries': 5,  # Retry 5 times
            'fragment_retries': 5,
            'ignoreerrors': False,
        }
        
        # Update task status
        download_tasks[task_id]['status'] = 'downloading'
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading: {url} with format {format_id}")
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # Check if file exists
            if not os.path.exists(downloaded_file):
                download_tasks[task_id]['status'] = 'failed'
                download_tasks[task_id]['error'] = 'File not found after download'
                return
            
            # Get safe filename
            filename = clean_filename(info.get('title', 'video'))
            extension = os.path.splitext(downloaded_file)[1]
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
            'created': time.time()
        }
        
        # Start download in background
        thread = threading.Thread(
            target=download_worker,
            args=(task_id, url, format_id)
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
        return send_file(
            file_info['path'], 
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"Error serving file: {str(e)}")
        return jsonify({"error": f"Error serving file: {str(e)}"}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "ok",
        "version": "2.0.0",
        "yt_dlp_version": yt_dlp.version.__version__
    })

# Cleanup function to prevent filling up disk space
def cleanup_old_files():
    """Remove old files (older than 2 hours)"""
    current_time = time.time()
    expiry_time = 7200  # 2 hours in seconds
    
    # Clean up downloaded files
    for file_id, file_info in list(downloaded_files.items()):
        if current_time - file_info['created'] > expiry_time:
            file_path = file_info['path']
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Removed old file: {file_path}")
                except Exception as e:
                    logger.error(f"Error removing file {file_path}: {str(e)}")
            downloaded_files.pop(file_id, None)
    
    # Clean up task records
    for task_id, task_info in list(download_tasks.items()):
        if current_time - task_info['created'] > expiry_time:
            download_tasks.pop(task_id, None)

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

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)