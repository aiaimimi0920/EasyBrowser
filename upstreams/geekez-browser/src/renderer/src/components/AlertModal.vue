<template>
    <div id="alertModal" class="modal-overlay" :class="{ active: uiStore.alertModalVisible }" style="z-index: 2500;">
        <div class="modal-content" style="width: 350px; text-align: center;">
            <div class="modal-header" style="justify-content: center; border: none;">
                <span style="color: var(--accent); font-size: 30px;">ℹ</span>
            </div>
            <p style="margin: 10px 0 20px; white-space: pre-wrap;">{{ uiStore.alertMsg }}</p>
            <button v-if="uiStore.alertShowBtn" class="primary" @click="uiStore.alertModalVisible = false">{{ $t('ok') || 'OK' }}</button>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';
const uiStore = useUIStore();
</script>
