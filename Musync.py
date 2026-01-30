import asyncio
import json
import time
import uuid
from aiohttp import web
import aiohttp_cors

# Global state
class MusicState:
    def __init__(self):
        self.playlist = []  # List of {id, name, data}
        self.current_song_index = -1
        self.is_playing = False
        self.start_time = None
        self.current_position = 0
        self.clients = {}  # ws: {id, username, is_admin, can_upload}
        self.admin_id = None
        self.chat_messages = []
        self.song_requests = []  # List of {id, song_name, requested_by, user_id, status}
        self.upload_chunks = {}  # Temporary storage for chunked uploads
        
    def get_current_position(self):
        if self.is_playing and self.start_time:
            elapsed = (time.time() * 1000 - self.start_time) / 1000
            return self.current_position + elapsed
        return self.current_position
    
    def get_current_song(self):
        if 0 <= self.current_song_index < len(self.playlist):
            return self.playlist[self.current_song_index]
        return None
        
state = MusicState()

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sync | Sonic Experience</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #050505;
            --glass-surface: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-highlight: rgba(255, 255, 255, 0.15);
            --accent-primary: #8b5cf6;
            --accent-secondary: #3b82f6;
            --accent-glow: rgba(139, 92, 246, 0.4);
            --text-main: #ffffff;
            --text-muted: #a1a1aa;
            --danger: #ef4444;
            --success: #10b981;
            --radius-lg: 24px;
            --radius-md: 16px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-font-smoothing: antialiased;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        body::before {
            content: '';
            position: absolute;
            top: -50%; left: -50%; width: 200%; height: 200%;
            background: radial-gradient(circle at center, #1e1b4b 0%, #000000 50%);
            z-index: -2;
            pointer-events: none;
        }

        .ambient-orb {
            position: absolute;
            width: 600px; height: 600px;
            background: radial-gradient(circle, var(--accent-primary) 0%, transparent 70%);
            filter: blur(80px); opacity: 0.15; border-radius: 50%;
            z-index: -1;
            animation: floatOrb 20s infinite alternate ease-in-out;
            pointer-events: none;
        }
        .ambient-orb:nth-child(2) {
            top: 10%; right: 10%;
            background: radial-gradient(circle, var(--accent-secondary) 0%, transparent 70%);
            animation-delay: -5s;
        }
        @keyframes floatOrb {
            0% { transform: translate(0, 0) scale(1); }
            100% { transform: translate(50px, 50px) scale(1.1); }
        }

        .app-header {
            height: 70px;
            flex-shrink: 0;
            padding: 0 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--glass-border);
            background: rgba(5, 5, 5, 0.6);
            backdrop-filter: blur(10px);
            z-index: 10;
        }

        .logo {
            font-weight: 700; font-size: 20px; letter-spacing: -0.5px;
            display: flex; align-items: center; gap: 10px;
            background: linear-gradient(135deg, #fff 0%, #a1a1aa 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }

        .container {
            flex: 1;
            display: grid;
            grid-template-columns: 320px 1fr 320px;
            gap: 24px;
            padding: 24px;
            max-width: 1920px;
            margin: 0 auto;
            width: 100%;
            overflow: hidden;
            min-height: 0;
        }

        .panel {
            background: var(--glass-surface);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-lg);
            backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
            min-height: 0;
        }

        .panel-header {
            padding: 20px;
            border-bottom: 1px solid var(--glass-border);
            font-weight: 600; font-size: 14px; text-transform: uppercase;
            letter-spacing: 1px; color: var(--text-muted);
            flex-shrink: 0;
            display: flex; justify-content: space-between; align-items: center;
        }

        .scrollable-content::-webkit-scrollbar { width: 6px; }
        .scrollable-content::-webkit-scrollbar-track { background: transparent; }
        .scrollable-content::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1); border-radius: 10px;
        }
        .scrollable-content::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }

        .playlist-panel { grid-column: 1; }
        
        .upload-section {
            padding: 20px;
            border-bottom: 1px solid var(--glass-border);
            flex-shrink: 0;
        }

        .playlist {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            min-height: 0;
        }

        .playlist-item {
            padding: 14px 16px; margin-bottom: 8px;
            border-radius: var(--radius-md); cursor: pointer;
            transition: all 0.2s ease; display: flex; justify-content: space-between;
            align-items: center; font-size: 14px; color: var(--text-muted);
            border: 1px solid transparent;
        }
        .playlist-item:hover { background: rgba(255, 255, 255, 0.05); color: var(--text-main); }
        .playlist-item.active {
            background: linear-gradient(90deg, rgba(139, 92, 246, 0.1) 0%, transparent 100%);
            border-left: 3px solid var(--accent-primary); color: var(--text-main); font-weight: 600;
        }

        .song-requests {
            margin-top: auto;
            padding: 20px;
            border-top: 1px solid var(--glass-border);
            background: rgba(0,0,0,0.2);
            flex-shrink: 0;
            max-height: 200px;
            display: flex; 
            flex-direction: column;
            overflow: hidden;
        }
        
        #requestsList { 
            overflow-y: auto; 
            flex: 1; 
            min-height: 0;
        }

        .player-panel {
            grid-column: 2;
            position: relative;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 24px;
        }

        .vinyl-container {
            width: min(180px, 25vh); 
            height: min(180px, 25vh); 
            border-radius: 50%;
            background: conic-gradient(from 0deg, #111, #222, #111);
            box-shadow: 0 10px 60px rgba(0,0,0,0.5);
            position: relative;
            display: flex; align-items: center; justify-content: center;
            border: 4px solid rgba(255,255,255,0.05);
            animation: spin 10s linear infinite; animation-play-state: paused;
            flex-shrink: 0;
        }
        .vinyl-container.playing { animation-play-state: running; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        
        .vinyl-inner {
            width: 33%; 
            height: 33%; 
            border-radius: 50%;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            box-shadow: inset 0 0 20px rgba(0,0,0,0.5);
        }

        .song-info { 
            text-align: center; 
            width: 100%; 
            flex-shrink: 0;
            max-width: 600px;
        }
        .song-name {
            font-size: clamp(20px, 4vw, 32px); 
            font-weight: 700; 
            margin-bottom: 6px;
            background: linear-gradient(to right, #fff, #ccc);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .time-display { 
            font-family: 'Inter', monospace; 
            color: var(--text-muted); 
            font-size: 13px; 
            letter-spacing: 1px; 
        }

        .progress-container { 
            width: 80%; 
            flex-shrink: 0;
            max-width: 600px;
        }
        .progress-bar {
            width: 100%; height: 6px; background: rgba(255, 255, 255, 0.1);
            border-radius: 10px; cursor: pointer; position: relative; overflow: hidden;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
            width: 0%; border-radius: 10px; box-shadow: 0 0 20px var(--accent-glow); transition: width 0.1s linear;
        }

        .controls-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
            width: 100%;
            flex-shrink: 0;
        }

        .controls {
            display: flex; gap: 20px; align-items: center;
            background: rgba(255, 255, 255, 0.05); padding: 12px 28px;
            border-radius: 100px; border: 1px solid var(--glass-border);
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            flex-shrink: 0;
        }

        .volume-control {
            display: flex; align-items: center; gap: 10px;
            width: 200px;
            flex-shrink: 0;
        }
        
        .volume-slider {
            -webkit-appearance: none; width: 100%; height: 4px;
            background: rgba(255,255,255,0.1); border-radius: 2px;
            outline: none;
        }
        .volume-slider::-webkit-slider-thumb {
            -webkit-appearance: none; width: 12px; height: 12px;
            background: #fff; border-radius: 50%; cursor: pointer;
            box-shadow: 0 0 10px rgba(0,0,0,0.5);
        }

        .user-meta-wrapper {
            margin-top: auto;
            padding: 16px 20px;
            border-top: 1px solid var(--glass-border);
            display: flex;
            justify-content: center;
            align-items: center;
            flex-shrink: 0;
            min-height: 48px;
        }

        .user-meta {
            font-size: 11px;
            padding: 6px 14px;
            border-radius: 999px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
        }

        .chat-panel { grid-column: 3; }

        .alias-input-group {
            display: flex; gap: 8px; width: 100%;
        }
        .alias-input {
            background: rgba(0,0,0,0.3); border: 1px solid var(--glass-border);
            color: var(--text-main); font-size: 12px; padding: 6px 10px;
            border-radius: 6px; outline: none; flex: 1;
        }
        .alias-save-btn {
            background: var(--accent-primary); color: white; border: none;
            padding: 6px 12px; border-radius: 6px; font-size: 11px;
            cursor: pointer; font-weight: 600;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex; flex-direction: column; gap: 12px;
            min-height: 0;
        }

        .chat-input-area {
            padding: 20px;
            border-top: 1px solid var(--glass-border);
            display: flex; gap: 10px;
            flex-shrink: 0;
        }

        button {
            background: transparent; color: var(--text-main); border: none;
            padding: 12px; border-radius: 50%; cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex; align-items: center; justify-content: center;
        }
        button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.1); transform: scale(1.1); color: #fff; }
        button:disabled { opacity: 0.3; cursor: not-allowed; transform: none; }
        
        #playBtn, #pauseBtn { background: var(--text-main); color: var(--bg-dark); width: 52px; height: 52px; }
        #playBtn:hover:not(:disabled), #pauseBtn:hover:not(:disabled) {
            background: #fff; box-shadow: 0 0 20px rgba(255, 255, 255, 0.4); transform: scale(1.1);
        }

        .chat-input {
            flex: 1; background: rgba(0, 0, 0, 0.3); border: 1px solid var(--glass-border);
            color: white; padding: 12px 16px; border-radius: var(--radius-md);
            outline: none; font-family: inherit; transition: all 0.3s;
        }
        .chat-input:focus { border-color: var(--accent-primary); box-shadow: 0 0 0 2px var(--accent-glow); }

        .send-btn {
            background: var(--accent-primary); color: white; padding: 0 20px;
            border-radius: var(--radius-md); font-weight: 600; font-size: 13px;
        }

        .status-pill {
            padding: 8px 16px; background: rgba(16, 185, 129, 0.1);
            color: var(--success); border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 20px; font-size: 12px; font-weight: 600;
            display: flex; align-items: center; gap: 8px;
        }
        .status-pill.disconnected { background: rgba(239, 68, 68, 0.1); color: var(--danger); border-color: rgba(239, 68, 68, 0.2); }
        
        .file-label {
            display: block; background: rgba(255, 255, 255, 0.05); color: var(--text-main);
            padding: 14px; border-radius: var(--radius-md); cursor: pointer; text-align: center;
            font-size: 13px; font-weight: 500; transition: all 0.3s ease;
            border: 1px dashed var(--glass-border);
        }
        .file-label:hover { background: rgba(255, 255, 255, 0.1); border-color: var(--accent-primary); }
        .file-label.disabled { opacity: 0.5; cursor: not-allowed; border-style: solid; }

        .message {
            background: rgba(255, 255, 255, 0.03); padding: 12px;
            border-radius: var(--radius-md); border-bottom-left-radius: 4px;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        .remove-btn { 
            opacity: 0; 
            transition: all 0.2s; 
            padding: 4px 8px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 4px;
            color: var(--danger);
            font-size: 11px;
        }
        .playlist-item:hover .remove-btn { opacity: 1; }
        .remove-btn:hover { 
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger); 
        }
        input[type="file"] { display: none; }
        
        .request-item {
            background: rgba(255,255,255,0.05); padding: 8px; border-radius: 8px;
            margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; font-size: 11px;
        }

        .request-actions {
            display: flex;
            gap: 4px;
        }

        .request-approve-btn,
        .request-reject-btn {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
        }

        .request-approve-btn {
            background: rgba(16, 185, 129, 0.2);
            color: var(--success);
        }

        .request-approve-btn:hover {
            background: rgba(16, 185, 129, 0.3);
        }

        .request-reject-btn {
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger);
        }

        .request-reject-btn:hover {
            background: rgba(239, 68, 68, 0.3);
        }

        .icon { width: 20px; height: 20px; fill: currentColor; }
        .icon-large { width: 24px; height: 24px; }

        @media (max-width: 1200px) {
            .container { grid-template-columns: 280px 1fr; }
            .chat-panel { grid-column: 1 / -1; height: 300px; }
            body { overflow-y: auto; height: auto; }
            .container { height: auto; display: flex; flex-direction: column; }
            .panel { height: 500px; }
        }
    </style>
