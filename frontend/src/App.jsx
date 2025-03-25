import React, { useState, useCallback } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [videoUrl, setVideoUrl] = useState('');
  const [downloadOptions, setDownloadOptions] = useState([]);
  const [audioOptions, setAudioOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [activeTab, setActiveTab] = useState('video');

  const handleUrlSubmit = useCallback(async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setDownloadOptions([]);
    setAudioOptions([]);
    setDownloadProgress(0);

    try {
      const response = await axios.post('https://provideodownloader-2-8bp1.onrender.com/analyze-video', { url: videoUrl }, {
        timeout: 15000
      });
      
      const sortedOptions = response.data.options.sort((a, b) => {
        const resA = parseInt(a.resolution);
        const resB = parseInt(b.resolution);
        return resB - resA;
      });

      // Separate video and audio options
      const videoOptions = sortedOptions;
      const audioOptions = [{ resolution: 'MP3', format: 'mp3', filesize: 'Varies' }];

      setDownloadOptions(videoOptions);
      setAudioOptions(audioOptions);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to analyze video');
    } finally {
      setLoading(false);
    }
  }, [videoUrl]);

  const handleDownload = useCallback(async (format, type, formatId) => {
    setDownloadProgress(0);
    setError(null);

    try {
      const response = await axios.post(
        'https://provideodownloader-2-8bp1.onrender.com/download', 
        { url: videoUrl, format: formatId, type: type },
        { 
          responseType: 'blob',
          timeout: 180000,
          onDownloadProgress: (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setDownloadProgress(percentCompleted);
          }
        }
      );

      const blob = new Blob([response.data]);
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(blob);
      link.download = `downloaded_${type}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setDownloadProgress(100);
    } catch (err) {
      setError('Download failed: ' + (err.response?.data?.error || 'Unknown error'));
      setDownloadProgress(0);
    }
  }, [videoUrl]);

  return (
    <div className="video-downloader-container">
      <div className="video-downloader-card">
        <div className="video-downloader-header">
          <h1>🚀 Video Downloader</h1>
          <p>Paste any video URL to download</p>
        </div>

        <form onSubmit={handleUrlSubmit} className="url-input-form">
          <input 
            type="text" 
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="Paste video URL here"
            required
          />
          <button type="submit" disabled={loading}>
            {loading ? 'Analyzing...' : 'Analyze Video'}
          </button>
        </form>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        {downloadProgress > 0 && (
          <div className="progress-container">
            <div 
              className="progress-bar" 
              style={{width: `${downloadProgress}%`}}
            >
              {downloadProgress}%
            </div>
          </div>
        )}

        {(downloadOptions.length > 0 || audioOptions.length > 0) && (
          <div className="download-section">
            <div className="tab-selector">
              <button 
                className={activeTab === 'video' ? 'active' : ''}
                onClick={() => setActiveTab('video')}
              >
                Video Downloads
              </button>
              <button 
                className={activeTab === 'audio' ? 'active' : ''}
                onClick={() => setActiveTab('audio')}
              >
                Audio Downloads
              </button>
            </div>

            <div className="download-options">
              {activeTab === 'video' && downloadOptions.map((option, index) => (
                <div key={index} className="download-option">
                  <div className="option-details">
                    <span className="resolution">{option.resolution}</span>
                    <span className="filesize">{option.filesize}</span>
                  </div>
                  <button 
                    onClick={() => handleDownload(option.format, 'video', option.format_id)}
                  >
                    Download
                  </button>
                </div>
              ))}

              {activeTab === 'audio' && audioOptions.map((option, index) => (
                <div key={index} className="download-option">
                  <div className="option-details">
                    <span className="resolution">{option.resolution}</span>
                    <span className="filesize">{option.filesize}</span>
                  </div>
                  <button 
                    onClick={() => handleDownload('mp3', 'audio')}
                  >
                    Extract Audio
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;