<template>
    <div id="progressModal" class="modal-overlay" :class="{ active: uiStore.progressModalVisible }" style="z-index: 2500;" @mousedown.stop>
        <div class="modal-content" style="width: 400px; text-align: center; padding: 30px;">
            <div style="font-size: 16px; font-weight: 600; margin-bottom: 10px; color: var(--accent);">
                {{ uiStore.progressTitle }}
            </div>
            
            <div style="width: 100%; background: rgba(0,0,0,0.2); height: 10px; border-radius: 5px; overflow: hidden; margin: 20px 0; border: 1px solid var(--border);">
                <div :style="{ width: uiStore.progressPercent + '%', background: 'var(--accent)', height: '100%', transition: 'width 0.3s ease' }"></div>
            </div>
            
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-bottom: 15px;">
                <span>{{ uiStore.progressMessage || '...' }}</span>
                <span style="font-weight: 600; color: var(--accent);">{{ uiStore.progressPercent }}%</span>
            </div>

            <p style="font-size: 12px; color: #e74c3c; font-weight: 600; margin-top: 10px; padding: 10px; background: rgba(231, 76, 60, 0.1); border-radius: 6px;">
                ⚠️ {{ uiStore.progressWarn }}
            </p>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';
const uiStore = useUIStore();
</script>
