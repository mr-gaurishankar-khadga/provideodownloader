import { useState, useEffect } from 'react';
import './App.css';

// UrlInput Component
function UrlInput({ url, setUrl, onSubmit, isLoading }) {
  const [focused, setFocused] = useState(false);
  
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit();
  };
  
  return (
    <form className="url-input-container" onSubmit={handleSubmit}>
      <div className={`input-wrapper ${focused ? 'focused' : ''}`}>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste video URL here..."
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={isLoading}
        />
        <button type="submit" className="search-button" disabled={isLoading || !url}>
          <span className="button-text">Analyze</span>
          <span className="button-icon">→</span>
        </button>
      </div>
    </form>
  );
}

// VideoPreview Component
function VideoPreview({ title, thumbnail, duration, platform, views, uploadDate }) {
  // Format duration from seconds to MM:SS or HH:MM:SS
  const formatDuration = (seconds) => {
    if (!seconds) return 'Unknown';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };
  
  // Format view count with commas
  const formatViews = (viewCount) => {
    if (!viewCount) return '';
    return new Intl.NumberFormat().format(viewCount);
  };
  
  return (
    <div className="video-preview-container">
      <div className="thumbnail-container">
        <img 
          src={thumbnail || '/placeholder-thumbnail.jpg'} 
          alt={title} 
          className="video-thumbnail"
          onError={(e) => {e.target.src = '/placeholder-thumbnail.jpg'}}
        />
        <div className="duration-badge">{formatDuration(duration)}</div>
        <div className="platform-badge">{platform}</div>
      </div>
      <div className="video-info">
        <h3 className="video-title">{title || 'Untitled Video'}</h3>
        {views && <p className="video-views">{formatViews(views)} views</p>}
        {uploadDate && <p className="video-date">Uploaded: {uploadDate}</p>}
      </div>
    </div>
  );
}

