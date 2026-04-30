<template>
    <div id="confirmModal" class="modal-overlay" :class="{ active: uiStore.confirmModalVisible }" style="z-index: 2050;">
        <div class="modal-content confirm-modal-content">
            <h4 class="confirm-title">{{ uiStore.confirmMsg }}</h4>
            <div
                v-if="uiStore.confirmNotes"
                v-html="uiStore.confirmNotes"
                class="confirm-notes">
            </div>
            <div class="modal-footer confirm-footer">
                <button class="outline" @click="uiStore.handleConfirm(false)">{{ $t('cancel') || 'Cancel' }}</button>
                <button class="primary" @click="uiStore.handleConfirm(true)">{{ $t('ok') || 'OK' }}</button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';
const uiStore = useUIStore();
</script>

<style scoped>
.confirm-modal-content {
    width: min(88vw, 560px);
    min-width: min(320px, 88vw);
    padding: clamp(18px, 2.2vw, 28px);
}

.confirm-title {
    margin: 0 0 18px;
    text-align: center;
    line-height: 1.35;
}

.confirm-notes {
    margin-bottom: 18px;
    font-size: 13px;
    opacity: 0.8;
    text-align: left;
    max-height: min(32vh, 220px);
    overflow-y: auto;
    background: rgba(0, 0, 0, 0.05);
    padding: 10px;
    border-radius: 4px;
}

.confirm-footer {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    border: none;
    padding: 0;
    margin-top: 2px;
    text-align: center;
}

.confirm-footer button {
    min-width: 92px;
}

@media (max-width: 540px) {
    .confirm-footer {
        flex-wrap: wrap;
    }

    .confirm-footer button {
        flex: 1 1 120px;
        max-width: 180px;
    }
}
</style>
