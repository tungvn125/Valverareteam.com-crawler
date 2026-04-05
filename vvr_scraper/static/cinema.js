/**
 * VVR-Cinema Player Engine
 * Handles playback, synchronization, and visual effects for cinematic novels.
 */

class CinemaPlayer {
    constructor() {
        // DOM Elements
        this.audio = document.getElementById('audio-player');
        this.bgCurrent = document.getElementById('bg-image-current');
        this.bgNext = document.getElementById('bg-image-next');
        this.vfxOverlay = document.getElementById('vfx-overlay');
        this.charName = document.getElementById('character-name');
        this.textDisplay = document.getElementById('text-display');
        
        this.playPauseBtn = document.getElementById('play-pause-btn');
        this.playIcon = document.getElementById('play-icon');
        this.pauseIcon = document.getElementById('pause-icon');
        this.progressBar = document.getElementById('progress-bar');
        this.progressContainer = document.getElementById('progress-container');
        this.timeDisplay = document.getElementById('time-display');
        this.volumeSlider = document.getElementById('volume-slider');
        this.speedSelector = document.getElementById('speed-selector');
        this.closeBtn = document.getElementById('close-btn');

        // State
        this.manifest = null;
        this.events = [];
        this.nextEventIndex = 0;
        this.currentWordSpans = [];
        this.currentDialogue = null;
        this.activeVFX = new Map(); // Effect name -> timeout ID
        this.lastTimeMs = -1;
        this.isSyncing = false;
        this.syncId = null;
        this.novelPath = '';

        this.initPlayer();
        this.setupVisibilityHandler();
    }

    /**
     * Initializes player controls and audio element listeners.
     */
    initPlayer() {
        // Play/Pause toggle
        this.playPauseBtn.addEventListener('click', () => this.togglePlay());
        
        // Progress bar seeking
        this.progressContainer.addEventListener('click', (e) => {
            const rect = this.progressContainer.getBoundingClientRect();
            const pos = (e.clientX - rect.left) / rect.width;
            this.seekTo(pos * this.audio.duration * 1000); // Pass ms as requested
        });

        // Volume control
        this.volumeSlider.addEventListener('input', (e) => {
            this.audio.volume = e.target.value;
        });

        // Playback speed
        this.speedSelector.addEventListener('change', (e) => {
            this.audio.playbackRate = parseFloat(e.target.value);
        });

        // Close player
        this.closeBtn.addEventListener('click', () => {
            this.destroy();
            window.parent.postMessage({ type: 'close-cinema' }, '*');
            // If not in iframe, try to go back
            if (window.self === window.top) {
                window.history.back();
            }
        });

        // Audio events
        this.audio.addEventListener('play', () => {
            this.playIcon.classList.add('hidden');
            this.pauseIcon.classList.remove('hidden');
            this.startSyncLoop();
        });

        this.audio.addEventListener('pause', () => {
            this.playIcon.classList.remove('hidden');
            this.pauseIcon.classList.add('hidden');
            this.stopSyncLoop();
        });

        this.audio.addEventListener('ended', () => {
            this.stopSyncLoop();
        });

        this.audio.addEventListener('error', () => {
            console.error('Audio error:', this.audio.error);
            this.showError(`Audio playback error: ${this.audio.error ? this.audio.error.message : 'Unknown error'}`);
        });

        this.audio.addEventListener('timeupdate', () => {
            this.updateUI();
        });
    }

