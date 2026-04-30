<template>
    <div id="inputModal" class="modal-overlay" :class="{ active: uiStore.inputModalVisible }" style="z-index: 2080;">
        <div class="modal-content" style="width: 350px;">
            <h4 style="margin-bottom:15px;">{{ uiStore.inputModalTitle }}</h4>
            <input type="text" v-model="uiStore.inputModalValue" @keyup.enter="uiStore.submitInput" class="input" style="width:100%; box-sizing:border-box; margin-bottom:20px;">
            <div class="modal-footer" style="justify-content:flex-end; gap:10px; border:none; padding:0;">
                <button class="outline" @click="uiStore.inputModalVisible = false">{{ $t('cancel') || 'Cancel' }}</button>
                <button class="primary" @click="uiStore.submitInput">{{ $t('ok') || 'OK' }}</button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';
const uiStore = useUIStore();
</script>