// QualitySelector Component with MP3 Conversion Option
function QualitySelector({ formats, selectedFormat, onChange, convertToMp3, setConvertToMp3 }) {
  if (!formats || formats.length === 0) {
    return <div className="no-formats">No download options available</div>;
  }
  
  // Group formats by type (video, audio, video+audio)
  const groupedFormats = {
    combined: formats.filter(f => f.vcodec !== 'none' && f.acodec !== 'none'),
    videoOnly: formats.filter(f => f.vcodec !== 'none' && f.acodec === 'none'),
    audioOnly: formats.filter(f => f.vcodec === 'none' && f.acodec !== 'none')
  };
  
  // Format filesize to human readable format
  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown size';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };
  
  // Check if audio formats are available
  const hasAudioFormats = groupedFormats.audioOnly.length > 0 || groupedFormats.combined.length > 0;
  
  return (
    <div className="quality-selector-container">
      <h3>Select Quality</h3>
      
      {groupedFormats.combined.length > 0 && (
        <div className="format-group">
          <h4>Video with Audio</h4>
          <div className="quality-options">
            {groupedFormats.combined.map((format) => (
              <div 
                key={format.format_id}
                className={`quality-option ${selectedFormat === format.format_id ? 'selected' : ''}`}
                onClick={() => onChange(format.format_id)}
              >
                <div className="quality-info">
                  <span className="quality-resolution">{format.resolution || 'Unknown'}</span>
                  <span className="quality-format">{format.ext?.toUpperCase() || 'Unknown'}</span>
                </div>
                <div className="quality-size">{formatFileSize(format.filesize || format.filesize_approx)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {groupedFormats.videoOnly.length > 0 && (
        <div className="format-group">
          <h4>Video Only</h4>
          <div className="quality-options">
            {groupedFormats.videoOnly.map((format) => (
              <div 
                key={format.format_id}
                className={`quality-option ${selectedFormat === format.format_id ? 'selected' : ''}`}
                onClick={() => onChange(format.format_id)}
              >
                <div className="quality-info">
                  <span className="quality-resolution">{format.resolution || 'Unknown'}</span>
                  <span className="quality-format">{format.ext?.toUpperCase() || 'Unknown'} (No Audio)</span>
                </div>
                <div className="quality-size">{formatFileSize(format.filesize || format.filesize_approx)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {groupedFormats.audioOnly.length > 0 && (
        <div className="format-group">
          <h4>Audio Only</h4>
          <div className="quality-options">
            {groupedFormats.audioOnly.map((format) => (
              <div 
                key={format.format_id}
                className={`quality-option ${selectedFormat === format.format_id ? 'selected' : ''}`}
                onClick={() => onChange(format.format_id)}
              >
                <div className="quality-info">
                  <span className="quality-resolution">{format.format_note || format.acodec || 'Audio'}</span>
                  <span className="quality-format">{format.ext?.toUpperCase() || 'Unknown'}</span>
                </div>
                <div className="quality-size">{formatFileSize(format.filesize || format.filesize_approx)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* MP3 Conversion Option */}
      {hasAudioFormats && (
        <div className="mp3-conversion-option">
          <label className="mp3-checkbox-container">
            <input 
              type="checkbox" 
              checked={convertToMp3} 
              onChange={() => setConvertToMp3(!convertToMp3)}
            />
            <span className="mp3-checkbox-label">Convert to MP3 Audio</span>
            <span className="mp3-checkbox-description">Extract audio and save as MP3 format</span>
          </label>
        </div>
      )}
    </div>
  );
}

// LoadingSpinner Component
function LoadingSpinner({ message }) {
  return (
    <div className="spinner-container">
      <div className="spinner"></div>
      <p>{message || 'Loading...'}</p>
    </div>
  );
}

// SupportedPlatforms Component
function SupportedPlatforms() {
  const platforms = [
    'YouTube', 'Instagram', 'Facebook', 'TikTok', 'Twitter', 'Vimeo',
    'Dailymotion', 'Twitch', 'Reddit', 'SoundCloud'
  ];
  
  return (
    <div className="supported-platforms">
      <h3>Supported Platforms</h3>
      <div className="platform-list">
        {platforms.map(platform => (
          <span key={platform} className="platform-badge-small">{platform}</span>
        ))}
        <span className="platform-badge-small">and more!</span>
      </div>
      <div className="feature-highlights">
        <div className="feature-item">
          <span className="feature-icon">🎬</span>
          <span className="feature-text">Download videos in HD quality</span>
        </div>
        <div className="feature-item">
          <span className="feature-icon">🎵</span>
          <span className="feature-text">Convert videos to MP3 audio</span>
        </div>
        <div className="feature-item">
          <span className="feature-icon">⚡</span>
          <span className="feature-text">Fast downloads with no limits</span>
        </div>
      </div>
    </div>
  );
}

// Enhanced Download Progress Component with status indicators
function DownloadProgress({ progress, status, convertToMp3 }) {
  // Create messages based on status and progress
  const getStatusMessage = () => {
    if (status === 'initializing') return 'Initializing download...';
    if (status === 'downloading') {
      if (progress < 5) return 'Starting download...';
      if (progress < 25) return 'Downloading video...';
      if (progress < 50) return 'Download in progress...';
      if (progress < 75) return 'Almost there...';
      if (progress < 95) return 'Finalizing download...';
      return 'Preparing file...';
    }
    if (status === 'converting' && convertToMp3) return 'Converting to MP3...';
    if (status === 'completed') return convertToMp3 ? 'MP3 conversion complete!' : 'Download complete!';
    return `${progress}% Complete`;
  };

  return (
    <div className="download-progress">
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${Math.min(progress, 100)}%` }}
        ></div>
      </div>
      <div className="progress-text">
        <span className="progress-percentage">{progress}%</span> 
        <span className="progress-status">{getStatusMessage()}</span>
      </div>
    </div>
  );
}

// Download Status Badge Component
function DownloadStatusBadge({ status, convertToMp3 }) {
  if (status === 'initializing') {
    return <div className="status-badge initializing">Preparing Download</div>;
  } else if (status === 'downloading') {
    return <div className="status-badge downloading">
      <div className="download-icon"></div>
      {convertToMp3 ? 'Downloading Video' : 'Video Downloading'}
    </div>;
  } else if (status === 'converting') {
    return <div className="status-badge converting">Converting to MP3</div>;
  } else if (status === 'completed') {
    return <div className="status-badge completed">
      <span className="check-icon">✓</span>
      {convertToMp3 ? 'MP3 Ready' : 'Download Complete'}
    </div>;
  }
  return null;
}

// Main App Component
function App() {
  const [url, setUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadStatus, setDownloadStatus] = useState(''); // New state for tracking download status
  const [downloadComplete, setDownloadComplete] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState(null);
  const [convertToMp3, setConvertToMp3] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const API_BASE_URL = 'https://provideodownloader-2.onrender.com';

  const fetchVideoInfo = async () => {
    if (!url) return;
    
    setLoading(true);
    setError('');
    setVideoInfo(null);
    setDownloadComplete(false);
    setDownloadStatus('');
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/info`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }
      
      const data = await response.json();
      
      setVideoInfo(data);
      if (data.formats && data.formats.length > 0) {
        // Select the best quality format by default
        const bestFormat = data.formats.find(f => 
          f.vcodec !== 'none' && f.acodec !== 'none'
        ) || data.formats[0];
        setSelectedFormat(bestFormat.format_id);
      }
    } catch (err) {
      setError(`Error: ${err.message || 'Failed to fetch video information'}`);
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const downloadVideo = async () => {
    if (!url || !selectedFormat) return;
    
    setDownloading(true);
    setDownloadProgress(0);
    setError('');
    setDownloadComplete(false);
    setDownloadStatus('initializing');
    
    try {
      // Start the download
      const response = await fetch(`${API_BASE_URL}/api/download`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          url,
          format_id: selectedFormat,
          convert_to_mp3: convertToMp3
        }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }
      
      const data = await response.json();
      
      // Set up download progress polling
      const progressInterval = setInterval(async () => {
        try {
          const progressResponse = await fetch(`${API_BASE_URL}/api/progress/${data.task_id}`);
          const progressData = await progressResponse.json();
          
          setDownloadProgress(progressData.progress);
          
          // Update status based on the progress data
          if (progressData.status === 'downloading') {
            setDownloadStatus('downloading');
          } else if (progressData.status === 'converting' && convertToMp3) {
            setDownloadStatus('converting');
          } else if (progressData.status === 'completed') {
            setDownloadStatus('completed');
            clearInterval(progressInterval);
            setDownloadComplete(true);
            
            // Trigger file download
            const downloadLink = document.createElement('a');
            downloadLink.href = `${API_BASE_URL}${progressData.file_url}`;
            downloadLink.download = progressData.filename || (convertToMp3 ? 'audio.mp3' : 'download');
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
          } else if (progressData.status === 'failed') {
            clearInterval(progressInterval);
            throw new Error(progressData.error || 'Download failed');
          }
        } catch (err) {
          console.error('Progress check error:', err);
        }
      }, 1000);
      
      // Clear interval if component unmounts
      return () => clearInterval(progressInterval);
      
    } catch (err) {
      setError(`Download error: ${err.message || 'Failed to download video'}`);
      console.error('Download error:', err);
      
      // If we haven't retried too many times, try again with a different format
      if (retryCount < 3 && videoInfo?.formats?.length > 1) {
        setRetryCount(prev => prev + 1);
        const alternateFormat = videoInfo.formats.find(f => f.format_id !== selectedFormat);
        if (alternateFormat) {
          setSelectedFormat(alternateFormat.format_id);
          setError(`Retrying with different format...`);
          setTimeout(() => downloadVideo(), 1500);
          return;
        }
      }
    } finally {
      if (!downloadComplete) {
        setDownloading(false);
      }
    }
  };

  const handleFormatChange = (formatId) => {
    setSelectedFormat(formatId);
    setDownloadComplete(false);
    setDownloadStatus('');
  };

  // Debounced URL fetch
  useEffect(() => {
    if (url) {
      const timer = setTimeout(() => {
        fetchVideoInfo();
      }, 800);
      
      return () => clearTimeout(timer);
    }
  }, [url]);

  // Reset retry count when URL changes
  useEffect(() => {
    setRetryCount(0);
  }, [url]);

  return (
    <div className="app-container">
      <div className="content-wrapper">
        <h1 className="downloadertitle">VIDEO DOWNLOADER <span>PRO</span></h1>
        <p className="subtitle">Download videos from YouTube, Instagram, Facebook, TikTok and more</p>
        
        <UrlInput 
          url={url} 
          setUrl={setUrl} 
          onSubmit={fetchVideoInfo}
          isLoading={loading}
        />
        
        {error && <div className="error-message">{error}</div>}
        
        {loading && <LoadingSpinner message="Analyzing video..." />}
        
        {!loading && !videoInfo && !error && <SupportedPlatforms />}
        
        {videoInfo && (
          <div className="results-container">
            <VideoPreview 
              title={videoInfo.title}
              thumbnail={videoInfo.thumbnail}
              duration={videoInfo.duration}
              platform={videoInfo.platform}
              views={videoInfo.view_count}
              uploadDate={videoInfo.upload_date}
            />
            
            {/* Download Status Badge Display */}
            {downloadStatus && (
              <DownloadStatusBadge 
                status={downloadStatus} 
                convertToMp3={convertToMp3} 
              />
            )}
            
            <QualitySelector 
              formats={videoInfo.formats}
              selectedFormat={selectedFormat}
              onChange={handleFormatChange}
              convertToMp3={convertToMp3}
              setConvertToMp3={setConvertToMp3}
            />
            
            {downloading && (
              <DownloadProgress 
                progress={downloadProgress} 
                status={downloadStatus}
                convertToMp3={convertToMp3}
              />
            )}
            
            <button 
              className={`download-button ${downloadComplete ? 'success' : ''}`}
              onClick={downloadVideo}
              disabled={downloading || !selectedFormat}
            >
              {downloadComplete ? 
                (convertToMp3 ? '✓ MP3 Download Complete' : '✓ Download Complete') : 
                downloading ? 
                  (convertToMp3 ? 
                    (downloadStatus === 'converting' ? 'Converting to MP3...' : 'Downloading...') : 
                    'Downloading...') : 
                  (convertToMp3 ? 'Download as MP3' : 'Download Now')}
            </button>
          </div>
        )}
      </div>
      
      <footer className="footer">
        <p>Made with yt-dlp, React and Python. For educational purposes only.</p>
        <p className="legal-disclaimer">Please respect copyright laws and content creators' rights.</p>
      </footer>
    </div>
  );
}

export default App;