    setupVisibilityHandler() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.syncId) {
                    cancelAnimationFrame(this.syncId);
                    this.syncId = null;
                }
            } else if (this.isSyncing && !this.syncId) {
                this.startSyncLoop();
            }
        });
    }

    showError(message) {
        const errorOverlay = document.createElement('div');
        errorOverlay.className = 'error-overlay';
        errorOverlay.innerHTML = `
            <div class="error-content">
                <h3>Error</h3>
                <p>${message}</p>
                <button onclick="location.reload()">Reload Page</button>
            </div>
        `;
        document.body.appendChild(errorOverlay);
    }

    destroy() {
        this.audio.pause();
        this.stopSyncLoop();
    }

    /**
     * Loads the chapter manifest from the API.
     * @param {string} path - The relative path to the chapter folder.
     */
    async loadManifest(path) {
        try {
            this.novelPath = path;
            const response = await fetch(`/api/novels/manifest?path=${encodeURIComponent(path)}`);
            if (!response.ok) throw new Error(`Failed to load manifest: ${response.statusText}`);
            
            this.manifest = await response.json();
            this.events = this.manifest.events || [];
            
            // Sort events by start time
            this.events.sort((a, b) => a.start - b.start);
            
            const audioSrc = `/novels/${path}/${this.manifest.audio}`;
            this.audio.src = audioSrc;
            
            console.log(`Manifest loaded for ${path}. Total events: ${this.events.length}`);
            this.resetState();
            
        } catch (error) {
            console.error('Error loading manifest:', error);
            this.showError(`Error loading cinema manifest: ${error.message}`);
        }
    }

    resetState() {
        this.lastTimeMs = -1;
        this.nextEventIndex = 0;
        this.currentDialogue = null;
        this.currentWordSpans = [];
        this.textDisplay.innerHTML = '';
        this.charName.textContent = '';
        this.bgCurrent.style.backgroundImage = '';
        this.bgNext.style.backgroundImage = '';
        this.bgNext.classList.add('hidden');
        this.clearAllVFX();
    }

    clearAllVFX() {
        this.activeVFX.forEach((timeoutId, effect) => {
            clearTimeout(timeoutId);
        });
        this.activeVFX.clear();
        this.vfxOverlay.className = '';
    }

    togglePlay() {
        if (this.audio.paused) {
            this.audio.play();
        } else {
            this.audio.pause();
        }
    }

    seekTo(timeMs) {
        const wasPlaying = !this.audio.paused;
        this.audio.currentTime = timeMs / 1000;
        
        // Reset state and find correct index
        this.resetState();
        
        let lastBackgroundEvent = null;
        let activeDialogue = null;
        
        for (let i = 0; i < this.events.length; i++) {
            const event = this.events[i];
            if (event.start <= timeMs) {
                if (event.type === 'background') {
                    lastBackgroundEvent = event;
                } else if (event.type === 'dialogue' && (!event.end || event.end > timeMs)) {
                    activeDialogue = event;
                }
                this.nextEventIndex = i + 1;
            } else {
                this.nextEventIndex = i;
                break;
            }
        }
        
        // Apply state
        if (lastBackgroundEvent) this.updateBackground(lastBackgroundEvent, true);
        if (activeDialogue) {
            this.renderDialogue(activeDialogue);
            this.updateKaraoke(activeDialogue, timeMs);
        }
        
        this.lastTimeMs = timeMs;
        if (wasPlaying) this.audio.play();
        this.updateUI();
    }

    /**
     * Main synchronization loop using requestAnimationFrame.
     */
    startSyncLoop() {
        if (this.isSyncing && this.syncId) return;
        this.isSyncing = true;

        const loop = () => {
            if (!this.isSyncing) return;
            
            const currentTimeMs = this.audio.currentTime * 1000;
            if (Math.abs(currentTimeMs - this.lastTimeMs) > 16) { // ~60fps check
                this.processEvents(currentTimeMs);
                this.lastTimeMs = currentTimeMs;
            }
            
            this.syncId = requestAnimationFrame(loop);
        };
        
        this.syncId = requestAnimationFrame(loop);
    }

    stopSyncLoop() {
        this.isSyncing = false;
        if (this.syncId) {
            cancelAnimationFrame(this.syncId);
            this.syncId = null;
        }
    }

    /**
     * Processes events based on the current playback time using index optimization.
     * @param {number} currentTimeMs 
     */
    processEvents(currentTimeMs) {
        // Trigger upcoming events
        while (this.nextEventIndex < this.events.length) {
            const event = this.events[this.nextEventIndex];
            if (event.start <= currentTimeMs) {
                this.handleEvent(event, currentTimeMs);
                this.nextEventIndex++;
            } else {
                break;
            }
        }
        
        // Cleanup current dialogue if it ended
        if (this.currentDialogue && this.currentDialogue.end && this.currentDialogue.end <= currentTimeMs) {
            this.cleanupEvent(this.currentDialogue);
        }
        
        // Update karaoke
        if (this.currentDialogue) {
            this.updateKaraoke(this.currentDialogue, currentTimeMs);
        }
    }

    /**
     * Dispatches events based on type.
     */
    handleEvent(event, currentTimeMs) {
        switch (event.type) {
            case 'background':
                this.updateBackground(event);
                break;
            case 'dialogue':
                if (this.currentDialogue !== event) {
                    this.renderDialogue(event);
                }
                break;
            case 'vfx':
                this.applyVFX(event, currentTimeMs);
                break;
        }
    }

    cleanupEvent(event) {
        if (event.type === 'dialogue' && this.currentDialogue === event) {
            this.currentDialogue = null;
            this.currentWordSpans = [];
            this.charName.textContent = '';
            this.textDisplay.innerHTML = '';
        }
    }

    /**
     * Handles background transitions with a cross-fade and random Ken Burns effect.
     */
    updateBackground(event, immediate = false) {
        const imageUrl = `url('/novels/${this.novelPath}/${event.src}')`;
        
        // If it's already the current background, do nothing
        if (this.bgCurrent.style.backgroundImage === imageUrl) return;

        // Pick a random Ken Burns variation
        const kbEffects = ['ken-burns-in', 'ken-burns-out', 'ken-burns-left', 'ken-burns-right'];
        const randomKB = kbEffects[Math.floor(Math.random() * kbEffects.length)];

        if (immediate) {
            this.bgCurrent.style.backgroundImage = imageUrl;
            this.bgCurrent.className = 'bg-layer ' + randomKB;
            this.bgNext.classList.add('hidden');
            this.bgNext.style.backgroundImage = '';
            return;
        }

        // Use bgNext to load and fade in
        this.bgNext.style.backgroundImage = imageUrl;
        this.bgNext.className = 'bg-layer ' + randomKB;
        this.bgNext.classList.remove('hidden');

        // After transition (defined in CSS as 1.5s), swap them
        setTimeout(() => {
            if (this.bgNext.style.backgroundImage === imageUrl) {
                this.bgCurrent.style.backgroundImage = imageUrl;
                this.bgCurrent.className = 'bg-layer ' + randomKB;
                this.bgNext.classList.add('hidden');
                this.bgNext.style.backgroundImage = '';
            }
        }, 1500);
    }

    /**
     * Renders dialogue and prepares karaoke spans.
     */
    renderDialogue(event) {
        this.currentDialogue = event;
        this.charName.textContent = event.character || '';
        this.charName.style.color = event.color || '#00d4ff';
        
        this.textDisplay.innerHTML = '';
        this.currentWordSpans = [];
        
        if (event.alignment && event.alignment.length > 0) {
            // Render words as spans for karaoke
            event.alignment.forEach((item, index) => {
                const span = document.createElement('span');
                span.className = 'word';
                span.textContent = item.word;
                span.dataset.start = item.start;
                span.dataset.end = item.end;
                this.textDisplay.appendChild(span);
                this.currentWordSpans.push(span);
                
                // Add space if not the last word
                if (index < event.alignment.length - 1) {
                    this.textDisplay.appendChild(document.createTextNode(' '));
                }
            });
        } else {
            // Fallback for dialogue without alignment
            this.textDisplay.textContent = event.text;
        }
    }

    /**
     * Highlights the current word in the dialogue.
     */
    updateKaraoke(event, currentTimeMs) {
        this.currentWordSpans.forEach(span => {
            const start = parseFloat(span.dataset.start);
            const end = parseFloat(span.dataset.end);
            
            if (currentTimeMs >= start && currentTimeMs <= end) {
                span.classList.add('active');
            } else if (currentTimeMs > end) {
                span.classList.add('active'); 
            } else {
                span.classList.remove('active');
            }
        });
    }

    /**
     * Applies VFX classes and handles duration.
     */
    applyVFX(event, currentTimeMs) {
        const effectClass = `vfx-${event.effect}`;
        
        if (!this.vfxOverlay.classList.contains(effectClass)) {
            this.vfxOverlay.classList.add(effectClass);
            
            // Some effects are transient (flash, shake)
            if (event.duration) {
                if (this.activeVFX.has(event.effect)) {
                    clearTimeout(this.activeVFX.get(event.effect));
                }
                
                const timeoutId = setTimeout(() => {
                    this.vfxOverlay.classList.remove(effectClass);
                    this.activeVFX.delete(event.effect);
                }, event.duration);
                
                this.activeVFX.set(event.effect, timeoutId);
            }
        }
    }

    updateUI() {
        const current = this.audio.currentTime;
        const total = this.audio.duration || 0;
        
        // Update progress bar
        const percent = (current / total) * 100;
        this.progressBar.style.width = `${percent}%`;
        
        // Update time display
        this.timeDisplay.textContent = `${this.formatTime(current)} / ${this.formatTime(total)}`;
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return '00:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
}

// Initialize player when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.player = new CinemaPlayer();
    
    // Auto-load if path is in URL
    const urlParams = new URLSearchParams(window.location.search);
    const path = urlParams.get('path');
    if (path) {
        window.player.loadManifest(path);
    }

    // Set VFX scaling from URL
    const vfxIntensity = urlParams.get('vfx') || 100;
    document.documentElement.style.setProperty('--vfx-scale', vfxIntensity / 100);
});