</head>
<body>
    <div class="ambient-orb"></div>
    <div class="ambient-orb"></div>

    <header class="app-header">
        <div class="logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent-primary)"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
            SYNC<span style="font-weight: 300; opacity: 0.7">PLAYER</span>
        </div>
        <div id="status" class="status-pill">
            <span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%;"></span>
            Connecting...
        </div>
    </header>
    
    <div class="container">
        <div class="panel playlist-panel">
            <div class="panel-header">
                <span>Library</span>
            </div>
            
            <div class="upload-section" id="uploadSection">
                <label for="audioFiles" class="file-label" id="uploadLabel">
                    <div style="font-size: 24px; margin-bottom: 8px;">+</div>
                    Upload Tracks
                </label>
                <input type="file" id="audioFiles" accept="audio/*" multiple>
                
                <div id="uploadProgress" style="display:none; margin-top:10px;">
                    <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
                        <span id="progressText">Uploading...</span>
                        <span id="progressPercent">0%</span>
                    </div>
                    <div style="width:100%; height:4px; background:rgba(255,255,255,0.1); border-radius:2px; margin-top:6px; overflow:hidden;">
                        <div id="progressBarFill" style="height:100%; background:var(--success); width:0%; transition:width 0.3s;"></div>
                    </div>
                </div>
            </div>
            
            <div class="playlist scrollable-content" id="playlist"></div>
            
            <div class="song-requests" id="songRequestsSection">
                <h3 style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px; letter-spacing: 1px;" id="requestsHeader">Song Requests</h3>
                <div class="chat-input-area" id="requestInputArea" style="padding: 0; border: none; margin-bottom: 10px; display: none;">
                    <input type="text" class="chat-input" id="requestInput" placeholder="Song name..." style="padding: 8px 12px; font-size: 12px;">
                    <button class="send-btn" id="requestBtn" style="padding: 0 12px;">+</button>
                </div>
                <div id="requestsList" class="scrollable-content"></div>
            </div>
        </div>
        
        <div class="panel player-panel">
            <div class="vinyl-container" id="visualizerParams">
                <div class="vinyl-inner"></div>
            </div>
            
            <div class="song-info">
                <div class="song-name" id="songName">Select a track</div>
                <div class="time-display" id="timeDisplay">--:-- / --:--</div>
            </div>
            
            <div class="progress-container">
                <div class="progress-bar" id="progressBar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
            </div>
            
            <div class="controls-wrapper">
                <div class="controls">
                    <button id="seekBackBtn" disabled title="-10s">
                        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg>
                    </button>
                    <button id="prevBtn" disabled title="Previous">
                        <svg class="icon-large" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
                    </button>
                    <button id="playBtn" disabled title="Play">
                        <svg class="icon-large" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M8 5v14l11-7z"/></svg>
                    </button>
                    <button id="pauseBtn" disabled title="Pause" style="display: none;">
                        <svg class="icon-large" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                    </button>
                    <button id="nextBtn" disabled title="Next">
                        <svg class="icon-large" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                    </button>
                    <button id="seekForwardBtn" disabled title="+10s">
                        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
                    </button>
                </div>

                <div class="volume-control">
                    <svg class="icon" style="width: 16px; height: 16px; opacity: 0.7;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
                    <input type="range" class="volume-slider" id="volumeSlider" min="0" max="1" step="0.01" value="1">
                </div>
            </div>
            
            <div class="user-meta-wrapper">
                <div class="user-meta" id="userInfo">
                    <span id="userCount">0</span> listeners • <span id="userRole">Guest</span>
                </div>
            </div>
        </div>
        
        <div class="panel chat-panel">
            <div class="panel-header" style="justify-content: flex-start; gap: 15px;">
                <div class="alias-input-group">
                    <input type="text" id="aliasInput" class="alias-input" placeholder="Enter Alias">
                    <button id="saveAliasBtn" class="alias-save-btn">Save</button>
                </div>
            </div>
            
            <div class="chat-messages scrollable-content" id="chatMessages"></div>
            
            <div class="chat-input-area">
                <input type="text" class="chat-input" id="chatInput" placeholder="Say something...">
                <button class="send-btn" id="sendBtn">
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </button>
            </div>
        </div>
    </div>
    
    <audio id="audio" preload="auto"></audio>
    
    <script>
        const vinyl = document.getElementById('visualizerParams');
        const audio = document.getElementById('audio');
        const CHUNK_SIZE = 64 * 1024; 
        
        const elements = {
            playBtn: document.getElementById('playBtn'),
            pauseBtn: document.getElementById('pauseBtn'),
            prevBtn: document.getElementById('prevBtn'),
            nextBtn: document.getElementById('nextBtn'),
            seekBackBtn: document.getElementById('seekBackBtn'),
            seekForwardBtn: document.getElementById('seekForwardBtn'),
            fileInput: document.getElementById('audioFiles'),
            uploadLabel: document.getElementById('uploadLabel'),
            uploadProgress: document.getElementById('uploadProgress'),
            progressText: document.getElementById('progressText'),
            progressBarFill: document.getElementById('progressBarFill'),
            playlist: document.getElementById('playlist'),
            songName: document.getElementById('songName'),
            timeDisplay: document.getElementById('timeDisplay'),
            progressFill: document.getElementById('progressFill'),
            progressBar: document.getElementById('progressBar'),
            status: document.getElementById('status'),
            userInfo: document.getElementById('userInfo'),
            userCount: document.getElementById('userCount'),
            userRole: document.getElementById('userRole'),
            chatMessages: document.getElementById('chatMessages'),
            chatInput: document.getElementById('chatInput'),
            sendBtn: document.getElementById('sendBtn'),
            requestInput: document.getElementById('requestInput'),
            requestBtn: document.getElementById('requestBtn'),
            requestsList: document.getElementById('requestsList'),
            songRequestsSection: document.getElementById('songRequestsSection'),
            requestInputArea: document.getElementById('requestInputArea'),
            requestsHeader: document.getElementById('requestsHeader'),
            aliasInput: document.getElementById('aliasInput'),
            saveAliasBtn: document.getElementById('saveAliasBtn'),
            volumeSlider: document.getElementById('volumeSlider')
        };
        
        let ws;
        let serverTimeOffset = 0;
        let isAdmin = false;
        let canUpload = false;
        let userId = null;
        let username = localStorage.getItem('sync_username') || 'Guest-' + Math.floor(Math.random() * 1000);
        let isSeeking = false;
        
        // --- Helper: Generate consistent color from string ---
        function stringToColor(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            const h = Math.abs(hash) % 360;
            return `hsl(${h}, 70%, 60%)`;
        }

        // --- Init UI ---
        elements.aliasInput.value = username;
        const savedVolume = localStorage.getItem('sync_volume');
        if(savedVolume !== null) {
            audio.volume = parseFloat(savedVolume);
            elements.volumeSlider.value = savedVolume;
        }

        // --- Volume Logic ---
        elements.volumeSlider.addEventListener('input', (e) => {
            const vol = parseFloat(e.target.value);
            audio.volume = vol;
            localStorage.setItem('sync_volume', vol);
        });

        // --- Alias Logic ---
        elements.saveAliasBtn.addEventListener('click', () => {
            const newName = elements.aliasInput.value.trim();
            if(newName && newName !== username) {
                username = newName;
                localStorage.setItem('sync_username', username);
                ws.send(JSON.stringify({ type: 'set_username', username }));
                
                const originalText = elements.saveAliasBtn.textContent;
                elements.saveAliasBtn.textContent = "Saved!";
                elements.saveAliasBtn.style.background = "var(--success)";
                setTimeout(() => {
                    elements.saveAliasBtn.textContent = originalText;
                    elements.saveAliasBtn.style.background = "var(--accent-primary)";
                }, 1500);
            }
        });

        function updateUploadUI() {
            if (canUpload) {
                elements.uploadLabel.classList.remove('disabled');
                elements.fileInput.disabled = false;
            } else {
                elements.uploadLabel.classList.add('disabled');
                elements.fileInput.disabled = true;
            }
        }

        function togglePlayPause(isPlaying) {
            if (isPlaying) {
                elements.playBtn.style.display = 'none';
                elements.pauseBtn.style.display = 'flex';
                vinyl.classList.add('playing');
            } else {
                elements.playBtn.style.display = 'flex';
                elements.pauseBtn.style.display = 'none';
                vinyl.classList.remove('playing');
            }
        }

        function getServerTime() {
            return Date.now() + serverTimeOffset;
        }
        
        function formatTime(seconds) {
            if (!isFinite(seconds)) return '00:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        
        function updateProgress() {
            if (audio.duration && !isSeeking) {
                const progress = (audio.currentTime / audio.duration) * 100;
                elements.progressFill.style.width = progress + '%';
                elements.timeDisplay.textContent = formatTime(audio.currentTime) + ' / ' + formatTime(audio.duration);
            }
        }
        
        function base64ToBlob(base64) {
            const parts = base64.split(',');
            const mimeMatch = parts[0].match(/:(.*?);/);
            const mime = mimeMatch ? mimeMatch[1] : 'audio/mpeg';
            const bstr = atob(parts[1]);
            const n = bstr.length;
            const u8arr = new Uint8Array(n);
            for (let i = 0; i < n; i++) {
                u8arr[i] = bstr.charCodeAt(i);
            }
            return new Blob([u8arr], { type: mime });
        }
        
        async function uploadFileInChunks(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const base64 = e.target.result;
                    const uploadId = Date.now() + '_' + Math.random().toString(36);
                    const totalChunks = Math.ceil(base64.length / CHUNK_SIZE);
                    
                    elements.uploadProgress.style.display = 'block';
                    elements.progressText.textContent = `Uploading ${file.name}`;
                    
                    for (let i = 0; i < totalChunks; i++) {
                        const chunk = base64.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
                        ws.send(JSON.stringify({
                            type: 'upload_chunk',
                            upload_id: uploadId,
                            song_name: file.name,
                            chunk_index: i,
                            total_chunks: totalChunks,
                            chunk_data: chunk
                        }));
                        const progress = ((i + 1) / totalChunks * 100).toFixed(0);
                        document.getElementById('progressPercent').textContent = `${progress}%`;
                        elements.progressBarFill.style.width = progress + '%';
                        await new Promise(r => setTimeout(r, 10));
                    }
                    setTimeout(() => {
                         elements.uploadProgress.style.display = 'none';
                         elements.progressBarFill.style.width = '0%';
                    }, 1000);
                    resolve();
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        }
        
        function renderPlaylist(playlist, currentIndex) {
            if (playlist.length === 0) {
                elements.playlist.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 40px; font-size: 13px;">No tracks in library</div>';
                return;
            }
            elements.playlist.innerHTML = playlist.map((song, index) => `
                <div class="playlist-item ${index === currentIndex ? 'active' : ''}" data-index="${index}">
                    <div style="flex:1; overflow:hidden;">
                        <span class="song-title">${song.name}</span>
                    </div>
                    ${isAdmin ? `
                    <button class="remove-btn" data-id="${song.id}">Remove</button>` : ''}
                </div>
            `).join('');
            
            document.querySelectorAll('.playlist-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    if (!e.target.closest('.remove-btn')) {
                        const index = parseInt(item.dataset.index);
                        ws.send(JSON.stringify({ type: 'change_song', index }));
                    }
                });
            });
            
            document.querySelectorAll('.remove-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;
                    ws.send(JSON.stringify({ type: 'remove_song', id }));
                });
            });
        }
        
        function addChatMessage(msg) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${msg.isSystem ? 'system' : ''}`;
            const time = new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            const userColor = msg.username ? stringToColor(msg.username) : 'var(--accent-secondary)';
            
            messageDiv.innerHTML = `
                <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:11px;">
                    <span style="font-weight:600; color:${userColor};">${msg.username}${msg.isAdmin ? ' <span style="background:var(--accent-primary); color:white; padding:1px 4px; border-radius:3px; font-size:9px;">ADMIN</span>' : ''}</span>
                    <span style="color:var(--text-muted); opacity:0.5;">${time}</span>
                </div>
                <div style="color:#ddd; font-size:13px; line-height:1.4;">${msg.text}</div>
            `;
            elements.chatMessages.appendChild(messageDiv);
            elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
        }
        
        function renderRequests(requests) {
            const pending = requests.filter(r => r.status === 'pending');
            
            if (!isAdmin) {
                elements.requestsList.innerHTML = '';
                return;
            }
            
            // Show the requests section for admin if there are pending requests
            if (pending.length === 0) {
                elements.requestsList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 10px; font-size: 11px;">No pending requests</div>';
                return;
            }
            
            elements.requestsList.innerHTML = pending.map(req => `
                <div class="request-item">
                    <div style="flex:1;">
                        <div style="font-weight:600; color:white; margin-bottom:2px;">${req.song_name}</div>
                        <div style="color:var(--text-muted); font-size:10px;">by ${req.requested_by}</div>
                    </div>
                    <div class="request-actions">
                        <button class="request-approve-btn" data-id="${req.id}" data-user="${req.user_id}">✓</button>
                        <button class="request-reject-btn" data-id="${req.id}">✕</button>
                    </div>
                </div>
            `).join('');
            
            document.querySelectorAll('.request-approve-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    ws.send(JSON.stringify({ 
                        type: 'handle_request', 
                        request_id: btn.dataset.id, 
                        user_id: btn.dataset.user,
                        action: 'approve' 
                    }));
                });
            });
            document.querySelectorAll('.request-reject-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    ws.send(JSON.stringify({ 
                        type: 'handle_request', 
                        request_id: btn.dataset.id, 
                        action: 'reject' 
                    }));
                });
            });
        }
        
        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                ws.send(JSON.stringify({ type: 'set_username', username }));
                elements.status.innerHTML = '<span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%; box-shadow: 0 0 8px currentColor;"></span>Connected';
                elements.status.className = 'status-pill';
            };
            
            ws.onclose = () => {
                elements.status.innerHTML = '<span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%;"></span>Reconnecting...';
                elements.status.className = 'status-pill disconnected';
                setTimeout(connect, 1000);
            };
            
            ws.onmessage = async (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'init') {
                    isAdmin = data.is_admin;
                    canUpload = data.can_upload;
                    userId = data.user_id;
                    elements.userRole.innerHTML = isAdmin ? '<span style="background:var(--accent-primary); padding:2px 6px; border-radius:4px; font-size:10px;">ADMIN</span>' : 'Listener';
                    
                    if (isAdmin) {
                        // Admin sees "Pending Requests" header and no input
                        elements.requestsHeader.textContent = 'Pending Requests';
                        elements.requestInputArea.style.display = 'none';
                    } else {
                        // Non-admin sees "Request Queue" header with input
                        elements.requestsHeader.textContent = 'Request Queue';
                        elements.requestInputArea.style.display = 'flex';
                    }
                    
                    updateUploadUI();
                }
                else if (data.type === 'pong') {
                    const roundTrip = performance.now() - data.client_time;
                    serverTimeOffset = (data.server_time + (roundTrip / 2)) - Date.now();
                }
                else if (data.type === 'state') {
                    renderPlaylist(data.playlist, data.current_index);
                    renderRequests(data.song_requests);
                    elements.userCount.textContent = data.user_count;
                    if (data.current_song) {
                        const audioBlob = base64ToBlob(data.current_song.data);
                        if (audio.src !== URL.createObjectURL(audioBlob)) audio.src = URL.createObjectURL(audioBlob);
                        elements.songName.textContent = data.current_song.name;
                        audio.onloadedmetadata = () => {
                            elements.playBtn.disabled = false; elements.pauseBtn.disabled = false;
                            elements.prevBtn.disabled = false; elements.nextBtn.disabled = false;
                            elements.seekBackBtn.disabled = false; elements.seekForwardBtn.disabled = false;
                            
                            if (data.is_playing) {
                                togglePlayPause(true);
                                const targetTime = (getServerTime() - data.start_time) / 1000;
                                audio.currentTime = Math.max(0, targetTime);
                                audio.play().catch(console.error);
                            } else {
                                togglePlayPause(false);
                                audio.pause();
                                audio.currentTime = data.position;
                            }
                        };
                    }
                    if (data.chat_messages) {
                        elements.chatMessages.innerHTML = '';
                        data.chat_messages.forEach(addChatMessage);
                    }
                }
                else if (data.type === 'play') {
                    if (audio.src) {
                        isSeeking = true;
                        const targetTime = (getServerTime() - data.start_time) / 1000;
                        audio.currentTime = Math.max(0, targetTime);
                        setTimeout(async () => { await audio.play(); togglePlayPause(true); isSeeking = false; }, 10);
                    }
                }
                else if (data.type === 'pause') {
                    isSeeking = true; audio.pause(); togglePlayPause(false); audio.currentTime = data.position; setTimeout(() => isSeeking = false, 100);
                }
                else if (data.type === 'seek') {
                    isSeeking = true;
                    if (data.is_playing) {
                        const targetTime = (getServerTime() - data.start_time) / 1000;
                        audio.currentTime = Math.max(0, targetTime);
                        if (audio.paused) await audio.play();
                    } else {
                        audio.pause(); audio.currentTime = data.position;
                    }
                    setTimeout(() => isSeeking = false, 100);
                }
                else if (data.type === 'playlist_update') renderPlaylist(data.playlist, data.current_index);
                else if (data.type === 'chat_message') addChatMessage(data);
                else if (data.type === 'requests_update') renderRequests(data.requests);
                else if (data.type === 'upload_permission') {
                    canUpload = data.can_upload;
                    updateUploadUI();
                }
            };
        }
        
        elements.progressBar.addEventListener('click', (e) => {
            if (audio.duration && isAdmin) {
                const rect = elements.progressBar.getBoundingClientRect();
                const position = ((e.clientX - rect.left) / rect.width) * audio.duration;
                ws.send(JSON.stringify({ type: 'seek', position }));
            }
        });
        
        elements.fileInput.addEventListener('change', async (e) => {
            for (const file of Array.from(e.target.files)) {
                try { await uploadFileInChunks(file); } catch (error) { alert(`Failed to upload ${file.name}`); }
            }
            e.target.value = '';
        });
        
        elements.playBtn.onclick = () => ws.send(JSON.stringify({ type: 'play' }));
        elements.pauseBtn.onclick = () => ws.send(JSON.stringify({ type: 'pause', position: audio.currentTime }));
        elements.prevBtn.onclick = () => ws.send(JSON.stringify({ type: 'previous' }));
        elements.nextBtn.onclick = () => ws.send(JSON.stringify({ type: 'next' }));
        elements.seekBackBtn.onclick = () => ws.send(JSON.stringify({ type: 'seek', position: Math.max(0, audio.currentTime - 10) }));
        elements.seekForwardBtn.onclick = () => ws.send(JSON.stringify({ type: 'seek', position: Math.min(audio.duration, audio.currentTime + 10) }));
        
        function sendMessage() {
            const text = elements.chatInput.value.trim();
            if (text) { ws.send(JSON.stringify({ type: 'chat', text })); elements.chatInput.value = ''; }
        }
        elements.sendBtn.onclick = sendMessage;
        elements.chatInput.onkeypress = (e) => { if (e.key === 'Enter') sendMessage(); };
        
        elements.requestBtn.onclick = () => {
            const songName = elements.requestInput.value.trim();
            if (songName) { ws.send(JSON.stringify({ type: 'request_song', song_name: songName })); elements.requestInput.value = ''; }
        };
        elements.requestInput.onkeypress = (e) => { if (e.key === 'Enter') elements.requestBtn.click(); };
        
        audio.addEventListener('timeupdate', updateProgress);
        audio.addEventListener('ended', () => { togglePlayPause(false); ws.send(JSON.stringify({ type: 'next' })); });
        setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping', client_time: performance.now() })); }, 5000);
        
        // Fix layout breaking on window resize (F12, etc)
        window.addEventListener('resize', () => {
            // Force layout recalculation
            document.body.style.display = 'none';
            document.body.offsetHeight; // Trigger reflow
            document.body.style.display = 'flex';
        });
        
        connect();
    </script>
</body>
</html>
"""

async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=0)
    await ws.prepare(request)
    
    user_id = str(uuid.uuid4())
    is_admin = state.admin_id is None
    
    if is_admin:
        state.admin_id = user_id
    
    state.clients[ws] = {
        'id': user_id,
        'username': None,
        'is_admin': is_admin,
        'can_upload': is_admin  # Admins can always upload
    }
    
    await ws.send_json({
        'type': 'init',
        'user_id': user_id,
        'is_admin': is_admin,
        'can_upload': is_admin
    })
    
    await broadcast_state()
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                user_info = state.clients[ws]
                
                if data['type'] == 'set_username':
                    user_info['username'] = data['username']
                    await broadcast_chat({
                        'username': 'System',
                        'text': f"{data['username']} joined the room",
                        'timestamp': time.time() * 1000,
                        'isSystem': True,
                        'isAdmin': False
                    })
                    await broadcast_state()
                
                elif data['type'] == 'ping':
                    await ws.send_json({
                        'type': 'pong',
                        'client_time': data['client_time'],
                        'server_time': time.time() * 1000
                    })
                
                elif data['type'] == 'upload_chunk' and user_info['can_upload']:
                    upload_id = data['upload_id']
                    
                    if upload_id not in state.upload_chunks:
                        state.upload_chunks[upload_id] = {
                            'song_name': data['song_name'],
                            'total_chunks': data['total_chunks'],
                            'chunks': {}
                        }
                    
                    state.upload_chunks[upload_id]['chunks'][data['chunk_index']] = data['chunk_data']
                    
                    if len(state.upload_chunks[upload_id]['chunks']) == data['total_chunks']:
                        full_data = ''.join([
                            state.upload_chunks[upload_id]['chunks'][i] 
                            for i in range(data['total_chunks'])
                        ])
                        
                        song_id = str(uuid.uuid4())
                        state.playlist.append({
                            'id': song_id,
                            'name': data['song_name'],
                            'data': full_data
                        })
                        
                        del state.upload_chunks[upload_id]
                        
                        await broadcast_state()
                
                elif data['type'] == 'remove_song' and user_info['is_admin']:
                    state.playlist = [s for s in state.playlist if s['id'] != data['id']]
                    if state.current_song_index >= len(state.playlist):
                        state.current_song_index = len(state.playlist) - 1
                    await broadcast_state()
                
                elif data['type'] == 'change_song':
                    index = data['index']
                    if 0 <= index < len(state.playlist):
                        state.current_song_index = index
                        state.current_position = 0
                        state.is_playing = False
                        state.start_time = None
                        await broadcast_state()
                
                elif data['type'] == 'play':
                    state.is_playing = True
                    state.current_position = state.get_current_position()
                    state.start_time = int(time.time() * 1000) + 50
                    await broadcast({
                        'type': 'play',
                        'start_time': state.start_time
                    })
                
                elif data['type'] == 'pause':
                    state.is_playing = False
                    state.current_position = data.get('position', state.get_current_position())
                    state.start_time = None
                    await broadcast({
                        'type': 'pause',
                        'position': state.current_position
                    })
                
                elif data['type'] == 'seek' and user_info['is_admin']:
                    state.current_position = data['position']
                    if state.is_playing:
                        state.start_time = int(time.time() * 1000) + 50
                    await broadcast({
                        'type': 'seek',
                        'position': state.current_position,
                        'is_playing': state.is_playing,
                        'start_time': state.start_time
                    })
                
                elif data['type'] == 'next':
                    if state.current_song_index < len(state.playlist) - 1:
                        state.current_song_index += 1
                        state.current_position = 0
                        state.start_time = int(time.time() * 1000) + 50 if state.is_playing else None
                        await broadcast_state()
                
                elif data['type'] == 'previous':
                    if state.current_song_index > 0:
                        state.current_song_index -= 1
                        state.current_position = 0
                        state.start_time = int(time.time() * 1000) + 50 if state.is_playing else None
                        await broadcast_state()
                
                elif data['type'] == 'chat':
                    chat_msg = {
                        'username': user_info['username'],
                        'text': data['text'],
                        'timestamp': time.time() * 1000,
                        'isSystem': False,
                        'isAdmin': user_info['is_admin']
                    }
                    state.chat_messages.append(chat_msg)
                    await broadcast_chat(chat_msg)
                
                elif data['type'] == 'request_song' and not user_info['is_admin']:
                    request = {
                        'id': str(uuid.uuid4()),
                        'song_name': data['song_name'],
                        'requested_by': user_info['username'],
                        'user_id': user_info['id'],
                        'status': 'pending'
                    }
                    state.song_requests.append(request)
                    
                    # Broadcast to all clients immediately
                    await broadcast({
                        'type': 'requests_update',
                        'requests': state.song_requests
                    })
                    
                    # Also send chat notification
                    await broadcast_chat({
                        'username': 'System',
                        'text': f"🎵 {user_info['username']} requested: {data['song_name']}",
                        'timestamp': time.time() * 1000,
                        'isSystem': True,
                        'isAdmin': False
                    })
                
                elif data['type'] == 'handle_request' and user_info['is_admin']:
                    request_id = data['request_id']
                    action = data['action']
                    
                    for req in state.song_requests:
                        if req['id'] == request_id:
                            req['status'] = action
                            
                            if action == 'approve':
                                # Grant upload permission to the requesting user
                                requester_user_id = data.get('user_id')
                                if requester_user_id:
                                    for client_ws, client_info in state.clients.items():
                                        if client_info['id'] == requester_user_id:
                                            client_info['can_upload'] = True
                                            await client_ws.send_json({
                                                'type': 'upload_permission',
                                                'can_upload': True
                                            })
                                            break
                                
                                await broadcast_chat({
                                    'username': 'System',
                                    'text': f"✅ Song request '{req['song_name']}' by {req['requested_by']} was approved! {req['requested_by']} can now upload the song.",
                                    'timestamp': time.time() * 1000,
                                    'isSystem': True,
                                    'isAdmin': False
                                })
                            else:
                                await broadcast_chat({
                                    'username': 'System',
                                    'text': f"❌ Song request '{req['song_name']}' by {req['requested_by']} was rejected.",
                                    'timestamp': time.time() * 1000,
                                    'isSystem': True,
                                    'isAdmin': False
                                })
                            break
                    
                    await broadcast_requests()
    
    finally:
        user_info = state.clients.pop(ws, None)
        if user_info and user_info['username']:
            await broadcast_chat({
                'username': 'System',
                'text': f"{user_info['username']} left the room",
                'timestamp': time.time() * 1000,
                'isSystem': True,
                'isAdmin': False
            })
        
        if user_info and user_info['id'] == state.admin_id:
            state.admin_id = None
            if state.clients:
                next_admin_ws = list(state.clients.keys())[0]
                state.clients[next_admin_ws]['is_admin'] = True
                state.clients[next_admin_ws]['can_upload'] = True
                state.admin_id = state.clients[next_admin_ws]['id']
                await next_admin_ws.send_json({
                    'type': 'init',
                    'user_id': state.admin_id,
                    'is_admin': True,
                    'can_upload': True
                })
        
        await broadcast_state()
    
    return ws

async def broadcast(message):
    if state.clients:
        await asyncio.gather(
            *[client.send_json(message) for client in state.clients.keys()],
            return_exceptions=True
        )

async def broadcast_state():
    current_song = state.get_current_song()
    await broadcast({
        'type': 'state',
        'playlist': [{'id': s['id'], 'name': s['name']} for s in state.playlist],
        'current_index': state.current_song_index,
        'current_song': current_song,
        'is_playing': state.is_playing,
        'start_time': state.start_time,
        'position': state.get_current_position(),
        'user_count': len(state.clients),
        'chat_messages': state.chat_messages[-50:],
        'song_requests': state.song_requests
    })

async def broadcast_chat(message):
    await broadcast({
        'type': 'chat_message',
        **message
    })

async def broadcast_requests():
    await broadcast({
        'type': 'requests_update',
        'requests': state.song_requests
    })

async def index_handler(request):
    return web.Response(text=HTML_CONTENT, content_type='text/html')

def create_app():
    app = web.Application(client_max_size=0)
    
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    
    for route in list(app.router.routes()):
        cors.add(route)
    
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080)
